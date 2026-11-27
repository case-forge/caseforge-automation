#!/usr/bin/env python3
from __future__ import annotations

import contextvars
import json
import os
import re
import socket
import sys
import threading
import time
import datetime as dt
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

try:
    import ops_db
except ModuleNotFoundError:
    from tools import ops_db
try:
    import firm_profile
except ModuleNotFoundError:
    from tools import firm_profile


try:
    import pyodbc
    _PYODBC_AVAILABLE = True
except ImportError:
    _PYODBC_AVAILABLE = False


_SQLITE_ENV_KEY = "LOCAL_SQLITE_PATH"
_LOCAL_ENV_KEY  = "LOCAL_SQL_CONNECTION_STRING"
_SQLITE_DEFAULT_DISABLE_ENV = "CASEFORGE_SQL_DISABLE_LOCAL_SQLITE_DEFAULT"
_SQL_BACKEND_ENV = "CASEFORGE_SQL_BACKEND"
_RETIRED_FOLDER_LOCATIONS_ENV = "CASEFORGE_SQL_ENABLE_RETIRED_MATTER_FOLDER_LOCATIONS"
_DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "clients" / "caseforge-clientdb.sqlite"

_RAW_QUERY_TRUSTED_RUNTIME_LABELS = {
    "codex-cli",
    "claude-cli",
    "gemini-cli",
    "copilot-cli",
    "vscode",
    "caseforge-startup",
}
_RAW_QUERY_DENY_RE = re.compile(
    r"\b("
    r"ALTER|BACKUP|BULK|CREATE|DBCC|DECLARE|DELETE|DROP|EXEC|EXECUTE|GRANT|INSERT|"
    r"MERGE|RECONFIGURE|RESTORE|REVOKE|SET|SHUTDOWN|TRUNCATE|UPDATE|USE"
    r")\b",
    re.IGNORECASE,
)
_RAW_QUERY_COMMENT_RE = re.compile(r"(--|/\*|\*/)")



def _relocate_top_clauses(sql: str) -> str:
    pattern = re.compile(r'\bSELECT\s+(DISTINCT\s+)?TOP\s*\(?\s*(\d+)\s*\)?\s*', re.IGNORECASE)
    while True:
        m = pattern.search(sql)
        if not m:
            return sql
        limit_val = m.group(2)
        distinct = m.group(1) or ""
        before = sql[: m.start()]
        after = sql[m.end():]
        depth = 0
        in_str = False
        end_idx = len(after)
        i = 0
        while i < len(after):
            ch = after[i]
            if ch == "'":
                in_str = not in_str
            elif not in_str:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    if depth == 0:
                        end_idx = i
                        break
                    depth -= 1
            i += 1
        scope = after[:end_idx].rstrip('; \n\t')
        rest = after[end_idx:]
        sql = before + "SELECT " + distinct + scope + f"\nLIMIT {limit_val}" + rest



def _translate_tsql(sql: str) -> str:
    sql = _relocate_top_clauses(sql)

    sql = re.sub(r'\bdbo\.', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bGETUTCDATE\s*\(\)', "datetime('now')", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bSYSUTCDATETIME\s*\(\)', "datetime('now')", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bGETDATE\s*\(\)', "datetime('now','localtime')", sql, flags=re.IGNORECASE)

    for t in ('nvarchar', 'varchar', 'nchar', 'char', 'ntext', 'uniqueidentifier', 'xml'):
        sql = re.sub(rf'\bAS\s+{t}\s*(?:\([^)]*\))?', 'AS TEXT', sql, flags=re.IGNORECASE)
    for t in ('bigint', 'smallint', 'tinyint'):
        sql = re.sub(rf'\bAS\s+{t}\b', 'AS INTEGER', sql, flags=re.IGNORECASE)

    sql = re.sub(
        r'\bLEFT\s*\(\s*([^,]+?)\s*,\s*(\d+)\s*\)',
        lambda mo: f'substr({mo.group(1).strip()}, 1, {mo.group(2)})',
        sql, flags=re.IGNORECASE,
    )

    return sql


def _normalise_params(params: tuple) -> tuple:
    if len(params) == 1 and isinstance(params[0], (list, tuple)):
        return tuple(params[0])
    return params


_QUERY_BUDGET_DEFAULT = 3000
_query_budget_state = {"count": 0, "limit": _QUERY_BUDGET_DEFAULT}


def _reset_query_budget() -> None:
    _query_budget_state["count"] = 0
    _query_budget_state["limit"] = int(os.getenv("CASEFORGE_SQL_QUERY_BUDGET", _QUERY_BUDGET_DEFAULT))


def _check_query_budget(sql: str) -> None:
    _query_budget_state["count"] += 1
    if _query_budget_state["count"] > _query_budget_state["limit"]:
        raise RuntimeError(
            f"clientdb_sql query budget exceeded: {_query_budget_state['count']} queries "
            f"on one connection (limit {_query_budget_state['limit']}, override with "
            f"CASEFORGE_SQL_QUERY_BUDGET). Likely a runaway loop, not legitimate work -- "
            f"last SQL: {sql[:200]!r}"
        )


class _SqliteCursor:
    def __init__(self, cur: object) -> None:
        self._cur = cur

    def execute(self, sql: str, *params) -> "_SqliteCursor":
        _check_query_budget(sql)
        self._cur.execute(_translate_tsql(sql), _normalise_params(params))
        return self

    def fetchone(self) -> object:
        return self._cur.fetchone()

    def fetchall(self) -> list:
        return self._cur.fetchall()

    @property
    def description(self) -> object:
        return self._cur.description

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    def __iter__(self):
        return iter(self._cur)


class _SqliteConn:

    def __init__(self, conn: object) -> None:
        self._conn = conn

    def cursor(self) -> _SqliteCursor:
        return _SqliteCursor(self._conn.cursor())

    def execute(self, sql: str, params: tuple = ()) -> _SqliteCursor:
        _check_query_budget(sql)
        return _SqliteCursor(self._conn.execute(_translate_tsql(sql), params))

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


@contextmanager
def _sqlite_get_connection():
    import sqlite3 as _sqlite3
    path = _sqlite_path()
    if not path:
        raise RuntimeError(f"SQLite path not set and default DB not found at {_DEFAULT_SQLITE_PATH}")
    conn = _sqlite3.connect(path)
    conn.row_factory = _sqlite3.Row
    wrapped = _SqliteConn(conn)
    _reset_query_budget()
    started = time.perf_counter()
    try:
        yield wrapped
        conn.commit()
    except Exception as exc:
        _record_sql_probe("failed", duration_ms=int((time.perf_counter() - started) * 1000), exc=exc)
        conn.rollback()
        raise
    else:
        _record_sql_probe("success", duration_ms=int((time.perf_counter() - started) * 1000))
    finally:
        conn.close()




_PG_URL_ENV = "CASEFORGE_CLIENTDB_PG_URL"


def _pg_url() -> str:
    cs = os.environ.get(_PG_URL_ENV, "").strip()
    if not cs:
        try:
            from env_bootstrap import load_repo_secrets

            load_repo_secrets(required_keys=(_PG_URL_ENV,))
        except Exception:
            pass
        cs = os.environ.get(_PG_URL_ENV, "").strip()
    return cs


def _translate_tsql_pg(sql: str) -> str:
    sql = _relocate_top_clauses(sql)

    sql = re.sub(r'\bdbo\.', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bGETUTCDATE\s*\(\)', "(now() at time zone 'utc')", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bSYSUTCDATETIME\s*\(\)', "(now() at time zone 'utc')", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bGETDATE\s*\(\)', "now()", sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bISNULL\s*\(', 'COALESCE(', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\[([A-Za-z_][A-Za-z0-9_]*)\]', r'"\1"', sql)

    for t in ('nvarchar', 'varchar', 'nchar', 'char', 'ntext', 'uniqueidentifier', 'xml'):
        sql = re.sub(rf'\bAS\s+{t}\s*(?:\([^)]*\))?', 'AS TEXT', sql, flags=re.IGNORECASE)

    parts = sql.split("'")
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r'\bLIKE\b', 'ILIKE', parts[i], flags=re.IGNORECASE)
    sql = "'".join(parts)

    parts = sql.split("'")
    returning: list[str] = []
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(
            r'\bOUTPUT\s+INSERTED\.(\w+)\s*',
            lambda m: returning.append(m.group(1)) or '',
            parts[i],
            flags=re.IGNORECASE,
        )
    sql = "'".join(parts)
    if returning:
        sql = sql.rstrip().rstrip(';') + " RETURNING " + ", ".join(returning)

    out, in_str = [], False
    for ch in sql:
        if ch == "'":
            in_str = not in_str
            out.append(ch)
        elif ch == '%':
            out.append('%%')
        elif ch == '?' and not in_str:
            out.append('%s')
        else:
            out.append(ch)
    return ''.join(out)


class _PgCursor:
    def __init__(self, cur: object) -> None:
        self._cur = cur

    def execute(self, sql: str, *params) -> "_PgCursor":
        _check_query_budget(sql)
        self._cur.execute(_translate_tsql_pg(sql), _normalise_params(params) or None)
        return self

    def fetchone(self) -> object:
        return self._cur.fetchone()

    def fetchall(self) -> list:
        return self._cur.fetchall()

    def fetchmany(self, n: int = 1000) -> list:
        return self._cur.fetchmany(n)

    @property
    def description(self) -> object:
        return self._cur.description

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    def __iter__(self):
        return iter(self._cur)


class _PgConn:

    def __init__(self, conn: object) -> None:
        self._conn = conn

    def cursor(self) -> _PgCursor:
        from psycopg2.extras import NamedTupleCursor
        return _PgCursor(self._conn.cursor(cursor_factory=NamedTupleCursor))

    def execute(self, sql: str, params: tuple = ()) -> _PgCursor:
        return self.cursor().execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()



_ACTOR_ENV = "CASEFORGE_SQL_ACTOR"
_ACTOR: contextvars.ContextVar[str] = contextvars.ContextVar("clientdb_sql_actor", default="")
_PG_APP_NAME_MAX = 63


def application_name(argv0: str | None = None) -> str:
    raw = argv0 if argv0 is not None else (sys.argv[0] if sys.argv and sys.argv[0] else "")
    path = Path(raw) if raw and raw != "-c" else None
    name = f"{path.parent.name}/{path.name}" if path and path.parent.name else (path.name if path else "python")
    cleaned = "".join(ch for ch in name if ch.isprintable() and ord(ch) < 128)
    return f"caseforge:{cleaned}"[:_PG_APP_NAME_MAX]


def current_actor() -> str:
    return _ACTOR.get() or os.environ.get(_ACTOR_ENV, "").strip()


@contextmanager
def acting_as(actor: str):
    token = _ACTOR.set(" ".join(str(actor or "").split())[:200])
    try:
        yield
    finally:
        _ACTOR.reset(token)


def set_actor(conn, actor: str) -> None:
    raw = getattr(conn, "_conn", conn)
    if type(raw).__module__.split(".")[0] != "psycopg2":
        return
    try:
        with raw.cursor() as cur:
            cur.execute("SELECT set_config('caseforge.actor', %s, false)", (" ".join(str(actor or "").split())[:200],))
        _PG_ACTOR_SET.add(id(raw))
    except Exception:
        pass



_PG_POOL_MAX_ENV = "CASEFORGE_SQL_PG_POOL_MAX"
_PG_POOL_DEFAULT_MAX = 8
_PG_POOL_IDLE_CHECK_SECONDS = 30.0
_PG_POOL_LOCK = threading.Lock()
_PG_POOL: tuple[tuple, object] | None = None
_PG_LAST_USED: dict[int, float] = {}
_PG_ACTOR_SET: set[int] = set()


def _pg_pool_max() -> int:
    try:
        return int(os.environ.get(_PG_POOL_MAX_ENV, _PG_POOL_DEFAULT_MAX))
    except ValueError:
        return _PG_POOL_DEFAULT_MAX


def _pg_pool_for(url: str, app_name: str):
    global _PG_POOL
    size = _pg_pool_max()
    if size <= 0:
        return None
    key = (os.getpid(), url, app_name, size)
    with _PG_POOL_LOCK:
        if _PG_POOL is not None and _PG_POOL[0] == key:
            return _PG_POOL[1]
        try:
            from psycopg2 import pool as pg_pool

            created = pg_pool.ThreadedConnectionPool(1, size, url, connect_timeout=15, application_name=app_name)
        except Exception:
            return None
        _PG_POOL = (key, created)
        return created


def _pg_checkout(pool):
    try:
        raw = pool.getconn()
    except Exception:
        return None
    now = time.monotonic()
    try:
        if raw.closed:
            raise RuntimeError("closed")
        if now - _PG_LAST_USED.get(id(raw), now) > _PG_POOL_IDLE_CHECK_SECONDS:
            with raw.cursor() as cur:
                cur.execute("SELECT 1")
            raw.rollback()
    except Exception:
        _pg_discard(pool, raw)
        return None
    return raw


def _pg_discard(pool, raw) -> None:
    _PG_LAST_USED.pop(id(raw), None)
    _PG_ACTOR_SET.discard(id(raw))
    try:
        pool.putconn(raw, close=True)
    except Exception:
        pass


def _pg_checkin(pool, raw) -> None:
    try:
        if raw.closed:
            raise RuntimeError("closed")
        if id(raw) in _PG_ACTOR_SET:
            with raw.cursor() as cur:
                cur.execute("RESET caseforge.actor")
            _PG_ACTOR_SET.discard(id(raw))
            raw.commit()
        _PG_LAST_USED[id(raw)] = time.monotonic()
        pool.putconn(raw)
    except Exception:
        _pg_discard(pool, raw)


@contextmanager
def _pg_get_connection():
    import psycopg2
    url, app_name = _pg_url(), application_name()
    pool = _pg_pool_for(url, app_name)
    conn = _pg_checkout(pool) if pool is not None else None
    if conn is None:
        pool = None
        conn = psycopg2.connect(url, connect_timeout=15, application_name=app_name)
    actor = current_actor()
    if actor:
        set_actor(conn, actor)
        try:
            conn.commit()
        except Exception:
            pass
    wrapped = _PgConn(conn)
    _reset_query_budget()
    started = time.perf_counter()
    try:
        yield wrapped
        conn.commit()
    except Exception as exc:
        _record_sql_probe("failed", duration_ms=int((time.perf_counter() - started) * 1000), exc=exc)
        try:
            conn.rollback()
        except Exception:
            if pool is None:
                raise
        raise
    else:
        _record_sql_probe("success", duration_ms=int((time.perf_counter() - started) * 1000))
    finally:
        if pool is not None:
            _pg_checkin(pool, conn)
        else:
            conn.close()


_sql_probe_count: int = 0


def _probe_error_summary(exc: BaseException | None) -> str:
    if exc is None:
        return ""
    name = type(exc).__name__
    pgcode = getattr(exc, "pgcode", None)
    return f"{name} (pgcode {pgcode})" if pgcode else name


def _record_sql_probe(status: str, duration_ms: int = 0, exc: BaseException | None = None) -> None:
    try:
        from telemetry_sqlite import record_runtime_event, utc_now_z

        record_runtime_event(
            {
                "timestamp": utc_now_z(),
                "event_name": "sql_probe",
                "runtime_label": os.environ.get("CASEFORGE_RUNTIME_LABEL", ""),
                "model_label": os.environ.get("CASEFORGE_MODEL_LABEL", ""),
                "command": "clientdb_sql.get_connection",
                "metrics": {
                    "status": status,
                    "duration_ms": duration_ms,
                    "error": _probe_error_summary(exc),
                },
            }
        )
    except Exception:
        pass


def _sqlite_default_disabled() -> bool:
    return os.environ.get(_SQLITE_DEFAULT_DISABLE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _sql_backend_is_local() -> bool:
    return os.environ.get(_SQL_BACKEND_ENV, "").strip().lower() == "local"


def _sqlite_path() -> str:
    configured = os.environ.get(_SQLITE_ENV_KEY, "").strip()
    if configured:
        return configured
    if _sqlite_default_disabled():
        return ""
    if _sql_backend_is_local():
        return str(_DEFAULT_SQLITE_PATH)
    return ""


def _using_sqlite() -> bool:
    return bool(_sqlite_path())


def _using_postgres() -> bool:
    return bool(_pg_url())


def configured_backend() -> str:
    if _sqlite_path():
        return "sqlite"
    if _pg_url():
        return "postgres"
    try:
        _connection_string()
    except RuntimeError:
        return ""
    return "sqlserver-local"


def _raw_query_enabled() -> bool:
    if os.environ.get("CASEFORGE_SQL_ENABLE_RAW_QUERY", "").strip() == "1":
        return True
    runtime = os.environ.get("CASEFORGE_RUNTIME_LABEL", "").strip().lower()
    return runtime in _RAW_QUERY_TRUSTED_RUNTIME_LABELS


def _validate_readonly_query(sql: str) -> str:
    statement = (sql or "").strip()
    if not statement:
        raise RuntimeError("Raw SQL query is empty.")
    if _RAW_QUERY_COMMENT_RE.search(statement):
        raise RuntimeError("Raw SQL query comments are not allowed.")
    if statement.endswith(";"):
        statement = statement[:-1].strip()
    if ";" in statement:
        raise RuntimeError("Raw SQL query must contain exactly one statement.")
    if not re.match(r"^(SELECT|WITH)\b", statement, flags=re.IGNORECASE):
        raise RuntimeError("Raw SQL query is limited to SELECT/CTE read-only statements.")
    if _RAW_QUERY_DENY_RE.search(statement):
        raise RuntimeError("Raw SQL query contains a blocked write/admin keyword.")
    return statement


def _sqlite_table_exists(conn, table_name: str) -> bool:
    if not _using_sqlite():
        return True
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _sqlite_column_exists(conn, table_name: str, column_name: str) -> bool:
    if not _using_sqlite():
        return True
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    except Exception:
        return False
    return any(str(row[1]) == column_name for row in rows)


def _db_column_exists(conn, table_name: str, column_name: str) -> bool:
    if _using_sqlite():
        return _sqlite_column_exists(conn, table_name, column_name)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ? AND COLUMN_NAME = ?
            """,
            (table_name, column_name),
        )
        return cursor.fetchone() is not None
    except Exception:
        return False


_CLIENT_SEARCH_OPTIONAL_MATTER_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("intake_source", ("intake_source",)),
    ("referral_source", ("referral_source",)),
    ("referral_sent_at", ("referral_sent_at",)),
    ("source_email_sent_at", ("source_email_sent_at",)),
    ("created_utc", ("created_utc",)),
    ("primary_person_id", ("primary_person_id",)),
    ("withheld_fields", ("withheld_fields",)),
    ("benefits_canonical", ("benefits_canonical",)),
    ("children_summary", ("children_summary",)),
    ("property_summary", ("property_summary",)),
    ("relationship_start", ("relationship_start", "relationship_start_date", "relationship_started_at")),
    ("relationship_end", ("relationship_end", "relationship_end_date", "relationship_ended_at")),
    ("marriage_date", ("marriage_date",)),
    ("divorce_date", ("divorce_date",)),
    ("lived_together", ("lived_together",)),
    ("married", ("married",)),
    ("bail_conditions", ("bail_conditions",)),
    ("bail_end_date", ("bail_end_date",)),
    ("crime_refs", ("crime_refs",)),
    ("tracker_notes", ("tracker_notes",)),
    ("order_type_tags", ("order_type_tags",)),
    ("c8_phone", ("c8_phone",)),
    ("c8_email", ("c8_email",)),
    ("c8_address", ("c8_address",)),
)
_CLIENT_SEARCH_OPTIONAL_LIVE_STATUS_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("draft_order_status", ("draft_order_status",)),
    ("waiting_for_sealed_order", ("waiting_for_sealed_order",)),
)


def _client_search_optional_matter_select(conn) -> str:
    expressions: list[str] = []
    for alias, candidates in _CLIENT_SEARCH_OPTIONAL_MATTER_FIELDS:
        source_column = next(
            (column for column in candidates if _db_column_exists(conn, "matters", column)),
            "",
        )
        expressions.append(f"m.{source_column} AS {alias}" if source_column else f"NULL AS {alias}")
    for column in ("sex", "sex_other"):
        expressions.append(f"p.{column} AS {column}" if _db_column_exists(conn, "people", column) else f"NULL AS {column}")
    return ",\n                ".join(expressions)


def _client_search_optional_live_status_select(conn) -> str:
    expressions: list[str] = []
    for alias, candidates in _CLIENT_SEARCH_OPTIONAL_LIVE_STATUS_FIELDS:
        source_column = next(
            (column for column in candidates if _db_column_exists(conn, "matter_live_status", column)),
            "",
        )
        expressions.append(f"ls.{source_column} AS {alias}" if source_column else f"NULL AS {alias}")
    return ",\n                ".join(expressions)


_SQLITE_CLIENT_SEARCH_SCHEMA: dict[tuple[str, int], tuple[bool, bool, bool, str, str]] = {}


def _sqlite_client_search_schema(conn) -> tuple[bool, bool, bool, str, str]:
    try:
        version = int(conn.execute("PRAGMA schema_version").fetchone()[0])
    except Exception:
        version = None
    key = (_sqlite_path(), version) if version is not None else None
    if key is not None:
        cached = _SQLITE_CLIENT_SEARCH_SCHEMA.get(key)
        if cached is not None:
            return cached
    result = (
        _sqlite_column_exists(conn, "matters", "closed_at"),
        _sqlite_column_exists(conn, "matters", "closed_by"),
        _sqlite_column_exists(conn, "matters", "closed_notes"),
        _client_search_optional_matter_select(conn),
        _client_search_optional_live_status_select(conn),
    )
    if key is not None:
        _SQLITE_CLIENT_SEARCH_SCHEMA[key] = result
    return result


def _flag_to_bool(value) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _legacy_permission_row(matter_id: str) -> dict | None:
    mid = str(matter_id or "").strip()
    if not mid:
        return None
    try:
        with get_connection() as conn:
            if _using_sqlite() and not _sqlite_table_exists(conn, "matter_permissions"):
                return None
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    matter_id,
                    allow_email_print,
                    email_print_set_at,
                    email_print_set_by,
                    notes,
                    updated_at
                FROM matter_permissions
                WHERE matter_id = ?
                """,
                (mid,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cols = [col[0] for col in cursor.description]
            return dict(zip(cols, row))
    except Exception:
        return None


def _legacy_email_permission_rows(include_closed: bool = False) -> list[dict]:
    try:
        with get_connection() as conn:
            if _using_sqlite() and not _sqlite_table_exists(conn, "matter_permissions"):
                return []
            if _using_sqlite():
                has_closed_at = _sqlite_column_exists(conn, "matters", "closed_at")
                closed_expr = "m.closed_at" if has_closed_at else "NULL AS closed_at"
                closed_where = "" if include_closed or not has_closed_at else "AND m.closed_at IS NULL"
            else:
                closed_expr = "m.closed_at"
                closed_where = "" if include_closed else "AND m.closed_at IS NULL"
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT
                    mp.matter_id,
                    m.canonical_name,
                    mp.allow_email_print,
                    mp.email_print_set_at,
                    mp.email_print_set_by,
                    mp.notes,
                    {closed_expr}
                FROM matter_permissions mp
                LEFT JOIN matters m ON m.matter_id = mp.matter_id
                WHERE 1=1 {closed_where}
                ORDER BY m.canonical_name
                """
            )
            cols = [col[0] for col in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
    except Exception:
        return []


_LEGACY_PERMISSION_COLUMNS = (
    "allow_email_print",
    "email_print_set_at",
    "email_print_set_by",
)


def _mirror_permission_to_legacy(
    matter_id: str,
    *,
    allow_email_print: bool | None | object = ...,
    set_by: str = "operator",
    notes: str = "",
) -> None:
    mid = str(matter_id or "").strip()
    if not mid:
        return

    def _flag(value: bool | None | object) -> bool | None | object:
        if value is ...:
            return ...
        return None if value is None else bool(value)

    now = dt.datetime.now(dt.timezone.utc)
    fields: dict[str, Any] = {}
    if allow_email_print is not ...:
        fields.update(
            {
                "allow_email_print": _flag(allow_email_print),
                "email_print_set_at": now,
                "email_print_set_by": str(set_by or "operator"),
            }
        )
    if not fields:
        return
    if notes:
        fields["notes"] = str(notes)
    fields["updated_at"] = now
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            if _using_sqlite() and not _sqlite_table_exists(conn, "matter_permissions"):
                return
            cursor.execute("SELECT matter_id FROM matter_permissions WHERE matter_id = ?", (mid,))
            exists = cursor.fetchone() is not None
            if exists:
                assignments = ", ".join(f"{col} = ?" for col in fields)
                cursor.execute(
                    f"UPDATE matter_permissions SET {assignments} WHERE matter_id = ?",
                    [*fields.values(), mid],
                )
            else:
                payload = {col: None for col in _LEGACY_PERMISSION_COLUMNS}
                payload.update(fields)
                payload["notes"] = payload.get("notes") or ""
                payload["created_at"] = now
                cols = ["matter_id", *payload.keys()]
                placeholders = ", ".join("?" for _ in cols)
                cursor.execute(
                    f"INSERT INTO matter_permissions ({', '.join(cols)}) VALUES ({placeholders})",
                    [mid, *payload.values()],
                )
            conn.commit()
    except Exception as exc:
        print(f"[clientdb_sql] WARNING: Azure matter_permissions mirror failed for {mid}: {exc}", file=sys.stderr)


def _matter_summaries(matter_ids: list[str]) -> dict[str, dict]:
    ids = [str(item or "").strip() for item in matter_ids if str(item or "").strip()]
    if not ids:
        return {}
    try:
        placeholders = ", ".join("?" for _ in ids)
        with get_connection() as conn:
            if _using_sqlite():
                has_closed_at = _sqlite_column_exists(conn, "matters", "closed_at")
                closed_expr = "m.closed_at" if has_closed_at else "NULL AS closed_at"
            else:
                closed_expr = "m.closed_at"
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT m.matter_id, m.canonical_name, {closed_expr}
                FROM matters m
                WHERE CAST(m.matter_id AS TEXT) IN ({placeholders})
                """,
                tuple(ids),
            )
            cols = [col[0] for col in cursor.description]
            return {str(row[0]): dict(zip(cols, row)) for row in cursor.fetchall()}
    except Exception:
        return {}


def _ensure_sqlite_matter_permissions(conn) -> None:
    if not _using_sqlite():
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS matter_permissions (
            matter_id            TEXT PRIMARY KEY,
            allow_email_print    INTEGER,
            email_print_set_at   TEXT,
            email_print_set_by   TEXT,
            allow_sos_to_court_draft INTEGER,
            sos_to_court_draft_set_at TEXT,
            sos_to_court_draft_set_by TEXT,
            notes                TEXT,
            updated_at           TEXT
        )
        """
    )
    for col, defn in (
        ("allow_sos_to_court_draft", "INTEGER"),
        ("sos_to_court_draft_set_at", "TEXT"),
        ("sos_to_court_draft_set_by", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE matter_permissions ADD COLUMN {col} {defn}")
        except Exception:
            pass


def _ensure_sqlite_matter_closed_columns(conn) -> None:
    if not _using_sqlite():
        return
    for col, defn in (
        ("closed_at", "TEXT"),
        ("closed_by", "TEXT"),
        ("closed_notes", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE matters ADD COLUMN {col} {defn}")
        except Exception:
            pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS ix_matters_closed_at ON matters (closed_at)")
    except Exception:
        pass


def _connection_string() -> str:
    cs = os.environ.get(_LOCAL_ENV_KEY, "").strip()
    if not cs:
        try:
            from env_bootstrap import load_repo_secrets

            load_repo_secrets(required_keys=(_LOCAL_ENV_KEY,))
        except Exception:
            pass
        cs = os.environ.get(_LOCAL_ENV_KEY, "").strip()
    if not cs:
        raise RuntimeError(
            f"No local SQL Server connection string set. "
            f"Set {_LOCAL_ENV_KEY!r} (see tools/setup-local-sql.sh) or use "
            f"{_PG_URL_ENV!r} (Postgres, caseforge-clientdb) / {_SQLITE_ENV_KEY!r} "
            f"(SQLite) instead for anything other than local dialect testing."
        )
    return cs


def _require_pyodbc() -> None:
    if _sqlite_path() or _pg_url():
        return
    if not _PYODBC_AVAILABLE:
        raise RuntimeError(
            "pyodbc is not installed. Install ODBC Driver 18 and 'pip install pyodbc' "
            "manually (see tools/setup-local-sql.sh)."
        )


_LOCAL_SQL_CONNECT_TIMEOUT_SECONDS = 10


@contextmanager
def get_connection() -> Generator[object, None, None]:
    global _sql_probe_count
    _sql_probe_count += 1

    if _sqlite_path():
        with _sqlite_get_connection() as conn:
            yield conn
        return

    if _pg_url():
        with _pg_get_connection() as conn:
            yield conn
        return

    _require_pyodbc()
    started = time.perf_counter()
    conn_str = _connection_string()
    try:
        conn = pyodbc.connect(conn_str, timeout=_LOCAL_SQL_CONNECT_TIMEOUT_SECONDS)
    except Exception as exc:
        _record_sql_probe("failed", duration_ms=int((time.perf_counter() - started) * 1000), exc=exc)
        raise
    try:
        yield conn
        conn.commit()
    except Exception as exc:
        _record_sql_probe("failed", duration_ms=int((time.perf_counter() - started) * 1000), exc=exc)
        conn.rollback()
        raise
    else:
        _record_sql_probe("success", duration_ms=int((time.perf_counter() - started) * 1000))
    finally:
        conn.close()


def get_email_print_permission(matter_id: str) -> bool | None:
    row = ops_db.get_permission_row(matter_id)
    if row and row.get("allow_email_print") is not None:
        return _flag_to_bool(row.get("allow_email_print"))
    legacy = _legacy_permission_row(matter_id)
    if legacy and legacy.get("allow_email_print") is not None:
        return _flag_to_bool(legacy.get("allow_email_print"))
    return None


def list_email_print_permissions(include_closed: bool = False) -> list[dict]:
    merged: dict[str, dict] = {
        str(row.get("matter_id") or ""): dict(row)
        for row in _legacy_email_permission_rows(include_closed=include_closed)
        if str(row.get("matter_id") or "").strip()
    }
    ops_rows = ops_db.list_permissions()
    summaries = _matter_summaries([str(row.get("matter_id") or "") for row in ops_rows])
    for row in ops_rows:
        mid = str(row.get("matter_id") or "").strip()
        if not mid:
            continue
        base = merged.get(mid, {"matter_id": mid})
        summary = summaries.get(mid, {})
        base["canonical_name"] = base.get("canonical_name") or summary.get("canonical_name") or ""
        base["closed_at"] = base.get("closed_at") or summary.get("closed_at")
        for field in (
            "allow_email_print",
            "email_print_set_at",
            "email_print_set_by",
            "allow_sos_to_court_draft",
            "sos_to_court_draft_set_at",
            "sos_to_court_draft_set_by",
            "notes",
            "updated_at",
        ):
            base[field] = row.get(field)
        merged[mid] = base

    rows = list(merged.values())
    if not include_closed:
        inactive = ops_db.inactive_matter_ids()
        rows = [
            row for row in rows
            if str(row.get("matter_id") or "").strip() not in inactive
            and not str(row.get("closed_at") or "").strip()
        ]
    return sorted(rows, key=lambda row: str(row.get("canonical_name") or row.get("matter_id") or ""))


def set_email_print_permission(
    matter_id: str,
    allowed: bool | None,
    set_by: str = "operator",
    notes: str = "",
) -> None:
    ops_db.upsert_permission(
        matter_id,
        allow_email_print=allowed,
        set_by=set_by,
        notes=notes,
    )
    _mirror_permission_to_legacy(matter_id, allow_email_print=allowed, set_by=set_by, notes=notes)


def get_sos_to_court_draft_permission(matter_id: str) -> bool | None:
    row = ops_db.get_permission_row(matter_id)
    if row and row.get("allow_sos_to_court_draft") is not None:
        return _flag_to_bool(row.get("allow_sos_to_court_draft"))
    legacy = _legacy_permission_row(matter_id)
    if legacy and legacy.get("allow_sos_to_court_draft") is not None:
        return _flag_to_bool(legacy.get("allow_sos_to_court_draft"))
    return None


def set_sos_to_court_draft_permission(
    matter_id: str,
    allowed: bool | None,
    set_by: str = "operator",
    notes: str = "",
) -> None:
    ops_db.upsert_permission(
        matter_id,
        allow_sos_to_court_draft=allowed,
        set_by=set_by,
        notes=notes,
    )


def list_auto_draft_eligible_names() -> list[str]:
    try:
        rows = list_email_print_permissions(include_closed=False)
    except Exception:
        return []
    return [str(row["canonical_name"]) for row in rows if row.get("allow_email_print") and row.get("canonical_name")]


def _phone_digits(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if digits.startswith("44") and len(digits) == 12:
        return "0" + digits[2:]
    return digits


def _name_token_clause(terms: list[str]) -> tuple[str, list[str]]:
    if len(terms) < 2:
        return "", []
    per_term_sql = []
    params: list[str] = []
    for term in terms:
        term_like = f"%{term}%"
        per_term_sql.append(
            "(p.canonical_name LIKE ? OR m.canonical_name LIKE ?"
            " OR EXISTS (SELECT 1 FROM person_aliases pa"
            "  WHERE pa.person_id = p.person_id AND pa.alias_text LIKE ?)"
            " OR EXISTS (SELECT 1 FROM matter_parties mp"
            "  WHERE mp.matter_id = m.matter_id AND mp.display_name LIKE ?)"
            " OR EXISTS (SELECT 1 FROM matter_children mc"
            "  WHERE mc.matter_id = m.matter_id AND mc.child_name LIKE ?))"
        )
        params.extend([term_like, term_like, term_like, term_like, term_like])
    return " AND ".join(per_term_sql), params


_NAME_PART_KEYS = ("name_first", "name_middle", "name_last")
_CLIENT_ADDRESS_KEYS = (
    "client_address_line1", "client_address_line2", "client_address_line3", "client_address_line4",
    "client_address_postcode",
)


def _fill_derived_client_parts(rows: list[dict]) -> list[dict]:
    try:
        from sql.split_name_address_fields import classify_address, classify_name
    except Exception:
        return rows
    for row in rows:
        if not any(str(row.get(k) or "").strip() for k in _NAME_PART_KEYS):
            parts = classify_name(str(row.get("client_name") or ""))
            if parts:
                row["name_first"], row["name_middle"], row["name_last"] = parts
                row["name_derived"] = "1"
        text = str(row.get("client_address_text") or "").strip()
        if text and not any(str(row.get(k) or "").strip() for k in _CLIENT_ADDRESS_KEYS):
            split = classify_address(text) or {"address_line1": text}
            for i, key in enumerate(_CLIENT_ADDRESS_KEYS[:4], start=1):
                row[key] = split.get(f"address_line{i}", "")
            row["client_address_postcode"] = split.get("address_postcode", "")
            row["client_address_derived"] = "1"
    return rows


def search_clients(query: str, limit: int = 8) -> list[dict]:
    return _search_clients(query, limit)


_NO_QUERY_PATTERN = "%\x01no-query\x01%"
_MATTER_ID_CHUNK = 400


def get_clients_by_matter_ids(matter_ids) -> dict[str, dict]:
    ids = [i for i in dict.fromkeys(str(m or "").strip() for m in matter_ids) if i]
    found: dict[str, dict] = {}
    for start in range(0, len(ids), _MATTER_ID_CHUNK):
        for row in _search_clients("", 0, matter_ids=ids[start : start + _MATTER_ID_CHUNK]):
            found[str(row.get("matter_id"))] = row
    return found


def _search_clients(query: str, limit: int, *, matter_ids: list[str] | None = None) -> list[dict]:
    text = " ".join((query or "").split())
    if matter_ids is None and len(text) < 2:
        return []
    top = max(1, min(int(limit or 8), 20))
    like = f"%{text}%"
    phone = _phone_digits(text)
    phone_like = f"%{phone}%" if phone else like
    name_clause, name_params = _name_token_clause(re.sub(r"[,;]", " ", text).split())
    name_or_sql = f"OR ({name_clause})" if name_clause else ""

    where_sql = f"""(
                p.canonical_name LIKE ?
                OR m.canonical_name LIKE ?
                OR p.email_primary LIKE ?
                OR p.dob_iso LIKE ?
                OR p.phone_digits LIKE ?
                OR m.company_reference LIKE ?
                OR EXISTS (
                    SELECT 1 FROM person_aliases pa
                    WHERE pa.person_id = p.person_id AND pa.alias_text LIKE ?
                )
                OR EXISTS (
                    SELECT 1 FROM matter_parties mp
                    WHERE mp.matter_id = m.matter_id
                      AND (
                        mp.display_name LIKE ?
                        OR mp.email_primary LIKE ?
                        OR mp.dob_iso LIKE ?
                        OR mp.address_text LIKE ?
                        OR mp.phone_digits LIKE ?
                      )
                )
                OR EXISTS (
                    SELECT 1 FROM matter_references mr
                    WHERE mr.matter_id = m.matter_id
                      AND (mr.ref_value LIKE ? OR mr.ref_value_normalised LIKE ?)
                )
                OR EXISTS (
                    SELECT 1 FROM matter_children mc
                    WHERE mc.matter_id = m.matter_id AND mc.child_name LIKE ?
                )
                {name_or_sql}
            )"""
    by_ids = matter_ids is not None
    if by_ids:
        where_sql = "m.matter_id IN (" + ", ".join("?" for _ in matter_ids) + ")"
        like = phone_like = _NO_QUERY_PATTERN

    if _using_sqlite():
        with get_connection() as conn:
            (
                has_closed_at,
                has_closed_by,
                has_closed_notes,
                optional_matter_select,
                optional_live_status_select,
            ) = _sqlite_client_search_schema(conn)
        closed_at_expr = "m.closed_at" if has_closed_at else "NULL"
        closed_by_expr = "m.closed_by" if has_closed_by else "NULL"
        closed_notes_expr = "m.closed_notes" if has_closed_notes else "NULL"
        sql = f"""
            SELECT DISTINCT
                m.matter_id,
                p.canonical_name AS client_name,
                p.email_primary AS client_email,
                m.canonical_name AS matter_name,
                m.client_role,
                m.company_reference,
                (
                    SELECT group_concat(mr.ref_type || ':' || mr.ref_value, ' | ')
                    FROM matter_references mr
                    WHERE mr.matter_id = m.matter_id
                ) AS reference_summary,
                (
                    SELECT mr.ref_value
                    FROM matter_references mr
                    WHERE mr.matter_id = m.matter_id
                    ORDER BY mr.is_primary DESC, mr.reference_id
                    LIMIT 1
                ) AS case_reference,
                m.has_c8,
                m.order_requested_text,
                {optional_matter_select},
                m.live_matter_folder,
                m.legal_aid_tracker_status,
                {closed_at_expr} AS closed_at,
                {closed_by_expr} AS closed_by,
                {closed_notes_expr} AS closed_notes,
                (
                    SELECT group_concat(mp.role || ': ' || mp.display_name, ' | ')
                    FROM matter_parties mp
                    WHERE mp.matter_id = m.matter_id
                      AND COALESCE(mp.display_name, '') <> ''
                ) AS party_summary,
                (
                    SELECT group_concat(mp.role || ': ' || mp.dob_iso, ' | ')
                    FROM matter_parties mp
                    WHERE mp.matter_id = m.matter_id
                      AND COALESCE(mp.dob_iso, '') <> ''
                ) AS party_dob_summary,
                (
                    SELECT group_concat(mp.role || ': ' || mp.display_name, ' | ')
                    FROM matter_parties mp
                    WHERE mp.matter_id = m.matter_id
                      AND (
                        mp.display_name LIKE ?
                        OR mp.email_primary LIKE ?
                        OR mp.dob_iso LIKE ?
                        OR mp.address_text LIKE ?
                        OR mp.phone_digits LIKE ?
                      )
                ) AS matched_party_summary,
                (
                    SELECT group_concat(
                        COALESCE(NULLIF(mp.role, ''), 'Address') ||
                        CASE WHEN COALESCE(mp.address_owner, '') <> '' THEN ' (' || mp.address_owner || ')' ELSE '' END ||
                        ': ' || mp.address_text, ' | ')
                    FROM matter_parties mp
                    WHERE mp.matter_id = m.matter_id
                      AND COALESCE(mp.address_text, '') <> ''
                ) AS address_summary,
                p.dob_iso,
                p.phone_primary,
                p.email_primary,
                p.nino_canonical,
                p.name_first,
                p.name_middle,
                p.name_last,
                p.address_line1 AS client_address_line1,
                p.address_line2 AS client_address_line2,
                p.address_line3 AS client_address_line3,
                p.address_line4 AS client_address_line4,
                p.address_postcode AS client_address_postcode,
                p.address_text AS client_address_text,
                ls.latest_live_status,
                ls.order_status,
                ls.sealed_order_status,
                ls.service_status,
                ls.next_hearing_text,
                ls.awaiting_next_step,
                ls.last_material_email_received,
                ls.last_material_email_subject,
                {optional_live_status_select}
            FROM matters m
            JOIN people p ON p.person_id = m.primary_person_id
            LEFT JOIN matter_live_status ls ON ls.matter_id = m.matter_id
            WHERE {where_sql}
            ORDER BY p.canonical_name, m.canonical_name
            {"" if by_ids else "LIMIT ?"}
        """
        params = (
            like, like, like, like, phone_like,
            *(
                tuple(matter_ids)
                if by_ids
                else (
                    like, like, like, like, phone_like, like, like,
                    like, like, like, like, phone_like, like, like,
                    like,
                    *name_params,
                    top,
                )
            ),
        )
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            cols = [col[0] for col in cursor.description]
            return _fill_derived_client_parts([dict(zip(cols, row)) for row in cursor.fetchall()])

    params = (
        like,
        like,
        like,
        like,
        phone_like,
        *(
            tuple(matter_ids)
            if by_ids
            else (
                like,
                like,
                like,
                like,
                phone_like,
                like,
                like,
                like,
                like,
                like,
                like,
                phone_like,
                like,
                like,
                like,
                *name_params,
            )
        ),
    )
    _require_pyodbc()
    with get_connection() as conn:
        optional_matter_select = _client_search_optional_matter_select(conn)
        optional_live_status_select = _client_search_optional_live_status_select(conn)
        sql = f"""
            SELECT DISTINCT {"" if by_ids else f"TOP ({top})"}
                m.matter_id,
                p.canonical_name AS client_name,
                p.email_primary AS client_email,
                m.canonical_name AS matter_name,
                m.client_role,
                m.company_reference,
                (
                    SELECT STRING_AGG(CONCAT(mr.ref_type, ':', mr.ref_value), ' | ')
                    FROM matter_references mr
                    WHERE mr.matter_id = m.matter_id
                ) AS reference_summary,
                (
                    SELECT TOP (1) mr.ref_value
                    FROM matter_references mr
                    WHERE mr.matter_id = m.matter_id
                    ORDER BY mr.is_primary DESC, mr.reference_id
                ) AS case_reference,
                m.has_c8,
                m.order_requested_text,
                {optional_matter_select},
                m.live_matter_folder,
                m.legal_aid_tracker_status,
                m.closed_at,
                m.closed_by,
                m.closed_notes,
                (
                    SELECT STRING_AGG(CONCAT(mp.role, ': ', mp.display_name), ' | ')
                    FROM matter_parties mp
                    WHERE mp.matter_id = m.matter_id
                      AND NULLIF(mp.display_name, '') IS NOT NULL
                ) AS party_summary,
                (
                    SELECT STRING_AGG(CONCAT(mp.role, ': ', mp.dob_iso), ' | ')
                    FROM matter_parties mp
                    WHERE mp.matter_id = m.matter_id
                      AND NULLIF(mp.dob_iso, '') IS NOT NULL
                ) AS party_dob_summary,
                (
                    SELECT STRING_AGG(CONCAT(mp.role, ': ', mp.display_name), ' | ')
                    FROM matter_parties mp
                    WHERE mp.matter_id = m.matter_id
                      AND (
                        mp.display_name LIKE ?
                        OR mp.email_primary LIKE ?
                        OR mp.dob_iso LIKE ?
                        OR mp.address_text LIKE ?
                        OR mp.phone_digits LIKE ?
                      )
                ) AS matched_party_summary,
                (
                    SELECT STRING_AGG(
                        CONCAT(
                            COALESCE(NULLIF(mp.role, ''), 'Address'),
                            CASE WHEN NULLIF(mp.address_owner, '') IS NOT NULL
                                 THEN CONCAT(' (', mp.address_owner, ')') ELSE '' END,
                            ': ', mp.address_text
                        ), ' | ')
                    FROM matter_parties mp
                    WHERE mp.matter_id = m.matter_id
                      AND NULLIF(mp.address_text, '') IS NOT NULL
                ) AS address_summary,
                p.dob_iso,
                p.phone_primary,
                p.email_primary,
                p.nino_canonical,
                p.name_first,
                p.name_middle,
                p.name_last,
                p.address_line1 AS client_address_line1,
                p.address_line2 AS client_address_line2,
                p.address_line3 AS client_address_line3,
                p.address_line4 AS client_address_line4,
                p.address_postcode AS client_address_postcode,
                p.address_text AS client_address_text,
                ls.latest_live_status,
                ls.order_status,
                ls.sealed_order_status,
                ls.service_status,
                ls.next_hearing_text,
                ls.awaiting_next_step,
                ls.last_material_email_received,
                ls.last_material_email_subject,
                {optional_live_status_select}
            FROM matters m
            JOIN people p ON p.person_id = m.primary_person_id
            LEFT JOIN matter_live_status ls ON ls.matter_id = m.matter_id
            WHERE {where_sql}
            ORDER BY p.canonical_name, m.canonical_name
        """
        cursor = conn.cursor()
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        return _fill_derived_client_parts([dict(zip(cols, row)) for row in cursor.fetchall()])


def list_same_name_people() -> list[dict]:
    sql = """
        SELECT p.person_id AS person_id, p.canonical_name_key AS canonical_name_key,
               p.dob_iso AS dob_iso, m.matter_id AS matter_id,
               m.company_reference AS company_reference, m.created_utc AS created_utc
        FROM people p
        JOIN matters m ON m.primary_person_id = p.person_id
        WHERE p.canonical_name_key IN (
            SELECT p2.canonical_name_key
            FROM people p2
            JOIN matters m2 ON m2.primary_person_id = p2.person_id
            WHERE COALESCE(p2.canonical_name_key, '') <> ''
            GROUP BY p2.canonical_name_key
            HAVING COUNT(DISTINCT p2.person_id) > 1
        )
    """
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        return _rows_as_dicts(cursor)


_LIBRARY_ROOT_PARTS = firm_profile.load_profile().library_root.split("/")
FOLDER_ROOT_MARKERS = tuple(dict.fromkeys((_LIBRARY_ROOT_PARTS[-1], _LIBRARY_ROOT_PARTS[0])))


def _folder_storage_root(path: str) -> str:
    cleaned = str(path or "").replace("\\", "/").strip("/")
    parts = [part for part in cleaned.split("/") if part]
    for marker in FOLDER_ROOT_MARKERS:
        if marker in parts:
            index = parts.index(marker)
            if len(parts) > index + 1:
                return parts[index + 1]
    return parts[0] if parts else ""


def _folder_name_from_path(path: str) -> str:
    cleaned = str(path or "").replace("\\", "/").strip("/")
    return cleaned.rsplit("/", 1)[-1] if cleaned else ""


def ensure_matter_folder_locations_table() -> None:
    ops_db.ensure_database()


def _legacy_matter_folder_locations(
    query: str = "",
    *,
    matter_id: str = "",
    limit: int = 5,
) -> list[dict]:
    top = max(1, min(int(limit or 5), 20))
    text = " ".join(str(query or "").split())
    like = f"%{text}%"
    mid = str(matter_id or "").strip()
    if not mid and len(text) < 2:
        return []
    try:
        with get_connection() as conn:
            if _using_sqlite() and not _sqlite_table_exists(conn, "matter_folder_locations"):
                return []
            if _using_sqlite():
                sql = """
                    SELECT
                        matter_id, client_name, matter_name, storage_root, site_id, drive_id,
                        matter_folder_id, matter_folder_path, matter_folder_name,
                        attendance_folder_id, attendance_folder_name, source, last_verified_utc
                    FROM matter_folder_locations
                    WHERE
                        (? <> '' AND matter_id = ?)
                        OR (? <> '' AND (
                            client_name LIKE ?
                            OR matter_name LIKE ?
                            OR matter_folder_name LIKE ?
                            OR matter_folder_path LIKE ?
                        ))
                    ORDER BY
                        CASE WHEN matter_id = ? THEN 0 ELSE 1 END,
                        last_verified_utc DESC
                    LIMIT ?
                """
                params = (mid, mid, text, like, like, like, like, mid, top)
            else:
                sql = f"""
                    SELECT TOP ({top})
                        matter_id, client_name, matter_name, storage_root, site_id, drive_id,
                        matter_folder_id, matter_folder_path, matter_folder_name,
                        attendance_folder_id, attendance_folder_name, source, last_verified_utc
                    FROM dbo.matter_folder_locations
                    WHERE
                        (? <> '' AND matter_id = ?)
                        OR (? <> '' AND (
                            client_name LIKE ?
                            OR matter_name LIKE ?
                            OR matter_folder_name LIKE ?
                            OR matter_folder_path LIKE ?
                        ))
                    ORDER BY
                        CASE WHEN matter_id = ? THEN 0 ELSE 1 END,
                        last_verified_utc DESC
                """
                params = (mid, mid, text, like, like, like, like, mid)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            cols = [col[0] for col in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
    except Exception:
        return []


def seed_matter_folder_locations_from_matters() -> int:
    ensure_matter_folder_locations_table()
    inserted = 0
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT m.matter_id, m.live_matter_folder
                FROM matters m
                WHERE COALESCE(m.live_matter_folder, '') <> ''
                """
            )
            cols = [col[0] for col in cursor.description]
            rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    except Exception:
        rows = []

    drive_id = ""
    try:
        import graph_files

        drive_id = graph_files.shared_drive_id(graph_files.token())
    except Exception:
        drive_id = ""

    for row in rows:
        before = ops_db.find_matter_onedrive_roots(matter_id=str(row.get("matter_id") or ""), limit=1)
        ops_db.upsert_matter_onedrive_root(
            matter_id=str(row.get("matter_id") or ""),
            drive_id=drive_id,
            folder_path=str(row.get("live_matter_folder") or ""),
            source="matters.live_matter_folder",
        )
        after = ops_db.find_matter_onedrive_roots(matter_id=str(row.get("matter_id") or ""), limit=1)
        if after and not before:
            inserted += 1
    return inserted


def seed_matter_folder_location(matter_id: str) -> str:
    mid = str(matter_id or "").strip()
    if not mid:
        return ""
    try:
        ensure_matter_folder_locations_table()
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT live_matter_folder FROM matters WHERE matter_id = ?", (mid,))
            row = cursor.fetchone()
    except Exception:
        return ""
    recorded = str((row[0] if row else "") or "").strip()
    if not recorded:
        return ""
    drive_id = ""
    try:
        import graph_files

        drive_id = graph_files.shared_drive_id(graph_files.token())
    except Exception:
        drive_id = ""
    ops_db.upsert_matter_onedrive_root(
        matter_id=mid,
        drive_id=drive_id,
        folder_path=recorded,
        source="matters.live_matter_folder",
    )
    return recorded


def find_matter_folder_locations(
    query: str = "",
    *,
    matter_id: str = "",
    limit: int = 5,
) -> list[dict]:
    ensure_matter_folder_locations_table()
    rows = ops_db.find_matter_onedrive_roots(query, matter_id=matter_id, limit=limit)
    if rows:
        return rows
    if os.getenv(_RETIRED_FOLDER_LOCATIONS_ENV, "").strip() != "1":
        return []
    return _legacy_matter_folder_locations(query, matter_id=matter_id, limit=limit)


def upsert_matter_folder_location(
    *,
    matter_id: str,
    client_name: str = "",
    matter_name: str = "",
    matter_folder_path: str = "",
    matter_folder_name: str = "",
    matter_folder_id: str = "",
    attendance_folder_id: str = "",
    attendance_folder_name: str = "",
    drive_id: str = "",
    site_id: str = "",
    source: str = "caseforge-chat",
) -> None:
    mid = str(matter_id or "").strip()
    if not mid:
        return
    ensure_matter_folder_locations_table()
    path = str(matter_folder_path or "").strip()
    ops_db.upsert_matter_onedrive_root(
        matter_id=mid,
        folder_item_id=str(matter_folder_id or "").strip(),
        drive_id=str(drive_id or "").strip(),
        folder_path=path,
        root_name=_folder_storage_root(path),
        source=str(source or "caseforge-chat").strip(),
    )


def close_matter(matter_id: str, closed_by: str = "operator", notes: str = "", closed_at: str = "") -> None:
    _require_pyodbc()
    with get_connection() as conn:
        if _using_sqlite():
            _ensure_sqlite_matter_closed_columns(conn)
        cursor = conn.cursor()
        if closed_at:
            cursor.execute(
                """
                UPDATE dbo.matters
                SET closed_at = ?, closed_by = ?, closed_notes = ?
                WHERE matter_id = ?
                """,
                (closed_at, closed_by, notes or None, matter_id),
            )
        else:
            cursor.execute(
                """
                UPDATE dbo.matters
                SET closed_at = SYSUTCDATETIME(), closed_by = ?, closed_notes = ?
                WHERE matter_id = ?
                """,
                (closed_by, notes or None, matter_id),
            )


def reopen_matter(matter_id: str, reopened_by: str = "operator", notes: str = "") -> None:
    _require_pyodbc()
    with get_connection() as conn:
        if _using_sqlite():
            _ensure_sqlite_matter_closed_columns(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE dbo.matters
            SET closed_at = NULL, closed_by = NULL, closed_notes = ?
            WHERE matter_id = ?
            """,
            (notes or f"Reopened by {reopened_by}", matter_id),
        )


def is_matter_closed(matter_id: str) -> bool:
    _require_pyodbc()
    with get_connection() as conn:
        if _using_sqlite():
            _ensure_sqlite_matter_closed_columns(conn)
        if _using_sqlite() and not _sqlite_column_exists(conn, "matters", "closed_at"):
            return False
        cursor = conn.cursor()
        cursor.execute(
            "SELECT closed_at FROM dbo.matters WHERE matter_id = ?", (matter_id,)
        )
        row = cursor.fetchone()
    if row is None:
        return False
    return row[0] is not None


def list_closed_matters() -> list[dict]:
    _require_pyodbc()
    with get_connection() as conn:
        if _using_sqlite():
            _ensure_sqlite_matter_closed_columns(conn)
        if _using_sqlite() and not _sqlite_column_exists(conn, "matters", "closed_at"):
            return []
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT matter_id, canonical_name, closed_at, closed_by, closed_notes
            FROM dbo.matters
            WHERE closed_at IS NOT NULL
            ORDER BY closed_at DESC
            """
        )
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def list_closed_matter_ids_page(limit: int, offset: int = 0) -> tuple[list[str], int]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    _require_pyodbc()
    with get_connection() as conn:
        if _using_sqlite():
            _ensure_sqlite_matter_closed_columns(conn)
            if not _sqlite_column_exists(conn, "matters", "closed_at"):
                return [], 0
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM dbo.matters WHERE closed_at IS NOT NULL")
        total = int(cursor.fetchone()[0])
        if _using_sqlite():
            cursor.execute(
                "SELECT matter_id FROM dbo.matters WHERE closed_at IS NOT NULL "
                "ORDER BY closed_at DESC, matter_id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        else:
            cursor.execute(
                "SELECT matter_id FROM dbo.matters WHERE closed_at IS NOT NULL "
                "ORDER BY closed_at DESC, matter_id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
                (offset, limit),
            )
        return [str(row[0]) for row in cursor.fetchall()], total


EDITABLE_FIELDS: dict[str, tuple[str, str]] = {
    "name_first": ("people", "name_first"),
    "name_middle": ("people", "name_middle"),
    "name_last": ("people", "name_last"),
    "client_canonical_name": ("people", "canonical_name"),
    "dob_iso": ("people", "dob_iso"),
    "sex": ("people", "sex"),
    "sex_other": ("people", "sex_other"),
    "nino_canonical": ("people", "nino_canonical"),
    "phone_primary": ("people", "phone_primary"),
    "email_primary": ("people", "email_primary"),
    "address_line1": ("people", "address_line1"),
    "address_line2": ("people", "address_line2"),
    "address_line3": ("people", "address_line3"),
    "address_line4": ("people", "address_line4"),
    "address_postcode": ("people", "address_postcode"),
    "matter_name": ("matters", "canonical_name"),
    "client_role": ("matters", "client_role"),
    "company_reference": ("matters", "company_reference"),
    "order_requested_text": ("matters", "order_requested_text"),
    "legal_aid_tracker_status": ("matters", "legal_aid_tracker_status"),
    "has_c8": ("matters", "has_c8"),
    "c8_phone": ("matters", "c8_phone"),
    "c8_email": ("matters", "c8_email"),
    "c8_address": ("matters", "c8_address"),
    "tracker_notes": ("matters", "tracker_notes"),
    "order_type_tags": ("matters", "order_type_tags"),
    "children_summary": ("matters", "children_summary"),
    "relationship_start": ("matters", "relationship_start"),
    "relationship_end": ("matters", "relationship_end"),
    "marriage_date": ("matters", "marriage_date"),
    "divorce_date": ("matters", "divorce_date"),
    "lived_together": ("matters", "lived_together"),
    "married": ("matters", "married"),
    "bail_conditions": ("matters", "bail_conditions"),
    "bail_end_date": ("matters", "bail_end_date"),
    "crime_refs": ("matters", "crime_refs"),
}

BOOLEAN_EDITABLE_FIELDS: frozenset[str] = frozenset({"has_c8", "c8_phone", "c8_email", "c8_address"})

C8_FIELD_FLAGS: tuple[str, ...] = ("c8_phone", "c8_email", "c8_address")

NOT_NULL_EDITABLE_FIELDS: frozenset[str] = frozenset({
    "client_canonical_name",
    "legal_aid_tracker_status",
}) | BOOLEAN_EDITABLE_FIELDS

LONG_TEXT_EDITABLE_FIELDS: frozenset[str] = frozenset({"tracker_notes", "children_summary"})

LONG_TEXT_MAX_LENGTH = 20000


def get_primary_person_id(matter_id: str) -> str | None:
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT primary_person_id FROM dbo.matters WHERE matter_id = ?",
            (matter_id,),
        )
        row = cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def get_client_by_matter_id(matter_id: str) -> dict | None:
    matter_id = str(matter_id or "").strip()
    if not matter_id:
        return None
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT canonical_name FROM dbo.matters WHERE matter_id = ?", (matter_id,))
        row = cursor.fetchone()
    if row is None or not row[0]:
        return None
    import agwu

    for candidate in [m.row for m in agwu.resolve_client(str(row[0]), limit=5, caller="clientdb_sql.get_client_by_matter_id").matches]:
        if str(candidate.get("matter_id") or "") == matter_id:
            return candidate
    return None


def _email_lookup_forms(addresses) -> tuple[list[str], list[str]]:
    from recipient_identity import _DOTLESS_DOMAINS, canonical_address

    exact: set[str] = set()
    dotless: set[str] = set()
    for address in addresses:
        clean = str(address or "").strip().lower()
        if "@" not in clean:
            continue
        canonical = canonical_address(clean)
        exact.update((clean, canonical))
        local, domain = canonical.rsplit("@", 1)
        if domain in _DOTLESS_DOMAINS:
            dotless.update(f"{local}@{d.replace('.', '')}" for d in _DOTLESS_DOMAINS)
    return sorted(exact), sorted(dotless)


def find_client_email_records(addresses) -> list[dict]:
    exact, dotless = _email_lookup_forms(addresses)
    if not exact:
        return []

    def _match(column: str) -> tuple[str, list[str]]:
        clause = f"lower(trim({column})) IN ({', '.join('?' for _ in exact)})"
        params = list(exact)
        if dotless:
            clause += f" OR replace(lower(trim({column})), '.', '') IN ({', '.join('?' for _ in dotless)})"
            params += dotless
        return f"({clause})", params

    people_match, people_params = _match("p.email_primary")
    party_match, party_params = _match("mp.email_primary")
    sql = f"""
        SELECT m.matter_id AS matter_id, p.person_id AS person_id,
               p.canonical_name AS owner_name, p.email_primary AS email
        FROM people p
        LEFT JOIN matters m ON m.primary_person_id = p.person_id
        WHERE {people_match}
        UNION ALL
        SELECT mp.matter_id AS matter_id, m.primary_person_id AS person_id,
               mp.display_name AS owner_name, mp.email_primary AS email
        FROM matter_parties mp
        JOIN matters m ON m.matter_id = mp.matter_id
        WHERE lower(trim(COALESCE(mp.role, ''))) = lower(trim(COALESCE(NULLIF(m.client_role, ''), 'Applicant')))
          AND {party_match}
    """
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, tuple(people_params + party_params))
        return _rows_as_dicts(cursor)


def client_email_owner_lookup(addresses):
    from recipient_identity import OwnerLookup

    try:
        return OwnerLookup.from_rows(find_client_email_records(addresses))
    except Exception as exc:
        return OwnerLookup(error=f"the client database lookup failed: {type(exc).__name__}")


def _matter_exists(matter_id: str) -> bool:
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM dbo.matters WHERE matter_id = ?", (matter_id,))
        return cursor.fetchone() is not None


def _editable_row_id(matter_id: str, table: str) -> str | None:
    if table == "matters":
        return matter_id if _matter_exists(matter_id) else None
    return get_primary_person_id(matter_id)


def get_editable_field(matter_id: str, field_name: str) -> str | None:
    if field_name not in EDITABLE_FIELDS:
        raise ValueError(f"field_name {field_name!r} is not editable")
    table, column = EDITABLE_FIELDS[field_name]
    row_id = _editable_row_id(matter_id, table)
    if not row_id:
        return None
    id_column = "matter_id" if table == "matters" else "person_id"
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {column} FROM dbo.{table} WHERE {id_column} = ?",
            (row_id,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return None if row[0] is None else str(row[0])


COMPANY_REFERENCE_PLACEHOLDERS: frozenset[str] = frozenset({"n/a", "na", "unknown", "tbc", "withheld"})


class CompanyReferenceHeldError(ValueError):
    pass


def company_reference_holders(company_reference: str | None, exclude_matter_id: str | None = None) -> list[str]:
    norm = str(company_reference or "").strip().upper()
    if not norm or norm.lower() in COMPANY_REFERENCE_PLACEHOLDERS:
        return []
    _require_pyodbc()
    exclude = str(exclude_matter_id) if exclude_matter_id is not None else ""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT matter_id FROM dbo.matters WHERE upper(trim(company_reference)) = ? AND CAST(matter_id AS TEXT) <> ?",
            (norm, exclude),
        )
        holders = {str(row[0]) for row in cursor.fetchall()}
        cursor.execute(
            "SELECT matter_id FROM dbo.matter_references WHERE ref_type IN ('company_ref', 'company') "
            "AND upper(trim(ref_value_normalised)) = ? AND CAST(matter_id AS TEXT) <> ?",
            (norm.replace(" ", ""), exclude),
        )
        holders |= {str(row[0]) for row in cursor.fetchall()}
    return sorted(holders, key=lambda m: (len(m), m))


def refuse_company_reference_held_elsewhere(matter_id: str, company_reference: str | None) -> None:
    holders = company_reference_holders(company_reference, matter_id)
    if holders:
        raise CompanyReferenceHeldError(
            f"That company reference is already held by matter {', '.join(holders)}. "
            "A company reference belongs to one matter; it has not been changed."
        )


def update_editable_field(matter_id: str, field_name: str, new_value: str | None) -> None:
    if field_name not in EDITABLE_FIELDS:
        raise ValueError(f"field_name {field_name!r} is not editable")
    table, column = EDITABLE_FIELDS[field_name]
    row_id = _editable_row_id(matter_id, table)
    if not row_id:
        raise ValueError(f"matter {matter_id!r} has no {table} row to update")
    if field_name == "company_reference":
        refuse_company_reference_held_elsewhere(matter_id, new_value)
    id_column = "matter_id" if table == "matters" else "person_id"
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE dbo.{table} SET {column} = ? WHERE {id_column} = ?",
            (new_value, row_id),
        )
        if table == "people" and column == "phone_primary":
            cursor.execute("UPDATE dbo.people SET phone_digits = ? WHERE person_id = ?", (_phone_digits(new_value or "") or None, row_id))
        if table == "people" and column in PARTY_ADDRESS_PARTS:
            _recompose_person_address(cursor, row_id)


def _recompose_person_address(cursor, person_id) -> None:
    cursor.execute(
        "SELECT address_line1, address_line2, address_line3, address_line4, address_postcode FROM dbo.people WHERE person_id = ?",
        (person_id,),
    )
    row = cursor.fetchone()
    if not row:
        return
    parts = dict(zip(PARTY_ADDRESS_PARTS, tuple(row)))
    if not any(str(parts.get(k) or "").strip() for k in PARTY_ADDRESS_PARTS[:4]):
        return
    cursor.execute("UPDATE dbo.people SET address_text = ? WHERE person_id = ?", (_compose_address(parts), person_id))


COURT_REF_TYPES: tuple[str, ...] = ("court_family", "court_children", "court_ref")
MAX_COURT_REFERENCES = 5


def get_court_references(matter_id: str) -> list[str]:
    _require_pyodbc()
    marks = ", ".join("?" for _ in COURT_REF_TYPES)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT ref_value FROM dbo.matter_references WHERE matter_id = ? AND ref_type IN ({marks}) ORDER BY reference_id",
            (matter_id, *COURT_REF_TYPES),
        )
        return [str(row[0]).strip() for row in cursor.fetchall() if str(row[0] or "").strip()]


def set_court_references(matter_id: str, values: list[str]) -> list[str]:
    wanted: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = " ".join(str(raw or "").split())
        norm = value.upper().replace(" ", "")
        if value and norm not in seen:
            seen.add(norm)
            wanted.append(value)
    if len(wanted) > MAX_COURT_REFERENCES:
        raise ValueError(f"at most {MAX_COURT_REFERENCES} court references")
    if not _matter_exists(matter_id):
        raise ValueError(f"matter {matter_id!r} not found")
    _require_pyodbc()
    marks = ", ".join("?" for _ in COURT_REF_TYPES)
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT reference_id, ref_value FROM dbo.matter_references WHERE matter_id = ? AND ref_type IN ({marks})",
            (matter_id, *COURT_REF_TYPES),
        )
        held = {str(r[1]).upper().replace(" ", ""): r[0] for r in cursor.fetchall()}
        keep = {value.upper().replace(" ", "") for value in wanted}
        for norm, reference_id in held.items():
            if norm not in keep:
                cursor.execute("DELETE FROM dbo.matter_references WHERE reference_id = ?", (reference_id,))
        for value in wanted:
            norm = value.upper().replace(" ", "")
            if norm in held:
                continue
            cursor.execute(
                """
                INSERT INTO dbo.matter_references (
                    matter_id, ref_type, ref_value, ref_value_normalised, source, notes,
                    is_primary, created_utc, updated_utc
                ) VALUES (?, 'court_family', ?, ?, 'client-viewer edit', NULL, 0, ?, ?)
                """,
                (matter_id, value, norm, now, now),
            )
    return wanted


def mirror_company_reference(matter_id: str, value: str | None) -> None:
    _require_pyodbc()
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT reference_id FROM dbo.matter_references WHERE matter_id = ? AND ref_type = 'company_ref' "
            "ORDER BY is_primary DESC, reference_id",
            (matter_id,),
        )
        rows = [r[0] for r in cursor.fetchall()]
        if not value:
            for reference_id in rows:
                cursor.execute("DELETE FROM dbo.matter_references WHERE reference_id = ?", (reference_id,))
            return
        norm = value.upper().replace(" ", "")
        if rows:
            cursor.execute(
                "UPDATE dbo.matter_references SET ref_value = ?, ref_value_normalised = ?, is_primary = 1, updated_utc = ? "
                "WHERE reference_id = ?",
                (value, norm, now, rows[0]),
            )
            return
        cursor.execute(
            """
            INSERT INTO dbo.matter_references (
                matter_id, ref_type, ref_value, ref_value_normalised, source, notes,
                is_primary, created_utc, updated_utc
            ) VALUES (?, 'company_ref', ?, ?, 'client-viewer edit', NULL, 1, ?, ?)
            """,
            (matter_id, value, norm, now, now),
        )


PARTY_NAME_PARTS: tuple[str, ...] = ("name_first", "name_middle", "name_last")
PARTY_ADDRESS_PARTS: tuple[str, ...] = (
    "address_line1", "address_line2", "address_line3", "address_line4", "address_postcode",
)
PARTY_WORK_ADDRESS_PARTS: tuple[str, ...] = (
    "work_address_line1", "work_address_line2", "work_address_line3", "work_address_line4",
    "work_address_postcode",
)
PARTY_EDITABLE_FIELDS: frozenset[str] = frozenset({
    "role", "display_name", "aka_name", "dob_iso", "sex", "sex_other",
    "address_text", "address_owner",
    "phone_primary", "phone_owner",
    "email_primary", "email_owner",
}) | frozenset(PARTY_NAME_PARTS) | frozenset(PARTY_ADDRESS_PARTS) | frozenset(PARTY_WORK_ADDRESS_PARTS)

_PARTY_NOT_NULL: frozenset[str] = frozenset({
    "role", "display_name", "display_name_key", "phone_digits_key",
    "email_primary_key", "created_utc", "updated_utc",
}) | frozenset(PARTY_WORK_ADDRESS_PARTS)

_PARTY_SELECT = (
    "SELECT matter_party_id AS party_id, matter_id, role, display_name, "
    "name_first, name_middle, name_last, aka_name, dob_iso, sex, sex_other, "
    "address_text, address_line1, address_line2, address_line3, address_line4, address_postcode, "
    "address_owner, work_address_line1, work_address_line2, work_address_line3, work_address_line4, "
    "work_address_postcode, phone_primary, phone_digits, phone_owner, email_primary, email_owner "
    "FROM dbo.matter_parties"
)


def _rows_as_dicts(cursor) -> list[dict]:
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _compose_name(parts: dict) -> str:
    return " ".join(str(parts.get(k) or "").strip() for k in PARTY_NAME_PARTS if str(parts.get(k) or "").strip())


def _compose_address(parts: dict) -> str:
    return ", ".join(str(parts.get(k) or "").strip() for k in PARTY_ADDRESS_PARTS if str(parts.get(k) or "").strip())


def _party_derived_columns(fields: dict) -> dict:
    import re

    derived: dict = {}
    if "display_name" in fields:
        derived["display_name_key"] = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", fields["display_name"].lower())).strip()
    if "phone_primary" in fields:
        digits = re.sub(r"\D+", "", fields["phone_primary"] or "")
        derived["phone_digits"] = digits or None
        derived["phone_digits_key"] = digits
    if "email_primary" in fields:
        derived["email_primary_key"] = (fields["email_primary"] or "").strip().lower()
    return derived


def _normalise_party_address_fields(row: dict, existing: dict | None) -> None:
    from documents.address_utils import normalise_address_text

    for key in ("address_text", *PARTY_ADDRESS_PARTS[:4]):
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        cleaned = normalise_address_text(value)
        if cleaned:
            row[key] = cleaned
        elif str((existing or {}).get(key) or "").strip():
            del row[key]
        else:
            row[key] = ""


def _party_row_for_write(fields: dict, existing: dict | None) -> dict:
    row = {k: (v.strip() if isinstance(v, str) else v) for k, v in fields.items()}
    _normalise_party_address_fields(row, existing)
    merged = {**(existing or {}), **row}
    if any(k in row for k in PARTY_NAME_PARTS):
        name = _compose_name(merged)
        if not name:
            raise ValueError("a name is required")
        row["display_name"] = name
    if any(k in row for k in PARTY_ADDRESS_PARTS):
        row["address_text"] = _compose_address(merged)
    for required in ("role", "display_name"):
        if required in row and not str(row[required] or "").strip():
            raise ValueError(f"{required} cannot be blank")
    if "sex" in row or "sex_other" in row:
        import field_shapes

        row["sex"], row["sex_other"] = field_shapes.clean_sex_pair(merged.get("sex"), merged.get("sex_other"))
    row.update(_party_derived_columns(row))
    for column, value in list(row.items()):
        if column not in _PARTY_NOT_NULL and value == "":
            row[column] = None
    return row


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def list_parties(matter_id: str) -> list[dict]:
    matter = str(matter_id or "").strip()
    if not matter:
        return []
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_PARTY_SELECT + " WHERE matter_id = ? ORDER BY matter_party_id", (matter,))
        return _rows_as_dicts(cursor)


def list_parties_with_address(matter_id: str) -> list[dict]:
    return [row for row in list_parties(matter_id) if str(row.get("address_text") or "").strip()]


def client_postal_address(matter_id: str) -> dict | None:
    matter = str(matter_id or "").strip()
    if not matter:
        return None
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT p.canonical_name AS display_name, p.address_line1, p.address_line2, p.address_line3, "
            "p.address_line4, p.address_postcode FROM matters m "
            "JOIN people p ON p.person_id = m.primary_person_id WHERE m.matter_id = ?",
            (matter,),
        )
        rows = _rows_as_dicts(cursor)
    return rows[0] if rows else None


def add_party(matter_id: str, fields: dict) -> dict:
    matter = str(matter_id or "").strip()
    if not matter:
        raise ValueError("matter_id is required")
    unknown = set(fields) - PARTY_EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"unknown party field(s) {sorted(unknown)!r}; expected one of {sorted(PARTY_EDITABLE_FIELDS)}")
    row = _party_row_for_write(fields, None)
    if not str(row.get("role") or "").strip() or not str(row.get("display_name") or "").strip():
        raise ValueError("role and display_name are both required")
    row.setdefault("phone_digits_key", "")
    row.setdefault("email_primary_key", "")
    now = _utc_now_iso()
    row["created_utc"] = now
    row["updated_utc"] = now
    columns = list(row)
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO dbo.matter_parties (matter_id, {', '.join(columns)}) "
            f"VALUES (?, {', '.join('?' for _ in columns)})",
            (matter, *[row[c] for c in columns]),
        )
        cursor.execute(_PARTY_SELECT + " WHERE matter_id = ? ORDER BY matter_party_id DESC", (matter,))
        found = cursor.fetchone()
        result_columns = [c[0] for c in cursor.description]
    if found is None:
        raise ValueError("party insert did not return a row")
    return dict(zip(result_columns, found))


def update_party(party_id: str, fields: dict) -> dict:
    pid = str(party_id or "").strip()
    if not pid:
        raise ValueError("party_id is required")
    unknown = set(fields) - PARTY_EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"unknown party field(s) {sorted(unknown)!r}; expected one of {sorted(PARTY_EDITABLE_FIELDS)}")
    if not fields:
        raise ValueError("at least one field is required")
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_PARTY_SELECT + " WHERE matter_party_id = ?", (pid,))
        current = _rows_as_dicts(cursor)
        if not current:
            raise ValueError(f"no matter_parties row for party_id {pid!r}")
        row = _party_row_for_write(fields, current[0])
        row["updated_utc"] = _utc_now_iso()
        columns = list(row)
        cursor.execute(
            f"UPDATE dbo.matter_parties SET {', '.join(f'{c} = ?' for c in columns)} "
            f"WHERE matter_party_id = ?",
            (*[row[c] for c in columns], pid),
        )
        cursor.execute(_PARTY_SELECT + " WHERE matter_party_id = ?", (pid,))
        found = _rows_as_dicts(cursor)
    return found[0]


def delete_party(party_id: str) -> None:
    pid = str(party_id or "").strip()
    if not pid:
        raise ValueError("party_id is required")
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dbo.matter_parties WHERE matter_party_id = ?", (pid,))


CHILD_NAME_PARTS: tuple[str, ...] = ("name_first", "name_middle", "name_last")
CHILD_EDITABLE_FIELDS: frozenset[str] = frozenset({
    "dob_iso", "gender", "parental_responsibility", "lives_with", "notes",
}) | frozenset(CHILD_NAME_PARTS)

_CHILD_SELECT = (
    "SELECT child_id, matter_id, child_name, name_first, name_middle, name_last, "
    "dob_iso, gender, parental_responsibility, lives_with, notes FROM dbo.matter_children"
)


_PR_MARKER_NAME_RE = re.compile(r"^\s*p\.?\s?r\.?(?:\s|$)", re.IGNORECASE)


def _child_row_for_write(fields: dict, existing: dict | None) -> dict:
    row = {k: (v.strip() if isinstance(v, str) else v) for k, v in fields.items()}
    merged = {**(existing or {}), **row}
    if any(k in row for k in CHILD_NAME_PARTS):
        name = _compose_name(merged)
        if not name:
            raise ValueError("a name is required")
        row["child_name"] = name
    if _PR_MARKER_NAME_RE.match(str(row.get("child_name") or "")):
        raise ValueError("a child cannot be named PR: that is parental responsibility, a flag on a child")
    for column, value in list(row.items()):
        if value == "":
            row[column] = None
    return row


def list_children(matter_id: str) -> list[dict]:
    matter = str(matter_id or "").strip()
    if not matter:
        return []
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_CHILD_SELECT + " WHERE matter_id = ? ORDER BY child_id", (matter,))
        return _rows_as_dicts(cursor)


def add_child(matter_id: str, fields: dict) -> dict:
    matter = str(matter_id or "").strip()
    if not matter:
        raise ValueError("matter_id is required")
    unknown = set(fields) - CHILD_EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"unknown child field(s) {sorted(unknown)!r}; expected one of {sorted(CHILD_EDITABLE_FIELDS)}")
    row = _child_row_for_write(fields, None)
    if not row.get("child_name"):
        raise ValueError("a name is required")
    columns = list(row)
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO dbo.matter_children (matter_id, {', '.join(columns)}, source, created_utc, updated_utc) "
            f"VALUES (?, {', '.join('?' for _ in columns)}, 'Client Viewer', SYSUTCDATETIME(), SYSUTCDATETIME())",
            (matter, *[row[c] for c in columns]),
        )
        cursor.execute(_CHILD_SELECT + " WHERE matter_id = ? ORDER BY child_id DESC", (matter,))
        found = _rows_as_dicts(cursor)
    if not found:
        raise ValueError("child insert did not return a row")
    return found[0]


def update_child(child_id: str, fields: dict) -> dict:
    cid = str(child_id or "").strip()
    if not cid:
        raise ValueError("child_id is required")
    unknown = set(fields) - CHILD_EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"unknown child field(s) {sorted(unknown)!r}; expected one of {sorted(CHILD_EDITABLE_FIELDS)}")
    if not fields:
        raise ValueError("at least one field is required")
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(_CHILD_SELECT + " WHERE child_id = ?", (cid,))
        current = _rows_as_dicts(cursor)
        if not current:
            raise ValueError(f"no matter_children row for child_id {cid!r}")
        row = _child_row_for_write(fields, current[0])
        columns = list(row)
        cursor.execute(
            f"UPDATE dbo.matter_children SET {', '.join(f'{c} = ?' for c in columns)}, updated_utc = SYSUTCDATETIME() "
            f"WHERE child_id = ?",
            (*[row[c] for c in columns], cid),
        )
        cursor.execute(_CHILD_SELECT + " WHERE child_id = ?", (cid,))
        found = _rows_as_dicts(cursor)
    return found[0]


def delete_child(child_id: str) -> None:
    cid = str(child_id or "").strip()
    if not cid:
        raise ValueError("child_id is required")
    _require_pyodbc()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dbo.matter_children WHERE child_id = ?", (cid,))


def backfill_matter_activity_status(cutoff_year: int = 2025) -> dict:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    matter_id,
                    referral_sent_at,
                    source_email_sent_at,
                    created_utc,
                    live_matter_folder
                FROM matters
                """
            )
            cols = [col[0] for col in cursor.description]
            rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    except Exception:
        rows = []
    result = ops_db.backfill_activity_status(rows, cutoff_year=cutoff_year)
    result["rows_seen"] = len(rows)
    result["ops_db"] = str(ops_db.resolve_ops_db_path())
    return result


_LIVE_STATUS_WRITABLE = (
    "latest_live_status",
    "order_status",
    "sealed_order_status",
    "service_status",
    "next_hearing_text",
    "awaiting_next_step",
    "last_client_chase",
    "last_material_email_received",
    "last_material_email_subject",
    "draft_order_status",
    "waiting_for_sealed_order",
)


def _ensure_sqlite_matter_live_status(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS matter_live_status (
            matter_id INTEGER PRIMARY KEY,
            latest_live_status TEXT,
            order_status TEXT,
            sealed_order_status TEXT,
            service_status TEXT,
            next_hearing_text TEXT,
            awaiting_next_step TEXT,
            last_client_chase TEXT,
            last_material_email_received TEXT,
            last_material_email_subject TEXT,
            status_changed_at TEXT,
            created_utc TEXT,
            updated_utc TEXT,
            draft_order_status TEXT,
            waiting_for_sealed_order INTEGER
        )
        """
    )


def upsert_matter_live_status(matter_id, **fields) -> dict:
    if matter_id is None or str(matter_id).strip() == "":
        raise ValueError("matter_id is required")
    unknown = set(fields) - set(_LIVE_STATUS_WRITABLE)
    if unknown:
        raise ValueError(f"unknown live-status fields: {sorted(unknown)}")
    fields = {k: v for k, v in fields.items() if v is not None}
    if "waiting_for_sealed_order" in fields:
        waiting = fields["waiting_for_sealed_order"]
        fields["waiting_for_sealed_order"] = (
            waiting.strip().lower() in {"1", "true", "t", "yes", "y"} if isinstance(waiting, str) else bool(waiting)
        )

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    with get_connection() as conn:
        if _using_sqlite():
            _ensure_sqlite_matter_live_status(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT matter_id FROM matter_live_status WHERE matter_id = ?",
            (matter_id,),
        )
        exists = cur.fetchone() is not None

        set_fields = dict(fields)
        set_fields["updated_utc"] = now_iso
        if fields:
            set_fields["status_changed_at"] = now_iso

        if exists:
            assignments = ", ".join(f"{col} = ?" for col in set_fields)
            params = list(set_fields.values()) + [matter_id]
            conn.cursor().execute(
                f"UPDATE matter_live_status SET {assignments} WHERE matter_id = ?",
                tuple(params),
            )
            action = "update"
        else:
            set_fields.setdefault("status_changed_at", now_iso)
            set_fields["created_utc"] = now_iso
            set_fields.setdefault("waiting_for_sealed_order", False)
            cols = ["matter_id"] + list(set_fields)
            placeholders = ", ".join(["?"] * len(cols))
            params = [matter_id] + list(set_fields.values())
            conn.cursor().execute(
                f"INSERT INTO matter_live_status ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(params),
            )
            action = "insert"

    _record_runtime_live_status_write(matter_id, sorted(fields))
    return {"matter_id": matter_id, "action": action, "fields": sorted(fields)}


def _record_runtime_live_status_write(matter_id, fields: list) -> None:
    try:
        import telemetry_sqlite

        telemetry_sqlite.record_runtime_event(
            {
                "event_name": "matter_live_status_write",
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "runtime_label": os.environ.get("CASEFORGE_RUNTIME_LABEL", ""),
                "files_read": [],
                "files_written": ["caseforge-clientdb:matter_live_status"],
                "command": f"matter {matter_id}: {','.join(fields) or 'touch'}",
            }
        )
    except Exception:
        pass


def list_open_obligation_rows() -> list[dict]:
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    ls.matter_id        AS matter_id,
                    p.canonical_name    AS client,
                    m.has_c8            AS has_c8,
                    m.order_requested_text AS order_type,
                    (
                        SELECT mr.ref_value FROM matter_references mr
                        WHERE mr.matter_id = m.matter_id
                        ORDER BY mr.is_primary DESC, mr.reference_id
                        LIMIT 1
                    ) AS matter_ref,
                    ls.order_status, ls.sealed_order_status, ls.service_status,
                    ls.next_hearing_text, ls.awaiting_next_step, ls.draft_order_status,
                    ls.last_material_email_received, ls.status_changed_at
                FROM matter_live_status ls
                JOIN matters m ON m.matter_id = ls.matter_id
                LEFT JOIN people p ON p.person_id = m.primary_person_id
                WHERE COALESCE(ls.awaiting_next_step, '') <> ''
                """
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception:
        return []


def _ensure_instance_handoff_notes_table(conn) -> None:
    if _using_sqlite():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instance_handoff_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_utc TEXT NOT NULL,
                source_host TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                acknowledged_by TEXT,
                acknowledged_utc TEXT
            )
            """
        )
        return
    cursor = conn.cursor()
    if _using_postgres():
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS instance_handoff_notes (
                id SERIAL PRIMARY KEY,
                created_utc TIMESTAMP NOT NULL,
                source_host TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                acknowledged_by TEXT NULL,
                acknowledged_utc TIMESTAMP NULL
            )
            """
        )
        return
    cursor.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.tables WHERE name = 'instance_handoff_notes' AND schema_id = SCHEMA_ID('dbo')
        )
        CREATE TABLE dbo.instance_handoff_notes (
            id INT IDENTITY(1,1) PRIMARY KEY,
            created_utc DATETIME2 NOT NULL,
            source_host NVARCHAR(100) NOT NULL,
            title NVARCHAR(200) NOT NULL,
            body NVARCHAR(MAX) NOT NULL,
            acknowledged_by NVARCHAR(100) NULL,
            acknowledged_utc DATETIME2 NULL
        )
        """
    )


def write_handoff_note(title: str, body: str, source_host: str = "") -> dict:
    title = str(title or "").strip()
    body = str(body or "").strip()
    if not title:
        raise ValueError("title is required")
    if not body:
        raise ValueError("body is required")
    host = str(source_host or "").strip() or socket.gethostname()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    with get_connection() as conn:
        _ensure_instance_handoff_notes_table(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO instance_handoff_notes (created_utc, source_host, title, body)
            VALUES (?, ?, ?, ?)
            """,
            (now_iso, host, title, body),
        )
    return {"created_utc": now_iso, "source_host": host, "title": title}


def list_handoff_notes(limit: int = 20, unacknowledged_only: bool = False) -> list[dict]:
    top = max(1, min(int(limit or 20), 100))
    where = "WHERE acknowledged_utc IS NULL" if unacknowledged_only else ""
    with get_connection() as conn:
        _ensure_instance_handoff_notes_table(conn)
        cursor = conn.cursor()
        if _using_sqlite():
            cursor.execute(
                f"""
                SELECT id, created_utc, source_host, title, body, acknowledged_by, acknowledged_utc
                FROM instance_handoff_notes
                {where}
                ORDER BY created_utc DESC
                LIMIT ?
                """,
                (top,),
            )
        else:
            cursor.execute(
                f"""
                SELECT TOP ({top}) id, created_utc, source_host, title, body, acknowledged_by, acknowledged_utc
                FROM dbo.instance_handoff_notes
                {where}
                ORDER BY created_utc DESC
                """,
                (),
            )
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def acknowledge_handoff_note(note_id: int, acknowledged_by: str) -> dict:
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    by = str(acknowledged_by or "").strip() or socket.gethostname()
    with get_connection() as conn:
        _ensure_instance_handoff_notes_table(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE instance_handoff_notes
            SET acknowledged_by = ?, acknowledged_utc = ?
            WHERE id = ?
            """,
            (by, now_iso, note_id),
        )
    return {"id": note_id, "acknowledged_by": by, "acknowledged_utc": now_iso}


_instance_control_table_ensured_targets: set[str] = set()


def _ensure_instance_control_table(conn) -> None:
    target_key = _sqlite_path() or "postgres"
    if target_key in _instance_control_table_ensured_targets:
        return
    if _using_sqlite():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instance_control (
                job_name TEXT PRIMARY KEY,
                active_hostname TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_utc TEXT NOT NULL
            )
            """
        )
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(instance_control)").fetchall()}
        if "ack_hostname" not in existing_cols:
            conn.execute("ALTER TABLE instance_control ADD COLUMN ack_hostname TEXT")
        if "ack_utc" not in existing_cols:
            conn.execute("ALTER TABLE instance_control ADD COLUMN ack_utc TEXT")
        _instance_control_table_ensured_targets.add(target_key)
        return
    cursor = conn.cursor()
    if _using_postgres():
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS instance_control (
                job_name TEXT PRIMARY KEY,
                active_hostname TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_utc TIMESTAMP NOT NULL
            )
            """
        )
        cursor.execute("ALTER TABLE instance_control ADD COLUMN IF NOT EXISTS ack_hostname TEXT")
        cursor.execute("ALTER TABLE instance_control ADD COLUMN IF NOT EXISTS ack_utc TIMESTAMP")
        _instance_control_table_ensured_targets.add(target_key)
        return
    cursor.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.tables WHERE name = 'instance_control' AND schema_id = SCHEMA_ID('dbo')
        )
        CREATE TABLE dbo.instance_control (
            job_name NVARCHAR(100) PRIMARY KEY,
            active_hostname NVARCHAR(100) NOT NULL,
            updated_by NVARCHAR(100) NOT NULL,
            updated_utc DATETIME2 NOT NULL
        )
        """
    )
    cursor.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID('dbo.instance_control') AND name = 'ack_hostname'
        )
        ALTER TABLE dbo.instance_control ADD ack_hostname NVARCHAR(100) NULL
        """
    )
    cursor.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID('dbo.instance_control') AND name = 'ack_utc'
        )
        ALTER TABLE dbo.instance_control ADD ack_utc DATETIME2 NULL
        """
    )
    _instance_control_table_ensured_targets.add(target_key)


def _this_instance_hostname() -> str:
    override = os.environ.get("CASEFORGE_INSTANCE_HOSTNAME", "").strip()
    return override or socket.gethostname()


_ACTIVE_HOST_CACHE_TTL_SECONDS = 20.0
_active_host_cache: dict[tuple[str, str], tuple[float, str | None]] = {}


def _active_host_cache_key(job_name: str) -> tuple[str, str]:
    return (_sqlite_path() or "postgres", job_name)


OWNERSHIP_OWNER = "owner"
OWNERSHIP_OTHER = "other"
OWNERSHIP_UNKNOWN = "unknown"


def active_host_status(job_name: str) -> tuple[str, str | None]:
    cache_key = _active_host_cache_key(job_name)
    cached = _active_host_cache.get(cache_key)
    now = time.monotonic()
    if cached is not None and (now - cached[0]) < _ACTIVE_HOST_CACHE_TTL_SECONDS:
        active_hostname = cached[1]
    else:
        try:
            with get_connection() as conn:
                _ensure_instance_control_table(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT active_hostname FROM instance_control WHERE job_name = ?",
                    (job_name,),
                )
                row = cursor.fetchone()
                active_hostname = str(row[0]) if row else None
        except Exception:
            return (OWNERSHIP_UNKNOWN, None)
        _active_host_cache[cache_key] = (now, active_hostname)

    if not active_hostname:
        return (OWNERSHIP_UNKNOWN, None)
    if active_hostname.lower() == _this_instance_hostname().lower():
        return (OWNERSHIP_OWNER, active_hostname)
    return (OWNERSHIP_OTHER, active_hostname)


def is_active_host(job_name: str) -> bool:
    return active_host_status(job_name)[0] == OWNERSHIP_OWNER


def list_instance_control() -> list[dict]:
    with get_connection() as conn:
        _ensure_instance_control_table(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT job_name, active_hostname, updated_by, updated_utc, ack_hostname, ack_utc "
            "FROM instance_control ORDER BY job_name"
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


if __name__ == "__main__":
    import argparse
    import json as _json

    def _parse_bool(value: str) -> bool | None:
        v = value.strip().lower()
        if v in ("true", "1", "yes"):
            return True
        if v in ("false", "0", "no"):
            return False
        if v in ("null", "none", ""):
            return None
        raise argparse.ArgumentTypeError(f"Expected true/false/null, got: {value!r}")

    parser = argparse.ArgumentParser(description="caseforge-clientdb query and permission tool")
    sub = parser.add_subparsers(dest="cmd", metavar="COMMAND")

    p_search = sub.add_parser("search", help="Search clients/matters by name, email, phone, or DOB")
    p_search.add_argument("query", help="Search term")
    p_search.add_argument("--limit", "-n", type=int, default=8, metavar="N")

    p_getperm = sub.add_parser("get-permission", help="Show all permission flags for a matter")
    p_getperm.add_argument("matter_id")

    p_sep = sub.add_parser("set-email-print", help="Set allow_email_print flag (true/false/null)")
    p_sep.add_argument("matter_id")
    p_sep.add_argument("value", type=_parse_bool, metavar="true|false|null")
    p_sep.add_argument("--by", default="operator", metavar="WHO")
    p_sep.add_argument("--notes", default="", metavar="TEXT")

    p_sos = sub.add_parser("set-sos-to-court-draft", help="Set allow_sos_to_court_draft flag (true/false/null)")
    p_sos.add_argument("matter_id")
    p_sos.add_argument("value", type=_parse_bool, metavar="true|false|null")
    p_sos.add_argument("--by", default="operator", metavar="WHO")
    p_sos.add_argument("--notes", default="", metavar="TEXT")

    p_ls = sub.add_parser("set-live-status", help="Write matter_live_status fields (CaseForge Monitor)")
    p_ls.add_argument("matter_id")
    p_ls.add_argument("--order-status", dest="order_status", default=None)
    p_ls.add_argument("--awaiting", dest="awaiting_next_step", default=None,
                      help="Comma list of open obligation tokens: send_to_client,book_counsel,arrange_service,prepare_bundle")
    p_ls.add_argument("--next-hearing", dest="next_hearing_text", default=None,
                      help='"<date> | <court>"')
    p_ls.add_argument("--service-status", dest="service_status", default=None)
    p_ls.add_argument("--latest", dest="latest_live_status", default=None)

    sub.add_parser("list-obligations", help="List matter_live_status rows with open obligations")

    p_perms = sub.add_parser("permissions", help="List all matter_permissions rows")
    p_perms.add_argument("--include-closed", action="store_true")

    sub.add_parser("list-closed", help="List all closed matters")

    p_activity = sub.add_parser("activity-backfill", help="Backfill temporary ops activity_status from client matter dates")
    p_activity.add_argument("--cutoff-year", type=int, default=2025)

    p_close = sub.add_parser("close", help="Mark a matter as closed")
    p_close.add_argument("matter_id")
    p_close.add_argument("--by", default="operator", metavar="WHO")
    p_close.add_argument("--notes", default="", metavar="TEXT")

    p_reopen = sub.add_parser("reopen", help="Reopen a closed matter")
    p_reopen.add_argument("matter_id")
    p_reopen.add_argument("--by", default="operator", metavar="WHO")
    p_reopen.add_argument("--notes", default="", metavar="TEXT")

    p_fl = sub.add_parser("folder-location", help="Look up cached matter folder location")
    p_fl.add_argument("query", nargs="?", default="", help="Name search term (used when --matter-id misses or is absent)")
    p_fl.add_argument("--matter-id", default="", metavar="ID")
    p_fl.add_argument("--limit", "-n", type=int, default=5, metavar="N", help=argparse.SUPPRESS)

    p_query = sub.add_parser("query", help="Run a raw read-only SQL SELECT/CTE (trusted ad-hoc use only)")
    p_query.add_argument("sql", metavar="SQL")

    p_hw = sub.add_parser("handoff-write", help="Write a cross-machine coordination note")
    p_hw.add_argument("title")
    p_hw.add_argument("body")
    p_hw.add_argument("--host", default="", metavar="HOSTNAME", help="Defaults to this machine's hostname")

    p_hl = sub.add_parser("handoff-list", help="List cross-machine coordination notes")
    p_hl.add_argument("--limit", "-n", type=int, default=20, metavar="N")
    p_hl.add_argument("--unacknowledged-only", action="store_true")

    p_ha = sub.add_parser("handoff-ack", help="Acknowledge a coordination note by id")
    p_ha.add_argument("note_id", type=int)
    p_ha.add_argument("--by", default="", metavar="WHO", help="Defaults to this machine's hostname")

    args = parser.parse_args()

    if args.cmd is None:
        parser.print_help()
        sys.exit(0)

    try:
        if args.cmd == "search":
            import agwu

            result = agwu.resolve_client(args.query, limit=args.limit, caller="clientdb_sql.cli")
            rows = [m.row for m in result.matches]
            print(_json.dumps({"status": result.status, "matches": rows}, indent=2, default=str))

        elif args.cmd == "get-permission":
            result = {
                "matter_id": args.matter_id,
                "allow_email_print": get_email_print_permission(args.matter_id),
                "allow_sos_to_court_draft": get_sos_to_court_draft_permission(args.matter_id),
            }
            print(_json.dumps(result, indent=2, default=str))

        elif args.cmd == "set-email-print":
            set_email_print_permission(args.matter_id, args.value, set_by=args.by, notes=args.notes)
            print(f"allow_email_print set to {args.value} for {args.matter_id}")

        elif args.cmd == "set-sos-to-court-draft":
            set_sos_to_court_draft_permission(args.matter_id, args.value, set_by=args.by, notes=args.notes)
            print(f"allow_sos_to_court_draft set to {args.value} for {args.matter_id}")

        elif args.cmd == "set-live-status":
            payload = {
                k: getattr(args, k)
                for k in (
                    "order_status", "awaiting_next_step", "next_hearing_text",
                    "service_status", "latest_live_status",
                )
                if getattr(args, k) is not None
            }
            result = upsert_matter_live_status(args.matter_id, **payload)
            print(_json.dumps(result, indent=2, default=str))

        elif args.cmd == "list-obligations":
            print(_json.dumps(list_open_obligation_rows(), indent=2, default=str))

        elif args.cmd == "permissions":
            rows = list_email_print_permissions(include_closed=args.include_closed)
            print(_json.dumps(rows, indent=2, default=str))

        elif args.cmd == "list-closed":
            rows = list_closed_matters()
            print(_json.dumps(rows, indent=2, default=str))

        elif args.cmd == "activity-backfill":
            print(_json.dumps(backfill_matter_activity_status(cutoff_year=args.cutoff_year), indent=2, default=str))

        elif args.cmd == "close":
            close_matter(args.matter_id, closed_by=args.by, notes=args.notes)
            print(f"Matter {args.matter_id} marked closed.")

        elif args.cmd == "reopen":
            reopen_matter(args.matter_id, reopened_by=args.by, notes=args.notes)
            print(f"Matter {args.matter_id} reopened.")

        elif args.cmd == "folder-location":
            import agwu

            _fl_matter_id = str(getattr(args, "matter_id", "") or "").strip()
            _fl_query = " ".join(str(getattr(args, "query", "") or "").split())
            result = None
            if _fl_matter_id:
                result = agwu.resolve_folder(
                    _fl_matter_id, allow_live_fallback=False, caller="clientdb_sql.cli"
                )
            if (result is None or result.status == "not_found") and _fl_query:
                result = agwu.resolve_folder(
                    _fl_query, allow_live_fallback=True, caller="clientdb_sql.cli"
                )
            if result is None:
                raise SystemExit("folder-location needs a name search term or --matter-id.")
            print(_json.dumps(result.__dict__, indent=2, default=str))

        elif args.cmd == "handoff-write":
            result = write_handoff_note(args.title, args.body, source_host=args.host)
            print(_json.dumps(result, indent=2, default=str))

        elif args.cmd == "handoff-list":
            rows = list_handoff_notes(limit=args.limit, unacknowledged_only=args.unacknowledged_only)
            print(_json.dumps(rows, indent=2, default=str))

        elif args.cmd == "handoff-ack":
            result = acknowledge_handoff_note(args.note_id, acknowledged_by=args.by)
            print(_json.dumps(result, indent=2, default=str))

        elif args.cmd == "query":
            if not _raw_query_enabled():
                raise RuntimeError(
                    "Raw SQL query is disabled outside trusted CLI/admin runtime. "
                    "Set CASEFORGE_RUNTIME_LABEL to a trusted CLI label or CASEFORGE_SQL_ENABLE_RAW_QUERY=1."
                )
            safe_sql = _validate_readonly_query(args.sql)
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(safe_sql)
                if cur.description is None:
                    raise RuntimeError("Raw SQL query did not return a result set.")
                cols = [col[0] for col in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            print(_json.dumps(rows, indent=2, default=str))

    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
