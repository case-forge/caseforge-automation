#!/usr/bin/env python3

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

try:
    import ops_db
except ModuleNotFoundError:
    from tools import ops_db


DB_NAME = "caseforge-telemetry.sqlite3"
PROJECT_TELEMETRY_SUBPATH = Path("telemetry")
_ACTIVE_DB_PATH: Optional[Path] = None
_DEFAULT_FLUSH_ERROR_LOG = Path(__file__).resolve().parent.parent / "telemetry" / "postgres-flush-errors.log"


def _flush_error_log_path() -> Path:
    override = os.environ.get("CASEFORGE_TELEMETRY_FLUSH_ERROR_LOG", "").strip()
    return Path(override) if override else _DEFAULT_FLUSH_ERROR_LOG
_TELEMETRY_TABLES = (
    "runtime_activation_events",
    "runtime_activation_frequency_snapshots",
    "graph_api_calls",
    "state_snapshots",
    "latest_state",
    "startup_scorecards",
    "client_search_events",
    "jsonl_events",
    "session_events",
    "document_field_sources",
    "model_context_events",
    "context_source_events",
)


def utc_now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


_FLUSH_ERROR_MAX_CHARS = 240


def _short_error(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    line = f"{type(exc).__name__}: {text}" if text else type(exc).__name__
    return line[:_FLUSH_ERROR_MAX_CHARS]


def _log_flush_errors(errors: list) -> None:
    if not errors:
        return
    try:
        log_path = _flush_error_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = "; ".join(" ".join(str(e).split())[:_FLUSH_ERROR_MAX_CHARS] for e in errors)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{utc_now_z()} | {line}\n")
    except Exception:
        pass


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _content_hash(payload: Any) -> str:
    return hashlib.sha256(_json_text(payload).encode("utf-8")).hexdigest()


def _normalise_path(value: str) -> str:
    return str(value or "").strip().replace("/", "\\")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


_DEFAULT_HEARTBEAT_PAIRS = frozenset({
    ("mail-intake-azure-queue", "mail_intake"),
    ("mail-intake-webhook", "mail_intake"),
    ("graph-calendar-webhook-queue", "graph_webhook_relay"),
    ("graph-todo-webhook-queue", "graph_webhook_relay"),
    ("caseforge-startup", "sql_probe"),
    ("mail-intake-classifier", "sql_probe"),
})
_HEARTBEAT_DURATION_KEYS = frozenset({
    "duration_ms", "latency_ms", "elapsed_ms", "poll_seconds", "wait_seconds",
})
_HEARTBEAT_OK_STATUSES = frozenset({"", "ok", "success"})
_GRAPH_READ_METHODS = frozenset({"GET"})
_GRAPH_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_TOKEN_ENDPOINT_HOST = "login.microsoftonline.com"


def _is_token_endpoint(url: str) -> bool:
    return _TOKEN_ENDPOINT_HOST in str(url or "").lower()


def _heartbeat_pairs() -> frozenset:
    extra = os.getenv("CASEFORGE_TELEMETRY_HEARTBEAT_PAIRS", "").strip()
    if not extra:
        return _DEFAULT_HEARTBEAT_PAIRS
    pairs = set(_DEFAULT_HEARTBEAT_PAIRS)
    for chunk in extra.replace(";", ",").split(","):
        label, _, name = chunk.strip().partition(":")
        if label and name:
            pairs.add((label.strip(), name.strip()))
    return frozenset(pairs)


def _zero_work_metrics(metrics: Any) -> bool:
    if not isinstance(metrics, dict):
        return False
    for key, value in metrics.items():
        if isinstance(value, bool):
            if not value:
                return False
        elif isinstance(value, (int, float)):
            if key not in _HEARTBEAT_DURATION_KEYS and value != 0:
                return False
        elif isinstance(value, str):
            if key == "error" and value.strip():
                return False
            if key == "status" and value.strip().lower() not in _HEARTBEAT_OK_STATUSES:
                return False
        elif value:
            return False
    return True


def _is_heartbeat_event(event: Dict[str, Any]) -> bool:
    if os.getenv("CASEFORGE_TELEMETRY_HEARTBEAT_DISABLE", "").strip() == "1":
        return False
    pair = (
        str(event.get("runtime_label", "") or ""),
        str(event.get("event_name", "") or ""),
    )
    if pair not in _heartbeat_pairs():
        return False
    return _zero_work_metrics(event.get("metrics", {}) or {})


def _hour_key(timestamp: str) -> str:
    ts = str(timestamp or "").strip()
    if len(ts) >= 13 and ts[4:5] == "-" and ts[10:11] == "T":
        return ts[:13]
    return utc_now_z()[:13]


def _upsert_runtime_event_hourly(
    conn: sqlite3.Connection,
    hour_utc: str,
    runtime_label: str,
    event_name: str,
    *,
    events: int = 1,
    errors: int = 0,
    first_timestamp: str = "",
    last_timestamp: str = "",
    last_metrics_json: str = "{}",
) -> None:
    conn.execute(
        """
        INSERT INTO runtime_event_hourly (
            hour_utc, runtime_label, event_name, events, errors,
            first_timestamp, last_timestamp, last_metrics_json, updated_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hour_utc, runtime_label, event_name) DO UPDATE SET
            events = events + excluded.events,
            errors = errors + excluded.errors,
            last_timestamp = excluded.last_timestamp,
            last_metrics_json = excluded.last_metrics_json,
            updated_utc = excluded.updated_utc
        """,
        (hour_utc, runtime_label, event_name, events, errors,
         first_timestamp, last_timestamp, last_metrics_json, utc_now_z()),
    )


def _upsert_graph_call_hourly(
    conn: sqlite3.Connection,
    hour_utc: str,
    call_type: str,
    runtime_label: str,
    *,
    calls: int = 1,
    errors: int = 0,
    total_duration_ms: int = 0,
    max_duration_ms: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO graph_call_hourly (
            hour_utc, call_type, runtime_label, calls, errors,
            total_duration_ms, max_duration_ms, updated_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hour_utc, call_type, runtime_label) DO UPDATE SET
            calls = calls + excluded.calls,
            errors = errors + excluded.errors,
            total_duration_ms = total_duration_ms + excluded.total_duration_ms,
            max_duration_ms = MAX(max_duration_ms, excluded.max_duration_ms),
            updated_utc = excluded.updated_utc
        """,
        (hour_utc, call_type, runtime_label, calls, errors,
         total_duration_ms, max_duration_ms, utc_now_z()),
    )


def _candidate_telemetry_roots() -> list[Path]:
    candidates: list[Path] = []

    env_root = os.getenv("CASEFORGE_TELEMETRY_ROOT", "").strip() or ops_db.read_luks_paths_env("CASEFORGE_TELEMETRY_ROOT")
    if env_root:
        candidates.append(Path(env_root))

    candidates.append(_repo_root() / PROJECT_TELEMETRY_SUBPATH)

    seen: set[str] = set()
    unique: list[Path] = []
    for item in candidates:
        key = str(item).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def resolve_telemetry_root() -> Path:
    candidates = _candidate_telemetry_roots()
    existing = [item for item in candidates if item.exists()]
    if existing:
        return existing[0]
    if candidates:
        return candidates[0]
    return _repo_root() / PROJECT_TELEMETRY_SUBPATH


def resolve_db_path() -> Path:
    if _ACTIVE_DB_PATH is not None:
        return _ACTIVE_DB_PATH
    return _candidate_db_paths()[0]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_fallback_db_path() -> Path:
    return _repo_root() / PROJECT_TELEMETRY_SUBPATH / DB_NAME


def _candidate_db_paths() -> list[Path]:
    candidates: list[Path] = []

    if _ACTIVE_DB_PATH is not None:
        candidates.append(_ACTIVE_DB_PATH)

    env_db = os.getenv("CASEFORGE_TELEMETRY_DB", "").strip()
    if env_db:
        candidates.append(Path(env_db))

    configured_ops_db = ops_db.configured_ops_db_path()
    if configured_ops_db:
        candidates.append(configured_ops_db)

    env_fallback_root = os.getenv("CASEFORGE_TELEMETRY_FALLBACK_ROOT", "").strip()
    if env_fallback_root:
        candidates.append(Path(env_fallback_root) / DB_NAME)

    candidates.append(resolve_telemetry_root() / DB_NAME)
    candidates.append(_repo_fallback_db_path())

    seen: set[str] = set()
    unique: list[Path] = []
    for item in candidates:
        key = str(item).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


_LEGACY_META_KEY = "legacy:telemetry_sqlite:v1"

_SCHEMA_READY: set[str] = set()


def _legacy_migration_done(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM ops_schema_meta WHERE key = ?", (_LEGACY_META_KEY,)
        ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def _open_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    ready_key = str(db_path)
    already_ready = ready_key in _SCHEMA_READY and db_path.exists()
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        ops_db.apply_connection_pragmas(conn)
        if already_ready:
            return conn
        ops_db.ensure_schema(conn)
        _ensure_schema(conn)
        conn.commit()
        if not _legacy_migration_done(conn):
            ops_db.migrate_legacy_tables(
                _TELEMETRY_TABLES,
                ops_db.LEGACY_TELEMETRY_DB,
                db_path=db_path,
                meta_key=_LEGACY_META_KEY,
            )
        _SCHEMA_READY.add(ready_key)
        return conn
    except Exception:
        conn.close()
        raise


def _connect_with_path() -> Tuple[sqlite3.Connection, Path]:
    global _ACTIVE_DB_PATH

    errors: list[str] = []
    for db_path in _candidate_db_paths():
        try:
            conn = _open_connection(db_path)
            _ACTIVE_DB_PATH = db_path
            return conn, db_path
        except (OSError, sqlite3.Error) as exc:
            errors.append(f"{db_path}: {exc}")

    detail = " | ".join(errors) if errors else "no candidate paths available"
    raise sqlite3.OperationalError(f"unable to open telemetry database; attempted {detail}")


def _connect_raw() -> sqlite3.Connection:
    conn, _ = _connect_with_path()
    return conn


@contextlib.contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = _connect_raw()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _flush_lock_path() -> Path:
    conn, db_path = _connect_with_path()
    conn.close()
    return db_path.parent / (db_path.name + ".flush-lock")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runtime_activation_events (
            event_fingerprint TEXT PRIMARY KEY,
            timestamp TEXT,
            event_name TEXT,
            runtime_label TEXT,
            model_label TEXT,
            command_text TEXT,
            files_read_json TEXT,
            files_written_json TEXT,
            sections_skipped_json TEXT,
            metrics_json TEXT,
            inserted_utc TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_runtime_activation_events_timestamp
            ON runtime_activation_events(timestamp);

        CREATE TABLE IF NOT EXISTS runtime_activation_frequency_snapshots (
            generated_at TEXT PRIMARY KEY,
            total_events INTEGER,
            week_start TEXT,
            week_end_exclusive TEXT,
            payload_json TEXT,
            inserted_utc TEXT
        );

        CREATE TABLE IF NOT EXISTS graph_api_calls (
            event_id TEXT PRIMARY KEY,
            timestamp TEXT,
            call_type TEXT,
            method TEXT,
            url TEXT,
            status INTEGER,
            success INTEGER,
            duration_ms INTEGER,
            attempt INTEGER,
            retries INTEGER,
            request_id TEXT,
            client_request_id TEXT,
            runtime_label TEXT,
            model_label TEXT,
            payload_json TEXT,
            inserted_utc TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_graph_api_calls_timestamp
            ON graph_api_calls(timestamp);

        CREATE TABLE IF NOT EXISTS runtime_event_hourly (
            hour_utc TEXT NOT NULL,
            runtime_label TEXT NOT NULL,
            event_name TEXT NOT NULL,
            events INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0,
            first_timestamp TEXT,
            last_timestamp TEXT,
            last_metrics_json TEXT,
            updated_utc TEXT,
            PRIMARY KEY (hour_utc, runtime_label, event_name)
        );

        CREATE TABLE IF NOT EXISTS graph_call_hourly (
            hour_utc TEXT NOT NULL,
            call_type TEXT NOT NULL,
            runtime_label TEXT NOT NULL,
            calls INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0,
            total_duration_ms INTEGER NOT NULL DEFAULT 0,
            max_duration_ms INTEGER NOT NULL DEFAULT 0,
            updated_utc TEXT,
            PRIMARY KEY (hour_utc, call_type, runtime_label)
        );

        CREATE TABLE IF NOT EXISTS state_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state_kind TEXT NOT NULL,
            source_path TEXT NOT NULL,
            observed_utc TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            inserted_utc TEXT NOT NULL,
            UNIQUE(state_kind, source_path, content_hash)
        );

        CREATE INDEX IF NOT EXISTS idx_state_snapshots_kind_time
            ON state_snapshots(state_kind, observed_utc);

        CREATE TABLE IF NOT EXISTS latest_state (
            state_kind TEXT NOT NULL,
            source_path TEXT NOT NULL,
            observed_utc TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            updated_utc TEXT NOT NULL,
            PRIMARY KEY(state_kind, source_path)
        );

        CREATE TABLE IF NOT EXISTS startup_scorecards (
            scorecard_path TEXT PRIMARY KEY,
            generated_at TEXT,
            email_source TEXT,
            queue_mode TEXT,
            actionable_queue_count INTEGER,
            background_queue_count INTEGER,
            same_day_candidates INTEGER,
            payload_json TEXT,
            inserted_utc TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_startup_scorecards_generated_at
            ON startup_scorecards(generated_at);

        CREATE TABLE IF NOT EXISTS client_search_events (
            event_id TEXT PRIMARY KEY,
            recorded_at TEXT NOT NULL,
            query_raw TEXT NOT NULL,
            query_normalised TEXT NOT NULL,
            query_kind TEXT NOT NULL,
            resolver_confidence TEXT NOT NULL,
            resolver_resolved INTEGER NOT NULL,
            selected_canonical TEXT,
            selection_source TEXT,
            confirmed INTEGER NOT NULL DEFAULT 0,
            learn_observed_typo INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            inserted_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_client_search_events_recorded_at
            ON client_search_events(recorded_at);

        CREATE INDEX IF NOT EXISTS idx_client_search_events_query_normalised
            ON client_search_events(query_normalised);

        CREATE TABLE IF NOT EXISTS jsonl_events (
            record_key TEXT PRIMARY KEY,
            event_kind TEXT NOT NULL,
            source_path TEXT NOT NULL,
            event_timestamp TEXT,
            client_name TEXT,
            case_no TEXT,
            message_key TEXT,
            payload_json TEXT NOT NULL,
            inserted_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_jsonl_events_kind_time
            ON jsonl_events(event_kind, event_timestamp);

        CREATE TABLE IF NOT EXISTS session_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            model_label TEXT,
            tool_name TEXT NOT NULL,
            target TEXT,
            session_id TEXT,
            inserted_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_session_events_timestamp
            ON session_events(timestamp);

        CREATE TABLE IF NOT EXISTS document_field_sources (
            event_id TEXT PRIMARY KEY,
            recorded_at TEXT NOT NULL,
            document_kind TEXT NOT NULL,
            output_label TEXT NOT NULL,
            output_path TEXT,
            client_name TEXT,
            matter_id TEXT,
            matter_reference TEXT,
            field_name TEXT NOT NULL,
            field_value_hash TEXT,
            field_value_preview TEXT,
            redaction_level TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_label TEXT NOT NULL,
            source_path TEXT,
            source_item_id_hash TEXT,
            source_modified_utc TEXT,
            extraction_method TEXT,
            confidence TEXT,
            verified INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            payload_json TEXT NOT NULL,
            inserted_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_document_field_sources_recorded_at
            ON document_field_sources(recorded_at);

        CREATE INDEX IF NOT EXISTS idx_document_field_sources_output
            ON document_field_sources(document_kind, output_label);

        CREATE INDEX IF NOT EXISTS idx_document_field_sources_field
            ON document_field_sources(field_name);

        CREATE INDEX IF NOT EXISTS idx_document_field_sources_source
            ON document_field_sources(source_kind, source_label);

        CREATE TABLE IF NOT EXISTS model_context_events (
            event_id TEXT PRIMARY KEY,
            recorded_at TEXT NOT NULL,
            request_id TEXT,
            username_hash TEXT,
            selected_model TEXT,
            provider TEXT,
            route_label TEXT,
            route_reason TEXT,
            final_state TEXT,
            estimated_context_tokens INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cache_read_tokens INTEGER NOT NULL DEFAULT 0,
            cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd REAL NOT NULL DEFAULT 0,
            prompt_chars INTEGER NOT NULL DEFAULT 0,
            prompt_preview_hash TEXT,
            response_chars INTEGER NOT NULL DEFAULT 0,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            elapsed_seconds REAL NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            inserted_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_model_context_events_recorded_at
            ON model_context_events(recorded_at);

        CREATE INDEX IF NOT EXISTS idx_model_context_events_model
            ON model_context_events(selected_model, provider);

        CREATE INDEX IF NOT EXISTS idx_model_context_events_tokens
            ON model_context_events(estimated_context_tokens, input_tokens);

        CREATE TABLE IF NOT EXISTS context_source_events (
            event_id TEXT PRIMARY KEY,
            recorded_at TEXT NOT NULL,
            provider TEXT,
            session_id TEXT,
            turn_id TEXT,
            call_id TEXT,
            source_kind TEXT NOT NULL,
            source_label TEXT NOT NULL,
            source_path TEXT,
            tool_name TEXT,
            command_text TEXT,
            input_chars INTEGER NOT NULL DEFAULT 0,
            output_chars INTEGER NOT NULL DEFAULT 0,
            estimated_tokens INTEGER NOT NULL DEFAULT 0,
            original_token_count INTEGER NOT NULL DEFAULT 0,
            markdown_path_count INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            inserted_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_context_source_events_recorded_at
            ON context_source_events(recorded_at);

        CREATE INDEX IF NOT EXISTS idx_context_source_events_source
            ON context_source_events(source_kind, source_label);

        CREATE INDEX IF NOT EXISTS idx_context_source_events_tokens
            ON context_source_events(estimated_tokens, original_token_count);
        """
    )


def ensure_database() -> Path:
    conn, db_path = _connect_with_path()
    try:
        return db_path
    finally:
        conn.close()


GRAPH_RAW_DIAGNOSTIC_RETENTION_DAYS = 28
GRAPH_RAW_AUDIT_RETENTION_DAYS = 365

_GRAPH_AUDIT_ROW_SQL = (
    "UPPER(COALESCE(method, '')) IN ("
    + ", ".join(f"'{m}'" for m in sorted(_GRAPH_WRITE_METHODS))
    + ") AND INSTR(LOWER(COALESCE(url, '')), ?) = 0"
)


def _cutoff_z(days: int) -> str:
    moment = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def run_maintenance(payload_prune_days: int = 30, snapshot_prune_days: int = 30) -> Dict[str, int]:
    cutoff_payload = _cutoff_z(payload_prune_days)
    cutoff_snapshot = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=snapshot_prune_days)).isoformat()
    results: Dict[str, int] = {}

    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM runtime_activation_frequency_snapshots WHERE generated_at < ?",
            (cutoff_snapshot,),
        )
        results["frequency_snapshots_deleted"] = cur.rowcount

        cur = conn.execute(
            """
            DELETE FROM runtime_activation_frequency_snapshots
            WHERE rowid NOT IN (
                SELECT MAX(rowid)
                FROM runtime_activation_frequency_snapshots
                GROUP BY week_start, week_end_exclusive
            )
            """
        )
        results["frequency_snapshots_deduped"] = cur.rowcount

        cutoff_session = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).isoformat()
        cur = conn.execute(
            "DELETE FROM session_events WHERE timestamp < ?",
            (cutoff_session,),
        )
        results["session_events_deleted"] = cur.rowcount

        cap_days = _env_int("CASEFORGE_TELEMETRY_RAW_HARD_CAP_DAYS", 90)
        cutoff_cap = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=cap_days)).isoformat()
        results["runtime_raw_hard_capped"] = 0
        while True:
            rows = conn.execute(
                "SELECT event_fingerprint, timestamp, event_name, runtime_label "
                "FROM runtime_activation_events WHERE timestamp < ? LIMIT 50000",
                (cutoff_cap,),
            ).fetchall()
            if not rows:
                break
            for fingerprint, ts_str, event_name, runtime_label in rows:
                _upsert_runtime_event_hourly(
                    conn,
                    _hour_key(ts_str),
                    runtime_label or "",
                    event_name or "",
                    first_timestamp=ts_str or "",
                    last_timestamp=ts_str or "",
                )
            conn.executemany(
                "DELETE FROM runtime_activation_events WHERE event_fingerprint = ?",
                [(row[0],) for row in rows],
            )
            results["runtime_raw_hard_capped"] += len(rows)

        diag_days = _env_int("CASEFORGE_TELEMETRY_GRAPH_RAW_DAYS", GRAPH_RAW_DIAGNOSTIC_RETENTION_DAYS)
        audit_days = _env_int("CASEFORGE_TELEMETRY_GRAPH_AUDIT_DAYS", GRAPH_RAW_AUDIT_RETENTION_DAYS)
        cur = conn.execute(
            f"""
            DELETE FROM graph_api_calls
            WHERE timestamp < CASE
                WHEN {_GRAPH_AUDIT_ROW_SQL} THEN ?
                ELSE ?
            END
            """,
            (_TOKEN_ENDPOINT_HOST, _cutoff_z(audit_days), _cutoff_z(diag_days)),
        )
        results["graph_raw_pruned"] = cur.rowcount

        cur = conn.execute(
            "UPDATE graph_api_calls SET payload_json = NULL "
            f"WHERE timestamp < ? AND payload_json IS NOT NULL AND NOT ({_GRAPH_AUDIT_ROW_SQL})",
            (cutoff_payload, _TOKEN_ENDPOINT_HOST),
        )
        results["graph_api_calls_pruned"] = cur.rowcount

        hourly_days = _env_int("CASEFORGE_TELEMETRY_HOURLY_RETENTION_DAYS", 400)
        cutoff_hour = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=hourly_days)
        ).strftime("%Y-%m-%dT%H")
        cur = conn.execute("DELETE FROM runtime_event_hourly WHERE hour_utc < ?", (cutoff_hour,))
        pruned_hourly = cur.rowcount
        cur = conn.execute("DELETE FROM graph_call_hourly WHERE hour_utc < ?", (cutoff_hour,))
        results["hourly_pruned"] = pruned_hourly + cur.rowcount

        conn.commit()

    try:
        chk_conn = _connect_raw()
        try:
            row = chk_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            results["wal_checkpoint"] = list(row) if row else []
        finally:
            chk_conn.close()
    except sqlite3.Error as exc:
        results["wal_checkpoint"] = [f"error: {exc}"]

    return results


FLUSHED_WATERMARK_TABLES = frozenset({
    "runtime_activation_events", "runtime_event_hourly", "startup_scorecards",
    "session_events", "graph_call_hourly", "client_search_events",
})


_FLUSH_BATCH_DEFAULT = 1000
_FLUSH_BUDGET_HEADROOM = 50


def _flush_batch_size() -> int:
    wanted = _env_int("CASEFORGE_TELEMETRY_FLUSH_BATCH_ROWS", _FLUSH_BATCH_DEFAULT)
    try:
        budget = int(os.environ.get("CASEFORGE_SQL_QUERY_BUDGET", "3000"))
    except ValueError:
        budget = 3000
    ceiling = max(1, budget - _FLUSH_BUDGET_HEADROOM)
    return max(1, min(wanted, ceiling))


def _committed_watermark(keys: list, committed: int, prior: str, done_value: str) -> str:
    if committed >= len(keys):
        return done_value
    if committed <= 0:
        return prior
    first_unshipped = keys[committed]
    best = prior
    for key in keys[:committed]:
        if key and key < first_unshipped and key > best:
            best = key
    return best


def flush_telemetry_to_postgres(conn_str: str = "") -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "events_flushed": 0, "hourly_flushed": 0, "scorecards_flushed": 0,
        "session_events_flushed": 0, "graph_api_days_flushed": 0,
        "client_search_events_flushed": 0,
    }
    import fcntl
    flush_lock = open(_flush_lock_path(), "w")
    try:
        fcntl.flock(flush_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        flush_lock.close()
        results["skipped"] = "another flush is already running (single-flight lock)"
        return results
    forced_env = {
        "LOCAL_SQLITE_PATH": os.environ.pop("LOCAL_SQLITE_PATH", None),
        "CASEFORGE_SQL_DISABLE_LOCAL_SQLITE_DEFAULT": os.environ.get("CASEFORGE_SQL_DISABLE_LOCAL_SQLITE_DEFAULT"),
        "CASEFORGE_CLIENTDB_PG_URL": os.environ.get("CASEFORGE_CLIENTDB_PG_URL"),
    }
    os.environ["CASEFORGE_SQL_DISABLE_LOCAL_SQLITE_DEFAULT"] = "1"
    if str(conn_str or "").strip() and not os.environ.get("CASEFORGE_CLIENTDB_PG_URL", "").strip():
        os.environ["CASEFORGE_CLIENTDB_PG_URL"] = str(conn_str).strip()
    try:
        tools_dir = str(Path(__file__).resolve().parent)
        import sys
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from clientdb_sql import get_connection
        import clientdb_sql as _clientdb_sql
        if bool(getattr(_clientdb_sql, "_using_sqlite", lambda: False)()):
            results["error"] = (
                "refused: clientdb_sql resolved a local SQLite path; the telemetry "
                "flush targets the telemetry Postgres schema only (check "
                "LOCAL_SQLITE_PATH / CASEFORGE_SQL_DISABLE_LOCAL_SQLITE_DEFAULT)"
            )
            return results
        if not bool(getattr(_clientdb_sql, "_using_postgres", lambda: False)()):
            results["skipped"] = "CASEFORGE_CLIENTDB_PG_URL not set; telemetry flush skipped"
            return results

        state = get_latest_state("telemetry_postgres_flush")
        if not state.get("found"):
            state = get_latest_state("telemetry_azure_flush")
        payload_state = state.get("payload") or {}
        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

        raw_watermarks = payload_state.get("per_table")
        if isinstance(raw_watermarks, dict):
            watermarks: dict = raw_watermarks
        else:
            legacy = str(payload_state.get("last_flushed_at") or "")
            watermarks = {}
            if legacy and legacy != "1970-01-01T00:00:00Z":
                for tbl in ("runtime_activation_events", "startup_scorecards",
                            "session_events", "graph_api_calls", "client_search_events"):
                    watermarks[tbl] = legacy

        def _wm(table: str) -> str:
            return watermarks.get(table) or "1970-01-01T00:00:00Z"

        new_watermarks: dict = dict(watermarks)
        batch_rows = _flush_batch_size()
        failures: list = []
        connection_error = {"text": ""}

        def _ship(table: str, items: list, statements) -> int:
            committed = 0
            while committed < len(items) and not connection_error["text"]:
                chunk_end = committed
                chunk: list = []
                connecting = opened = False
                try:
                    while chunk_end < len(items):
                        item_statements = statements(items[chunk_end])
                        if chunk and len(chunk) + len(item_statements) > batch_rows:
                            break
                        chunk.extend(item_statements)
                        chunk_end += 1
                    connecting = True
                    with get_connection() as sql_conn:
                        opened = True
                        sql_cur = sql_conn.cursor()
                        for sql_text, params in chunk:
                            sql_cur.execute(sql_text, params)
                except Exception as exc:
                    kept = len(items) - committed
                    if connecting and not opened:
                        connection_error["text"] = _short_error(exc)
                        failures.append(f"connection: {connection_error['text']}")
                    else:
                        failures.append(
                            f"{table}: {_short_error(exc)} ({kept} rows kept locally for the next run)"
                        )
                    break
                committed = chunk_end
            return committed

        max_rows = _env_int("CASEFORGE_TELEMETRY_FLUSH_MAX_ROWS", 20000)
        with _connect() as sqlite_conn:
            rows = sqlite_conn.execute(
                "SELECT event_fingerprint, event_name, timestamp, runtime_label, model_label, command_text, metrics_json "
                "FROM runtime_activation_events WHERE timestamp > ? AND timestamp <= ? "
                "ORDER BY timestamp LIMIT ?",
                (_wm("runtime_activation_events"), now, max_rows + 1),
            ).fetchall()
        batch_complete = len(rows) <= max_rows
        if not batch_complete:
            boundary_ts = rows[max_rows][2]
            trimmed = [r for r in rows[:max_rows] if r[2] < boundary_ts]
            if trimmed:
                rows = trimmed
            else:
                rows = rows[:max_rows]

        wm_before = _wm("runtime_activation_events")
        shipped = _ship("runtime_activation_events", rows, lambda row: [(
            "INSERT INTO telemetry.runtime_activation_events "
            "(event_id, event, run_utc, runtime_label, model_label, command, sub_results_json) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT (event_id) DO NOTHING",
            (row[0], row[1], row[2], row[3], row[4], row[5], row[6]),
        )])
        results["events_flushed"] = shipped
        events_done = now if batch_complete else (rows[-1][2] if rows else wm_before)
        new_watermarks["runtime_activation_events"] = _committed_watermark(
            [r[2] for r in rows], shipped, wm_before, events_done,
        )

        with _connect() as sqlite_conn:
            hourly_rows = sqlite_conn.execute(
                "SELECT hour_utc, runtime_label, event_name, events, errors, "
                "first_timestamp, last_timestamp, updated_utc "
                "FROM runtime_event_hourly WHERE updated_utc > ? AND updated_utc <= ? "
                "ORDER BY updated_utc LIMIT ?",
                (_wm("runtime_event_hourly"), now, max_rows),
            ).fetchall()
        shipped = _ship("runtime_event_hourly", hourly_rows, lambda row: [(
            "INSERT INTO telemetry.runtime_event_hourly "
            "(hour_utc, runtime_label, event_name, events, errors, first_timestamp, last_timestamp, updated_utc) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT (hour_utc, runtime_label, event_name) DO UPDATE SET "
            "events=EXCLUDED.events, errors=EXCLUDED.errors, "
            "first_timestamp=EXCLUDED.first_timestamp, last_timestamp=EXCLUDED.last_timestamp, "
            "updated_utc=EXCLUDED.updated_utc",
            tuple(row),
        )])
        results["hourly_flushed"] = shipped
        hourly_keys = [r[7] or "" for r in hourly_rows]
        hourly_done = now if len(hourly_rows) < max_rows else max(hourly_keys, default="") or _wm("runtime_event_hourly")
        new_watermarks["runtime_event_hourly"] = _committed_watermark(
            hourly_keys, shipped, _wm("runtime_event_hourly"), hourly_done,
        )

        with _connect() as sqlite_conn:
            scards = sqlite_conn.execute(
                "SELECT scorecard_path, generated_at, payload_json "
                "FROM startup_scorecards WHERE generated_at > ? AND generated_at <= ? ORDER BY generated_at",
                (_wm("startup_scorecards"), now),
            ).fetchall()

        def _scorecard_statements(row) -> list:
            sc_payload = json.loads(row[2] or "{}")
            raw_path = (row[0] or "").replace("\\", "/")
            scorecard_id = (Path(raw_path).name or row[1] or "")[:64]
            tranches = sc_payload.get("hearing_tranches", {})
            sub_json = json.dumps(sc_payload.get("sub_results", {}))[:1000]
            return [(
                "INSERT INTO telemetry.startup_scorecards_summary "
                "(scorecard_id, run_utc, run_end_utc, runtime_label, model_label, "
                " graph_scan_success, same_day_count, high_count, normal_count, low_count, sub_results_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT (scorecard_id) DO NOTHING",
                (
                    scorecard_id,
                    sc_payload.get("run_utc"), sc_payload.get("run_end_utc"),
                    sc_payload.get("runtime_label"), sc_payload.get("model_label"),
                    1 if sc_payload.get("graph_scan_success") else 0,
                    tranches.get("same_day", 0), tranches.get("high", 0),
                    tranches.get("normal", 0), tranches.get("low", 0),
                    sub_json,
                ),
            )]

        shipped = _ship("startup_scorecards", scards, _scorecard_statements)
        results["scorecards_flushed"] = shipped
        new_watermarks["startup_scorecards"] = _committed_watermark(
            [r[1] or "" for r in scards], shipped, _wm("startup_scorecards"), now,
        )

        with _connect() as sqlite_conn:
            sevents = sqlite_conn.execute(
                "SELECT id, timestamp, model_label, tool_name, target, session_id, inserted_utc "
                "FROM session_events WHERE timestamp > ? AND timestamp <= ? ORDER BY timestamp",
                (_wm("session_events"), now),
            ).fetchall()

        def _session_statements(row) -> list:
            event_key = hashlib.sha256(
                f"{row[5]}|{row[1]}|{row[3]}|{row[4]}".encode("utf-8")
            ).hexdigest()[:64]
            return [(
                "INSERT INTO telemetry.session_events "
                "(event_key, timestamp, model_label, tool_name, target, session_id, inserted_utc) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT (event_key) DO NOTHING",
                (event_key, row[1], row[2], row[3], row[4], row[5], row[6]),
            )]

        shipped = _ship("session_events", sevents, _session_statements)
        results["session_events_flushed"] = shipped
        new_watermarks["session_events"] = _committed_watermark(
            [r[1] or "" for r in sevents], shipped, _wm("session_events"), now,
        )

        with _connect() as sqlite_conn:
            new_days = [d for (d,) in sqlite_conn.execute(
                "SELECT DISTINCT substr(hour_utc, 1, 10) "
                "FROM graph_call_hourly WHERE updated_utc > ? AND updated_utc <= ? ORDER BY 1",
                (_wm("graph_call_hourly"), now),
            ).fetchall()]
            day_aggregates = [(day_utc, sqlite_conn.execute(
                "SELECT call_type, SUM(calls) as total, "
                "SUM(calls) - SUM(errors), "
                "SUM(errors), "
                "CAST(SUM(total_duration_ms) * 1.0 / MAX(SUM(calls), 1) AS INT), "
                "COALESCE(MAX(NULLIF(runtime_label,'')), 'unspecified-runtime') "
                "FROM graph_call_hourly WHERE hour_utc >= ? AND hour_utc < ? "
                "GROUP BY call_type",
                (day_utc, day_utc + "~"),
            ).fetchall()) for day_utc in new_days]

        def _graph_day_statements(item) -> list:
            day_utc, agg_rows = item
            return [(
                "INSERT INTO telemetry.graph_api_calls_daily "
                "(day_utc, call_type, total_calls, success_count, error_count, avg_duration_ms, runtime_label) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT (day_utc, call_type) DO UPDATE SET "
                "total_calls=EXCLUDED.total_calls, success_count=EXCLUDED.success_count, "
                "error_count=EXCLUDED.error_count, avg_duration_ms=EXCLUDED.avg_duration_ms, "
                "runtime_label=EXCLUDED.runtime_label",
                (day_utc, call_type, total, successes, err_count, avg_ms, rt_label),
            ) for (call_type, total, successes, err_count, avg_ms, rt_label) in agg_rows]

        shipped = _ship("graph_call_hourly", day_aggregates, _graph_day_statements)
        results["graph_api_days_flushed"] = shipped
        if shipped >= len(day_aggregates):
            new_watermarks["graph_call_hourly"] = now

        with _connect() as sqlite_conn:
            cse_rows = sqlite_conn.execute(
                "SELECT event_id, recorded_at, query_kind, resolver_resolved, "
                "resolver_confidence, learn_observed_typo, inserted_utc "
                "FROM client_search_events WHERE recorded_at > ? AND recorded_at <= ? ORDER BY recorded_at",
                (_wm("client_search_events"), now),
            ).fetchall()
        shipped = _ship("client_search_events", cse_rows, lambda row: [(
            "INSERT INTO telemetry.client_search_events "
            "(event_id, recorded_at, query_kind, resolver_success, confidence_hint, is_typo, inserted_utc) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT (event_id) DO NOTHING",
            (row[0], row[1], row[2], 1 if row[3] else 0, row[4] or "", 1 if row[5] else 0, row[6]),
        )])
        results["client_search_events_flushed"] = shipped
        new_watermarks["client_search_events"] = _committed_watermark(
            [r[1] or "" for r in cse_rows], shipped, _wm("client_search_events"), now,
        )

        if failures:
            results["row_errors"] = len(failures)
            results["flush_errors"] = failures
            if connection_error["text"]:
                results["error"] = connection_error["text"]
            _log_flush_errors(failures)

        record_state_snapshot(
            "telemetry_postgres_flush", "postgres",
            {"per_table": {k: v for k, v in new_watermarks.items()
                           if k in FLUSHED_WATERMARK_TABLES
                           and v and v != "1970-01-01T00:00:00Z"}},
            observed_utc=now,
        )

        keep_days = _env_int("CASEFORGE_TELEMETRY_LOCAL_KEEP_DAYS", 14)
        keep_cutoff = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=keep_days)
        ).isoformat().replace("+00:00", "Z")
        pruned: Dict[str, int] = {}
        with _connect() as sqlite_conn:
            for table, column in (
                ("runtime_activation_events", "timestamp"),
                ("startup_scorecards", "generated_at"),
                ("session_events", "timestamp"),
            ):
                committed_wm = str(new_watermarks.get(table) or "")
                if not committed_wm or committed_wm == "1970-01-01T00:00:00Z":
                    continue
                cur = sqlite_conn.execute(
                    f"DELETE FROM {table} WHERE {column} <= ?",
                    (min(committed_wm, keep_cutoff),),
                )
                pruned[table] = max(int(cur.rowcount or 0), 0)
            sqlite_conn.commit()
        results["local_rows_pruned"] = pruned

    except Exception as exc:
        results["error"] = str(exc)
        _log_flush_errors([f"connection/outer: {exc}"])
    finally:
        flush_lock.close()
        for key, value in forced_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    return results


def backfill_hourly(apply: bool = False) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "runtime_heartbeats_found": 0,
        "runtime_heartbeats_deleted": 0,
        "graph_rows_aggregated": 0,
        "graph_rows_deleted": 0,
        "applied": bool(apply),
    }
    pairs = _heartbeat_pairs()
    slow_ms = _env_int("CASEFORGE_TELEMETRY_GRAPH_SLOW_MS", 2000)

    state = get_latest_state("telemetry_hourly_backfill", "graph")
    state_payload = state.get("payload") or {}
    pinned_until = str(state_payload.get("until") or "")
    graph_days_done = str(state_payload.get("last_day_done") or "")
    until = pinned_until or utc_now_z()

    with _connect() as conn:
        day_rows = conn.execute(
            "SELECT DISTINCT substr(timestamp, 1, 10) FROM runtime_activation_events "
            "WHERE timestamp < ? ORDER BY 1",
            (until,),
        ).fetchall()
    for (day,) in day_rows:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT event_fingerprint, timestamp, event_name, runtime_label, metrics_json "
                "FROM runtime_activation_events "
                "WHERE timestamp >= ? AND timestamp < ? AND timestamp < ?",
                (day, day + "~", until),
            ).fetchall()
            agg: Dict[tuple, Dict[str, Any]] = {}
            doomed: list = []
            for fingerprint, ts_str, event_name, runtime_label, metrics_json in rows:
                if (runtime_label or "", event_name or "") not in pairs:
                    continue
                try:
                    metrics = json.loads(metrics_json or "{}")
                except ValueError:
                    continue
                if not _zero_work_metrics(metrics):
                    continue
                results["runtime_heartbeats_found"] += 1
                if not apply:
                    continue
                key = (_hour_key(ts_str), runtime_label or "", event_name or "")
                entry = agg.setdefault(
                    key,
                    {"events": 0, "first": ts_str, "last": ts_str,
                     "metrics": metrics_json or "{}"},
                )
                entry["events"] += 1
                if ts_str >= entry["last"]:
                    entry["last"] = ts_str
                    entry["metrics"] = metrics_json or "{}"
                if ts_str < entry["first"]:
                    entry["first"] = ts_str
                doomed.append(fingerprint)
            if apply and doomed:
                for (hour_utc, label, name), entry in sorted(agg.items()):
                    _upsert_runtime_event_hourly(
                        conn, hour_utc, label, name,
                        events=entry["events"],
                        first_timestamp=entry["first"],
                        last_timestamp=entry["last"],
                        last_metrics_json=entry["metrics"],
                    )
                for start in range(0, len(doomed), 500):
                    chunk = doomed[start:start + 500]
                    conn.execute(
                        "DELETE FROM runtime_activation_events WHERE event_fingerprint IN (%s)"
                        % ",".join("?" * len(chunk)),
                        chunk,
                    )
                results["runtime_heartbeats_deleted"] += len(doomed)

    with _connect() as conn:
        gday_rows = conn.execute(
            "SELECT DISTINCT substr(timestamp, 1, 10) FROM graph_api_calls "
            "WHERE timestamp < ? ORDER BY 1",
            (until,),
        ).fetchall()
    last_day_done = graph_days_done
    for (day,) in gday_rows:
        if graph_days_done and day <= graph_days_done:
            continue
        with _connect() as conn:
            rows = conn.execute(
                "SELECT event_id, timestamp, call_type, method, success, duration_ms, "
                "retries, attempt, runtime_label FROM graph_api_calls "
                "WHERE timestamp >= ? AND timestamp < ? AND timestamp < ?",
                (day, day + "~", until),
            ).fetchall()
            gagg: Dict[tuple, Dict[str, int]] = {}
            gdoomed: list = []
            for (event_id, ts_str, call_type, method, success, duration_ms,
                 retries, attempt, runtime_label) in rows:
                results["graph_rows_aggregated"] += 1
                dur = int(duration_ms or 0)
                key = (_hour_key(ts_str), call_type or "", runtime_label or "")
                entry = gagg.setdefault(key, {"calls": 0, "errors": 0, "total": 0, "max": 0})
                entry["calls"] += 1
                if not success:
                    entry["errors"] += 1
                entry["total"] += dur
                entry["max"] = max(entry["max"], dur)
                deletable = (
                    bool(success)
                    and str(method or "").upper() in _GRAPH_READ_METHODS
                    and dur <= slow_ms
                    and int(retries or 0) == 0
                    and int(attempt or 0) <= 1
                )
                if deletable:
                    gdoomed.append(event_id)
            if apply:
                for (hour_utc, call_type, label), entry in sorted(gagg.items()):
                    _upsert_graph_call_hourly(
                        conn, hour_utc, call_type, label,
                        calls=entry["calls"], errors=entry["errors"],
                        total_duration_ms=entry["total"],
                        max_duration_ms=entry["max"],
                    )
                for start in range(0, len(gdoomed), 500):
                    chunk = gdoomed[start:start + 500]
                    conn.execute(
                        "DELETE FROM graph_api_calls WHERE event_id IN (%s)"
                        % ",".join("?" * len(chunk)),
                        chunk,
                    )
                results["graph_rows_deleted"] += len(gdoomed)
                last_day_done = day

    if apply:
        record_state_snapshot(
            "telemetry_hourly_backfill", "graph",
            {"until": until, "last_day_done": last_day_done},
        )
    return results


STATE_SNAPSHOT_RETENTION_DAYS = 30


def prune_state_snapshots(retention_days: Optional[int] = None, *, apply: bool = False) -> Dict[str, Any]:
    days = (
        int(retention_days)
        if retention_days is not None
        else _env_int("CASEFORGE_TELEMETRY_STATE_SNAPSHOT_RETENTION_DAYS", STATE_SNAPSHOT_RETENTION_DAYS)
    )
    cutoff = _cutoff_z(days)
    results: Dict[str, Any] = {"applied": bool(apply), "retention_days": days, "cutoff": cutoff}

    with _connect() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(LENGTH(payload_json)), 0), "
            "MIN(observed_utc), MAX(observed_utc) "
            "FROM state_snapshots WHERE observed_utc < ?",
            (cutoff,),
        ).fetchone()
        candidate_count, candidate_bytes, oldest, newest = count_row
        results["candidate_count"] = int(candidate_count or 0)
        results["candidate_bytes"] = int(candidate_bytes or 0)
        results["candidate_oldest_observed_utc"] = oldest or ""
        results["candidate_newest_observed_utc"] = newest or ""

        by_kind = conn.execute(
            "SELECT state_kind, COUNT(*) FROM state_snapshots WHERE observed_utc < ? "
            "GROUP BY state_kind ORDER BY 2 DESC",
            (cutoff,),
        ).fetchall()
        results["candidate_by_state_kind"] = {kind: int(n) for kind, n in by_kind}

        if apply:
            cur = conn.execute("DELETE FROM state_snapshots WHERE observed_utc < ?", (cutoff,))
            results["deleted_count"] = cur.rowcount
            conn.commit()
        else:
            results["deleted_count"] = 0

    return results


VACUUM_MIN_RECLAIM_BYTES = 50 * 1024 * 1024
VACUUM_MIN_FREE_DISK_HEADROOM = 1.2


def vacuum_db(
    *,
    apply: bool = False,
    min_reclaim_bytes: Optional[int] = None,
    ) -> Dict[str, Any]:
    threshold = int(VACUUM_MIN_RECLAIM_BYTES if min_reclaim_bytes is None else min_reclaim_bytes)
    results: Dict[str, Any] = {"applied": False, "skipped_reason": ""}

    conn, db_path = _connect_with_path()
    try:
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        free_pages = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
    finally:
        conn.close()

    reclaimable = page_size * free_pages
    size_before = db_path.stat().st_size if db_path.exists() else 0
    results.update({
        "db_path": str(db_path),
        "page_size": page_size,
        "free_pages": free_pages,
        "reclaimable_bytes": reclaimable,
        "size_before_bytes": size_before,
        "min_reclaim_bytes": threshold,
    })

    if reclaimable < threshold:
        results["skipped_reason"] = "below_threshold"
        return results

    from monitoring import disk_space

    free_disk = disk_space.free_bytes(db_path.parent)
    results["free_disk_bytes"] = free_disk
    if free_disk < size_before * VACUUM_MIN_FREE_DISK_HEADROOM:
        results["skipped_reason"] = "insufficient_free_disk"
        return results

    if not apply:
        results["skipped_reason"] = "dry_run"
        return results

    started = time.monotonic()
    vac = sqlite3.connect(str(db_path), timeout=60.0, isolation_level=None)
    try:
        vac.execute("VACUUM")
        vac.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        vac.close()

    size_after = db_path.stat().st_size if db_path.exists() else 0
    results.update({
        "applied": True,
        "skipped_reason": "",
        "size_after_bytes": size_after,
        "freed_bytes": max(0, size_before - size_after),
        "duration_seconds": round(time.monotonic() - started, 2),
    })
    return results


def record_runtime_event(event: Dict[str, Any]) -> None:
    if _is_heartbeat_event(event):
        ts_str = str(event.get("timestamp", "") or "") or utc_now_z()
        with _connect() as conn:
            _upsert_runtime_event_hourly(
                conn,
                _hour_key(ts_str),
                str(event.get("runtime_label", "") or ""),
                str(event.get("event_name", "") or ""),
                first_timestamp=ts_str,
                last_timestamp=ts_str,
                last_metrics_json=_json_text(event.get("metrics", {}) or {}),
            )
        return
    if not str(event.get("timestamp", "") or "").strip():
        event = {**event, "timestamp": utc_now_z()}
    fingerprint = _content_hash(event)
    inserted_utc = utc_now_z()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO runtime_activation_events (
                event_fingerprint, timestamp, event_name, runtime_label, model_label,
                command_text, files_read_json, files_written_json, sections_skipped_json,
                metrics_json, inserted_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fingerprint,
                str(event.get("timestamp", "") or ""),
                str(event.get("event_name", "") or ""),
                str(event.get("runtime_label", "") or ""),
                str(event.get("model_label", "") or ""),
                str(event.get("command", "") or ""),
                _json_text(event.get("files_read", []) or []),
                _json_text(event.get("files_written", []) or []),
                _json_text(event.get("sections_skipped", []) or []),
                _json_text(event.get("metrics", {}) or {}),
                inserted_utc,
            ),
        )


def record_frequency_snapshot(summary: Dict[str, Any]) -> None:
    inserted_utc = utc_now_z()
    generated_at = str(summary.get("generated_at", "") or inserted_utc)
    current_week = summary.get("current_week", {}) or {}
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO runtime_activation_frequency_snapshots (
                generated_at, total_events, week_start, week_end_exclusive, payload_json, inserted_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                generated_at,
                int(summary.get("total_events", 0) or 0),
                str(current_week.get("week_start", "") or ""),
                str(current_week.get("week_end_exclusive", "") or ""),
                _json_text(summary),
                inserted_utc,
            ),
        )


def record_graph_api_call(event: Dict[str, Any]) -> None:
    inserted_utc = utc_now_z()
    event_id = str(event.get("event_id", "") or _content_hash(event))
    aggregate = os.getenv("CASEFORGE_TELEMETRY_GRAPH_AGGREGATE_DISABLE", "").strip() != "1"
    success = bool(event.get("success", False))
    method = str(event.get("method", "") or "").upper()
    url = str(event.get("url", "") or "")
    duration_ms = int(event.get("duration_ms", 0) or 0)
    retries = int(event.get("retries", 0) or 0)
    attempt = int(event.get("attempt", 0) or 0)
    non_read_call = method not in _GRAPH_READ_METHODS and not _is_token_endpoint(url)
    keep_raw = (
        not aggregate
        or not success
        or non_read_call
        or duration_ms > _env_int("CASEFORGE_TELEMETRY_GRAPH_SLOW_MS", 2000)
        or retries > 0
        or attempt > 1
    )
    if aggregate:
        with _connect() as conn:
            _upsert_graph_call_hourly(
                conn,
                _hour_key(str(event.get("timestamp", "") or "")),
                str(event.get("type", "") or ""),
                str(event.get("runtime_label", "") or ""),
                errors=0 if success else 1,
                total_duration_ms=duration_ms,
                max_duration_ms=duration_ms,
            )
    if not keep_raw:
        return
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO graph_api_calls (
                event_id, timestamp, call_type, method, url, status, success, duration_ms,
                attempt, retries, request_id, client_request_id, runtime_label, model_label,
                payload_json, inserted_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                str(event.get("timestamp", "") or ""),
                str(event.get("type", "") or ""),
                str(event.get("method", "") or ""),
                str(event.get("url", "") or ""),
                int(event.get("status", 0) or 0),
                1 if bool(event.get("success", False)) else 0,
                int(event.get("duration_ms", 0) or 0),
                int(event.get("attempt", 0) or 0),
                int(event.get("retries", 0) or 0),
                str(event.get("request_id", "") or ""),
                str(event.get("client_request_id", "") or ""),
                str(event.get("runtime_label", "") or ""),
                str(event.get("model_label", "") or ""),
                _json_text(event),
                inserted_utc,
            ),
        )


def latest_state_snapshot(state_kind: str) -> Optional[Dict[str, Any]]:
    kind = str(state_kind or "").strip()
    if not kind:
        return None
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT state_kind, source_path, observed_utc, content_hash, payload_json
                FROM latest_state WHERE state_kind = ?
                ORDER BY observed_utc DESC LIMIT 1
                """,
                (kind,),
            ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    try:
        payload = json.loads(row[4]) if row[4] else None
    except (TypeError, ValueError):
        payload = None
    return {
        "state_kind": row[0],
        "source_path": row[1],
        "observed_utc": row[2],
        "content_hash": row[3],
        "payload": payload,
    }


def record_state_snapshot(
    state_kind: str,
    source_path: str,
    payload: Any,
    *,
    observed_utc: str = "",
) -> None:
    inserted_utc = utc_now_z()
    observed = observed_utc or inserted_utc
    state_kind = str(state_kind or "").strip()
    source_path = _normalise_path(source_path)
    payload_json = _json_text(payload)
    content_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO state_snapshots (
                state_kind, source_path, observed_utc, content_hash, payload_json, inserted_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (state_kind, source_path, observed, content_hash, payload_json, inserted_utc),
        )
        conn.execute(
            """
            INSERT INTO latest_state (
                state_kind, source_path, observed_utc, content_hash, payload_json, updated_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(state_kind, source_path) DO UPDATE SET
                observed_utc = excluded.observed_utc,
                content_hash = excluded.content_hash,
                payload_json = excluded.payload_json,
                updated_utc = excluded.updated_utc
            """,
            (state_kind, source_path, observed, content_hash, payload_json, inserted_utc),
        )


def record_state_snapshot_once(
    state_kind: str,
    source_path: str,
    payload: Any,
    *,
    observed_utc: str = "",
) -> bool:
    inserted_utc = utc_now_z()
    observed = observed_utc or inserted_utc
    state_kind = str(state_kind or "").strip()
    source_path = str(source_path or "").strip()
    payload_json = _json_text(payload)
    content_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO latest_state (
                state_kind, source_path, observed_utc, content_hash, payload_json, updated_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (state_kind, source_path, observed, content_hash, payload_json, inserted_utc),
        )
        return cur.rowcount > 0


def _startup_scorecard_key(scorecard_path: str, payload: Dict[str, Any], inserted_utc: str) -> str:
    candidate = _normalise_path(scorecard_path)
    if candidate:
        return candidate
    generated_at = str(payload.get("generated_at", "") or "").strip() or inserted_utc
    safe_generated = generated_at.replace(":", "-")
    return f"sql://startup_scorecards/{safe_generated}"


def record_startup_scorecard(scorecard_path: str, payload: Dict[str, Any]) -> str:
    inserted_utc = utc_now_z()
    scorecard_key = _startup_scorecard_key(scorecard_path, payload, inserted_utc)
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO startup_scorecards (
                scorecard_path, generated_at, email_source, queue_mode, actionable_queue_count,
                background_queue_count, same_day_candidates, payload_json, inserted_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scorecard_key,
                str(payload.get("generated_at", "") or ""),
                str(payload.get("email_source", "") or ""),
                str(payload.get("queue_mode", "") or ""),
                int(payload.get("actionable_queue_count", 0) or 0),
                int(payload.get("background_queue_count", 0) or 0),
                int(payload.get("same_day_candidates", 0) or 0),
                _json_text(payload),
                inserted_utc,
            ),
        )
    return scorecard_key


def _client_search_event_id(payload: Dict[str, Any]) -> str:
    parts = [
        str(payload.get("recorded_at", "") or ""),
        str(payload.get("query_raw", "") or ""),
        str(payload.get("query_normalised", "") or ""),
        str(payload.get("query_kind", "") or ""),
        str(payload.get("selected_canonical", "") or ""),
        str(payload.get("selection_source", "") or ""),
        _json_text(payload.get("top_candidates", [])),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def record_client_search_event(payload: Dict[str, Any]) -> str:
    inserted_utc = utc_now_z()
    event_payload = dict(payload)
    recorded_at = str(event_payload.get("recorded_at", "") or inserted_utc)
    event_payload["recorded_at"] = recorded_at
    event_id = _client_search_event_id(event_payload)
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO client_search_events (
                event_id, recorded_at, query_raw, query_normalised, query_kind,
                resolver_confidence, resolver_resolved, selected_canonical, selection_source,
                confirmed, learn_observed_typo, payload_json, inserted_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                recorded_at,
                str(event_payload.get("query_raw", "") or ""),
                str(event_payload.get("query_normalised", "") or ""),
                str(event_payload.get("query_kind", "") or ""),
                str(event_payload.get("resolver_confidence", "") or ""),
                1 if bool(event_payload.get("resolver_resolved", False)) else 0,
                str(event_payload.get("selected_canonical", "") or ""),
                str(event_payload.get("selection_source", "") or ""),
                1 if bool(event_payload.get("confirmed", False)) else 0,
                1 if bool(event_payload.get("learn_observed_typo", False)) else 0,
                _json_text(event_payload),
                inserted_utc,
            ),
        )
    return event_id


def _hash_optional(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _document_field_source_event_id(payload: Dict[str, Any]) -> str:
    parts = [
        str(payload.get("recorded_at", "") or ""),
        str(payload.get("document_kind", "") or ""),
        str(payload.get("output_label", "") or ""),
        str(payload.get("output_path", "") or ""),
        str(payload.get("field_name", "") or ""),
        str(payload.get("field_value_hash", "") or ""),
        str(payload.get("source_kind", "") or ""),
        str(payload.get("source_label", "") or ""),
        str(payload.get("source_path", "") or ""),
        str(payload.get("source_item_id_hash", "") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def record_document_field_source(payload: Dict[str, Any]) -> str:
    inserted_utc = utc_now_z()
    event_payload = dict(payload)
    recorded_at = str(event_payload.get("recorded_at", "") or inserted_utc)
    event_payload["recorded_at"] = recorded_at

    field_value_hash = str(event_payload.get("field_value_hash", "") or "").strip()
    if not field_value_hash and "field_value" in event_payload:
        field_value_hash = _hash_optional(event_payload.get("field_value"))
    event_payload["field_value_hash"] = field_value_hash
    event_payload.pop("field_value", None)

    source_item_id_hash = str(event_payload.get("source_item_id_hash", "") or "").strip()
    if not source_item_id_hash and "source_item_id" in event_payload:
        source_item_id_hash = _hash_optional(event_payload.get("source_item_id"))
    event_payload["source_item_id_hash"] = source_item_id_hash
    event_payload.pop("source_item_id", None)

    event_id = str(event_payload.get("event_id", "") or "").strip() or _document_field_source_event_id(event_payload)
    event_payload["event_id"] = event_id

    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO document_field_sources (
                event_id, recorded_at, document_kind, output_label, output_path,
                client_name, matter_id, matter_reference, field_name, field_value_hash,
                field_value_preview, redaction_level, source_kind, source_label,
                source_path, source_item_id_hash, source_modified_utc, extraction_method,
                confidence, verified, notes, payload_json, inserted_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                recorded_at,
                str(event_payload.get("document_kind", "") or ""),
                str(event_payload.get("output_label", "") or ""),
                _normalise_path(str(event_payload.get("output_path", "") or "")),
                str(event_payload.get("client_name", "") or ""),
                str(event_payload.get("matter_id", "") or ""),
                str(event_payload.get("matter_reference", "") or ""),
                str(event_payload.get("field_name", "") or ""),
                field_value_hash,
                str(event_payload.get("field_value_preview", "") or ""),
                str(event_payload.get("redaction_level", "") or "redacted"),
                str(event_payload.get("source_kind", "") or ""),
                str(event_payload.get("source_label", "") or ""),
                _normalise_path(str(event_payload.get("source_path", "") or "")),
                source_item_id_hash,
                str(event_payload.get("source_modified_utc", "") or ""),
                str(event_payload.get("extraction_method", "") or ""),
                str(event_payload.get("confidence", "") or ""),
                1 if bool(event_payload.get("verified", False)) else 0,
                str(event_payload.get("notes", "") or ""),
                _json_text(event_payload),
                inserted_utc,
            ),
        )
    return event_id


def _model_context_event_id(payload: Dict[str, Any]) -> str:
    parts = [
        str(payload.get("recorded_at", "") or ""),
        str(payload.get("request_id", "") or ""),
        str(payload.get("selected_model", "") or ""),
        str(payload.get("provider", "") or ""),
        str(payload.get("final_state", "") or ""),
        str(payload.get("estimated_context_tokens", "") or ""),
        str(payload.get("input_tokens", "") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def record_model_context_event(payload: Dict[str, Any]) -> str:
    inserted_utc = utc_now_z()
    event_payload = dict(payload)
    recorded_at = str(event_payload.get("recorded_at", "") or inserted_utc)
    event_payload["recorded_at"] = recorded_at
    if not event_payload.get("prompt_preview_hash") and event_payload.get("prompt_preview"):
        event_payload["prompt_preview_hash"] = _hash_optional(event_payload.get("prompt_preview"))
    event_payload.pop("prompt_preview", None)
    if not event_payload.get("username_hash") and event_payload.get("username"):
        event_payload["username_hash"] = _hash_optional(str(event_payload.get("username")).lower())
    event_id = str(event_payload.get("event_id", "") or "").strip() or _model_context_event_id(event_payload)
    event_payload["event_id"] = event_id

    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO model_context_events (
                event_id, recorded_at, request_id, username_hash, selected_model,
                provider, route_label, route_reason, final_state,
                estimated_context_tokens, input_tokens, output_tokens,
                cache_read_tokens, cache_creation_tokens, estimated_cost_usd,
                prompt_chars, prompt_preview_hash, response_chars, tool_call_count,
                elapsed_seconds, payload_json, inserted_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                recorded_at,
                str(event_payload.get("request_id", "") or ""),
                str(event_payload.get("username_hash", "") or ""),
                str(event_payload.get("selected_model", "") or ""),
                str(event_payload.get("provider", "") or ""),
                str(event_payload.get("route_label", "") or ""),
                str(event_payload.get("route_reason", "") or ""),
                str(event_payload.get("final_state", "") or ""),
                int(event_payload.get("estimated_context_tokens", 0) or 0),
                int(event_payload.get("input_tokens", 0) or 0),
                int(event_payload.get("output_tokens", 0) or 0),
                int(event_payload.get("cache_read_tokens", 0) or 0),
                int(event_payload.get("cache_creation_tokens", 0) or 0),
                float(event_payload.get("estimated_cost_usd", 0) or 0),
                int(event_payload.get("prompt_chars", 0) or 0),
                str(event_payload.get("prompt_preview_hash", "") or ""),
                int(event_payload.get("response_chars", 0) or 0),
                int(event_payload.get("tool_call_count", 0) or 0),
                float(event_payload.get("elapsed_seconds", 0) or 0),
                _json_text(event_payload),
                inserted_utc,
            ),
        )
    return event_id


def _context_source_event_id(payload: Dict[str, Any]) -> str:
    parts = [
        str(payload.get("recorded_at", "") or ""),
        str(payload.get("provider", "") or ""),
        str(payload.get("session_id", "") or ""),
        str(payload.get("turn_id", "") or ""),
        str(payload.get("call_id", "") or ""),
        str(payload.get("source_kind", "") or ""),
        str(payload.get("source_label", "") or ""),
        str(payload.get("source_path", "") or ""),
        str(payload.get("tool_name", "") or ""),
        str(payload.get("estimated_tokens", "") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def record_context_source_event(payload: Dict[str, Any]) -> str:
    inserted_utc = utc_now_z()
    event_payload = dict(payload)
    recorded_at = str(event_payload.get("recorded_at", "") or inserted_utc)
    event_payload["recorded_at"] = recorded_at
    event_id = str(event_payload.get("event_id", "") or "").strip() or _context_source_event_id(event_payload)
    event_payload["event_id"] = event_id
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO context_source_events (
                event_id, recorded_at, provider, session_id, turn_id, call_id,
                source_kind, source_label, source_path, tool_name, command_text,
                input_chars, output_chars, estimated_tokens, original_token_count,
                markdown_path_count, payload_json, inserted_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                recorded_at,
                str(event_payload.get("provider", "") or ""),
                str(event_payload.get("session_id", "") or ""),
                str(event_payload.get("turn_id", "") or ""),
                str(event_payload.get("call_id", "") or ""),
                str(event_payload.get("source_kind", "") or ""),
                str(event_payload.get("source_label", "") or ""),
                _normalise_path(str(event_payload.get("source_path", "") or "")),
                str(event_payload.get("tool_name", "") or ""),
                str(event_payload.get("command_text", "") or ""),
                int(event_payload.get("input_chars", 0) or 0),
                int(event_payload.get("output_chars", 0) or 0),
                int(event_payload.get("estimated_tokens", 0) or 0),
                int(event_payload.get("original_token_count", 0) or 0),
                int(event_payload.get("markdown_path_count", 0) or 0),
                _json_text(event_payload),
                inserted_utc,
            ),
        )
    return event_id


def _generic_record_key(event_kind: str, source_path: str, payload: Dict[str, Any]) -> str:
    key_parts = [
        str(event_kind or ""),
        _normalise_path(source_path),
        str(payload.get("message_key", "") or ""),
        str(payload.get("message_id", "") or ""),
        str(payload.get("updated_utc", "") or ""),
        str(payload.get("recorded_utc", "") or ""),
        _json_text(payload),
    ]
    return hashlib.sha256("|".join(key_parts).encode("utf-8")).hexdigest()


def record_jsonl_event(event_kind: str, source_path: str, payload: Dict[str, Any]) -> None:
    inserted_utc = utc_now_z()
    record_key = _generic_record_key(event_kind, source_path, payload)
    event_timestamp = (
        str(payload.get("updated_utc", "") or "")
        or str(payload.get("recorded_utc", "") or "")
        or str(payload.get("timestamp", "") or "")
        or inserted_utc
    )
    client_name = str(payload.get("client", "") or payload.get("client_name", "") or "")
    case_no = str(payload.get("case_no", "") or "")
    message_key = str(payload.get("message_key_hash", "") or payload.get("message_key", "") or payload.get("message_id", "") or "")
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO jsonl_events (
                record_key, event_kind, source_path, event_timestamp, client_name, case_no,
                message_key, payload_json, inserted_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_key,
                str(event_kind or "").strip(),
                _normalise_path(source_path),
                event_timestamp,
                client_name,
                case_no,
                message_key,
                _json_text(payload),
                inserted_utc,
            ),
        )


def _decode_json(text: str, fallback: Any) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return fallback


def _parse_flexible_datetime(value: str) -> Optional[dt.datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for parser in (
        lambda raw: dt.datetime.fromisoformat(raw),
        lambda raw: dt.datetime.strptime(raw, "%m/%d/%Y %H:%M:%S"),
        lambda raw: dt.datetime.strptime(raw, "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            parsed = parser(text)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc)
        except ValueError:
            continue
    return None


def _window_bounds(date_value: str = "", date_from: str = "", date_to: str = "") -> Tuple[Optional[dt.datetime], Optional[dt.datetime]]:
    if date_value:
        day = dt.date.fromisoformat(str(date_value).strip())
        start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc)
        end = start + dt.timedelta(days=1)
        return start, end
    start = _parse_flexible_datetime(date_from)
    end = _parse_flexible_datetime(date_to)
    if end and len(str(date_to).strip()) == 10:
        end = dt.datetime.combine(end.date(), dt.time.min, tzinfo=dt.timezone.utc) + dt.timedelta(days=1)
    return start, end


def _in_window(timestamp: str, *, date_value: str = "", date_from: str = "", date_to: str = "") -> bool:
    start, end = _window_bounds(date_value=date_value, date_from=date_from, date_to=date_to)
    if start is None and end is None:
        return True
    parsed = _parse_flexible_datetime(timestamp)
    if parsed is None:
        return False
    if start and parsed < start:
        return False
    if end and parsed >= end:
        return False
    return True


def get_latest_state(state_kind: str, source_path: str = "") -> Dict[str, Any]:
    state_kind = str(state_kind or "").strip()
    source_path = _normalise_path(source_path)
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        if source_path:
            row = conn.execute(
                """
                SELECT state_kind, source_path, observed_utc, content_hash, payload_json, updated_utc
                FROM latest_state
                WHERE state_kind = ? AND source_path = ?
                LIMIT 1
                """,
                (state_kind, source_path),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT state_kind, source_path, observed_utc, content_hash, payload_json, updated_utc
                FROM latest_state
                WHERE state_kind = ?
                ORDER BY observed_utc DESC, updated_utc DESC
                LIMIT 1
                """,
                (state_kind,),
            ).fetchone()
    if row is None:
        return {
            "found": False,
            "state_kind": state_kind,
            "source_path": source_path,
            "observed_utc": "",
            "updated_utc": "",
            "content_hash": "",
            "payload": None,
        }
    return {
        "found": True,
        "state_kind": str(row["state_kind"]),
        "source_path": str(row["source_path"]),
        "observed_utc": str(row["observed_utc"]),
        "updated_utc": str(row["updated_utc"]),
        "content_hash": str(row["content_hash"]),
        "payload": _decode_json(str(row["payload_json"]), None),
    }


def list_events(
    event_kind: str,
    *,
    source_path: str = "",
    date_value: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
) -> list[Dict[str, Any]]:
    event_kind = str(event_kind or "").strip()
    source_path = _normalise_path(source_path)
    limit = max(1, int(limit))
    query = """
        SELECT event_kind, source_path, event_timestamp, client_name, case_no, message_key, payload_json, inserted_utc
        FROM jsonl_events
        WHERE event_kind = ?
    """
    params: list[Any] = [event_kind]
    if source_path:
        query += " AND source_path = ?"
        params.append(source_path)
    query += " ORDER BY event_timestamp DESC, inserted_utc DESC LIMIT ?"
    params.append(max(limit * 5, limit))

    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    result: list[Dict[str, Any]] = []
    for row in rows:
        event_timestamp = str(row["event_timestamp"] or "")
        if not _in_window(event_timestamp, date_value=date_value, date_from=date_from, date_to=date_to):
            continue
        result.append(
            {
                "event_kind": str(row["event_kind"]),
                "source_path": str(row["source_path"]),
                "event_timestamp": event_timestamp,
                "client_name": str(row["client_name"] or ""),
                "case_no": str(row["case_no"] or ""),
                "message_key": str(row["message_key"] or ""),
                "payload": _decode_json(str(row["payload_json"]), {}),
                "inserted_utc": str(row["inserted_utc"] or ""),
            }
        )
        if len(result) >= limit:
            break
    return result


def list_runtime_events(
    *,
    date_value: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
) -> list[Dict[str, Any]]:
    limit = max(1, int(limit))
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT timestamp, event_name, runtime_label, model_label, command_text,
                   files_read_json, files_written_json, sections_skipped_json, metrics_json, inserted_utc
            FROM runtime_activation_events
            ORDER BY inserted_utc DESC
            LIMIT ?
            """,
            (max(limit * 5, limit),),
        ).fetchall()

    result: list[Dict[str, Any]] = []
    for row in rows:
        timestamp = str(row["timestamp"] or "")
        if not _in_window(timestamp, date_value=date_value, date_from=date_from, date_to=date_to):
            continue
        result.append(
            {
                "timestamp": timestamp,
                "event_name": str(row["event_name"] or ""),
                "runtime_label": str(row["runtime_label"] or ""),
                "model_label": str(row["model_label"] or ""),
                "command": str(row["command_text"] or ""),
                "files_read": _decode_json(str(row["files_read_json"]), []),
                "files_written": _decode_json(str(row["files_written_json"]), []),
                "sections_skipped": _decode_json(str(row["sections_skipped_json"]), []),
                "metrics": _decode_json(str(row["metrics_json"]), {}),
                "inserted_utc": str(row["inserted_utc"] or ""),
            }
        )
        if len(result) >= limit:
            break
    return result


def list_startup_scorecards(
    *,
    date_value: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 20,
) -> list[Dict[str, Any]]:
    limit = max(1, int(limit))
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT scorecard_path, generated_at, email_source, queue_mode, actionable_queue_count,
                   background_queue_count, same_day_candidates, payload_json, inserted_utc
            FROM startup_scorecards
            ORDER BY generated_at DESC, inserted_utc DESC
            LIMIT ?
            """,
            (max(limit * 5, limit),),
        ).fetchall()

    result: list[Dict[str, Any]] = []
    for row in rows:
        generated_at = str(row["generated_at"] or "")
        if not _in_window(generated_at, date_value=date_value, date_from=date_from, date_to=date_to):
            continue
        result.append(
            {
                "scorecard_path": str(row["scorecard_path"] or ""),
                "generated_at": generated_at,
                "email_source": str(row["email_source"] or ""),
                "queue_mode": str(row["queue_mode"] or ""),
                "actionable_queue_count": int(row["actionable_queue_count"] or 0),
                "background_queue_count": int(row["background_queue_count"] or 0),
                "same_day_candidates": int(row["same_day_candidates"] or 0),
                "payload": _decode_json(str(row["payload_json"]), {}),
                "inserted_utc": str(row["inserted_utc"] or ""),
            }
        )
        if len(result) >= limit:
            break
    return result


def list_client_search_events(
    *,
    date_value: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
) -> list[Dict[str, Any]]:
    limit = max(1, int(limit))
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT event_id, recorded_at, query_raw, query_normalised, query_kind,
                   resolver_confidence, resolver_resolved, selected_canonical, selection_source,
                   confirmed, learn_observed_typo, payload_json, inserted_utc
            FROM client_search_events
            ORDER BY recorded_at DESC, inserted_utc DESC
            LIMIT ?
            """,
            (max(limit * 5, limit),),
        ).fetchall()

    result: list[Dict[str, Any]] = []
    for row in rows:
        recorded_at = str(row["recorded_at"] or "")
        if not _in_window(recorded_at, date_value=date_value, date_from=date_from, date_to=date_to):
            continue
        result.append(
            {
                "event_id": str(row["event_id"] or ""),
                "recorded_at": recorded_at,
                "query_raw": str(row["query_raw"] or ""),
                "query_normalised": str(row["query_normalised"] or ""),
                "query_kind": str(row["query_kind"] or ""),
                "resolver_confidence": str(row["resolver_confidence"] or ""),
                "resolver_resolved": bool(row["resolver_resolved"]),
                "selected_canonical": str(row["selected_canonical"] or ""),
                "selection_source": str(row["selection_source"] or ""),
                "confirmed": bool(row["confirmed"]),
                "learn_observed_typo": bool(row["learn_observed_typo"]),
                "payload": _decode_json(str(row["payload_json"]), {}),
                "inserted_utc": str(row["inserted_utc"] or ""),
            }
        )
        if len(result) >= limit:
            break
    return result


def list_document_field_sources(
    *,
    date_value: str = "",
    date_from: str = "",
    date_to: str = "",
    document_kind: str = "",
    output_label: str = "",
    field_name: str = "",
    source_label: str = "",
    limit: int = 50,
) -> list[Dict[str, Any]]:
    limit = max(1, int(limit))
    query = """
        SELECT event_id, recorded_at, document_kind, output_label, output_path,
               client_name, matter_id, matter_reference, field_name,
               field_value_hash, field_value_preview, redaction_level,
               source_kind, source_label, source_path, source_item_id_hash,
               source_modified_utc, extraction_method, confidence, verified,
               notes, payload_json, inserted_utc
        FROM document_field_sources
        WHERE 1=1
    """
    params: list[Any] = []
    if document_kind:
        query += " AND document_kind = ?"
        params.append(document_kind)
    if output_label:
        query += " AND output_label LIKE ?"
        params.append(f"%{output_label}%")
    if field_name:
        query += " AND field_name LIKE ?"
        params.append(f"%{field_name}%")
    if source_label:
        query += " AND source_label LIKE ?"
        params.append(f"%{source_label}%")
    query += " ORDER BY recorded_at DESC, inserted_utc DESC LIMIT ?"
    params.append(max(limit * 5, limit))

    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    result: list[Dict[str, Any]] = []
    for row in rows:
        recorded_at = str(row["recorded_at"] or "")
        if not _in_window(recorded_at, date_value=date_value, date_from=date_from, date_to=date_to):
            continue
        result.append(
            {
                "event_id": str(row["event_id"] or ""),
                "recorded_at": recorded_at,
                "document_kind": str(row["document_kind"] or ""),
                "output_label": str(row["output_label"] or ""),
                "output_path": str(row["output_path"] or ""),
                "client_name": str(row["client_name"] or ""),
                "matter_id": str(row["matter_id"] or ""),
                "matter_reference": str(row["matter_reference"] or ""),
                "field_name": str(row["field_name"] or ""),
                "field_value_hash": str(row["field_value_hash"] or ""),
                "field_value_preview": str(row["field_value_preview"] or ""),
                "redaction_level": str(row["redaction_level"] or ""),
                "source_kind": str(row["source_kind"] or ""),
                "source_label": str(row["source_label"] or ""),
                "source_path": str(row["source_path"] or ""),
                "source_item_id_hash": str(row["source_item_id_hash"] or ""),
                "source_modified_utc": str(row["source_modified_utc"] or ""),
                "extraction_method": str(row["extraction_method"] or ""),
                "confidence": str(row["confidence"] or ""),
                "verified": bool(row["verified"]),
                "notes": str(row["notes"] or ""),
                "payload": _decode_json(str(row["payload_json"]), {}),
                "inserted_utc": str(row["inserted_utc"] or ""),
            }
        )
        if len(result) >= limit:
            break
    return result


def list_model_context_events(
    *,
    date_value: str = "",
    date_from: str = "",
    date_to: str = "",
    selected_model: str = "",
    provider: str = "",
    limit: int = 50,
) -> list[Dict[str, Any]]:
    limit = max(1, int(limit))
    query = """
        SELECT event_id, recorded_at, request_id, username_hash, selected_model,
               provider, route_label, route_reason, final_state,
               estimated_context_tokens, input_tokens, output_tokens,
               cache_read_tokens, cache_creation_tokens, estimated_cost_usd,
               prompt_chars, prompt_preview_hash, response_chars, tool_call_count,
               elapsed_seconds, payload_json, inserted_utc
        FROM model_context_events
        WHERE 1=1
    """
    params: list[Any] = []
    if selected_model:
        query += " AND selected_model = ?"
        params.append(selected_model)
    if provider:
        query += " AND provider = ?"
        params.append(provider)
    query += " ORDER BY recorded_at DESC, inserted_utc DESC LIMIT ?"
    params.append(max(limit * 5, limit))

    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    result: list[Dict[str, Any]] = []
    for row in rows:
        recorded_at = str(row["recorded_at"] or "")
        if not _in_window(recorded_at, date_value=date_value, date_from=date_from, date_to=date_to):
            continue
        result.append(
            {
                "event_id": str(row["event_id"] or ""),
                "recorded_at": recorded_at,
                "request_id": str(row["request_id"] or ""),
                "username_hash": str(row["username_hash"] or ""),
                "selected_model": str(row["selected_model"] or ""),
                "provider": str(row["provider"] or ""),
                "route_label": str(row["route_label"] or ""),
                "route_reason": str(row["route_reason"] or ""),
                "final_state": str(row["final_state"] or ""),
                "estimated_context_tokens": int(row["estimated_context_tokens"] or 0),
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
                "cache_read_tokens": int(row["cache_read_tokens"] or 0),
                "cache_creation_tokens": int(row["cache_creation_tokens"] or 0),
                "estimated_cost_usd": float(row["estimated_cost_usd"] or 0),
                "prompt_chars": int(row["prompt_chars"] or 0),
                "prompt_preview_hash": str(row["prompt_preview_hash"] or ""),
                "response_chars": int(row["response_chars"] or 0),
                "tool_call_count": int(row["tool_call_count"] or 0),
                "elapsed_seconds": float(row["elapsed_seconds"] or 0),
                "payload": _decode_json(str(row["payload_json"]), {}),
                "inserted_utc": str(row["inserted_utc"] or ""),
            }
        )
        if len(result) >= limit:
            break
    return result


def list_context_source_events(
    *,
    date_value: str = "",
    date_from: str = "",
    date_to: str = "",
    provider: str = "",
    source_kind: str = "",
    source_label: str = "",
    limit: int = 50,
) -> list[Dict[str, Any]]:
    limit = max(1, int(limit))
    query = """
        SELECT event_id, recorded_at, provider, session_id, turn_id, call_id,
               source_kind, source_label, source_path, tool_name, command_text,
               input_chars, output_chars, estimated_tokens, original_token_count,
               markdown_path_count, payload_json, inserted_utc
        FROM context_source_events
        WHERE 1=1
    """
    params: list[Any] = []
    if provider:
        query += " AND provider = ?"
        params.append(provider)
    if source_kind:
        query += " AND source_kind = ?"
        params.append(source_kind)
    if source_label:
        query += " AND source_label LIKE ?"
        params.append(f"%{source_label}%")
    query += " ORDER BY COALESCE(NULLIF(original_token_count, 0), estimated_tokens) DESC, recorded_at DESC LIMIT ?"
    params.append(max(limit * 5, limit))

    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    result: list[Dict[str, Any]] = []
    for row in rows:
        recorded_at = str(row["recorded_at"] or "")
        if not _in_window(recorded_at, date_value=date_value, date_from=date_from, date_to=date_to):
            continue
        result.append(
            {
                "event_id": str(row["event_id"] or ""),
                "recorded_at": recorded_at,
                "provider": str(row["provider"] or ""),
                "session_id": str(row["session_id"] or ""),
                "turn_id": str(row["turn_id"] or ""),
                "call_id": str(row["call_id"] or ""),
                "source_kind": str(row["source_kind"] or ""),
                "source_label": str(row["source_label"] or ""),
                "source_path": str(row["source_path"] or ""),
                "tool_name": str(row["tool_name"] or ""),
                "command_text": str(row["command_text"] or ""),
                "input_chars": int(row["input_chars"] or 0),
                "output_chars": int(row["output_chars"] or 0),
                "estimated_tokens": int(row["estimated_tokens"] or 0),
                "original_token_count": int(row["original_token_count"] or 0),
                "markdown_path_count": int(row["markdown_path_count"] or 0),
                "payload": _decode_json(str(row["payload_json"]), {}),
                "inserted_utc": str(row["inserted_utc"] or ""),
            }
        )
        if len(result) >= limit:
            break
    return result




def _load_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if getattr(args, "payload_file", ""):
        return json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    raw = getattr(args, "payload_json", "")
    if raw:
        return json.loads(raw)
    raise SystemExit("Payload required.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mirror telemetry/state into SQLite.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ensure-db", help="Create the telemetry DB if needed")
    sub.add_parser("print-db-path", help="Print resolved DB path")

    p_flush_az = sub.add_parser("flush-to-postgres", help="Push SQLite rows into the telemetry Postgres schema then prune local copies")
    p_flush_az.add_argument("--conn-str", default="", help="Postgres DSN override (falls back to CASEFORGE_CLIENTDB_PG_URL)")

    p_backfill = sub.add_parser(
        "backfill-hourly",
        help="Fold historic heartbeat/poll raw rows into the hourly tables (dry-run by default)",
    )
    p_backfill.add_argument("--apply", action="store_true", help="Write aggregates and delete the folded raw rows")

    sub.add_parser("maintenance", help="Run local retention + WAL checkpoint housekeeping")

    p_prune_state = sub.add_parser(
        "prune-state-snapshots",
        help="Report on (default) or delete aged state_snapshots rows (dry-run by default, #99)",
    )
    p_prune_state.add_argument("--apply", action="store_true", help="Delete the rows past the retention window")
    p_prune_state.add_argument(
        "--retention-days", type=int, default=None,
        help="Override CASEFORGE_TELEMETRY_STATE_SNAPSHOT_RETENTION_DAYS / the built-in default",
    )

    p_vacuum = sub.add_parser(
        "vacuum",
        help="Report on (default) or perform a VACUUM to return freed pages to the disk (#91)",
    )
    p_vacuum.add_argument("--apply", action="store_true", help="Actually run the VACUUM")
    p_vacuum.add_argument(
        "--min-reclaim-bytes", type=int, default=None,
        help="Skip unless at least this much is reclaimable (default 50 MB)",
    )

    for name in ("runtime-event", "frequency-snapshot", "graph-api-call"):
        p = sub.add_parser(name)
        p.add_argument("--payload-file", default="")
        p.add_argument("--payload-json", default="")

    p_state = sub.add_parser("state-snapshot")
    p_state.add_argument("--state-kind", required=True)
    p_state.add_argument("--source-path", required=True)
    p_state.add_argument("--observed-utc", default="")
    p_state.add_argument("--payload-file", default="")
    p_state.add_argument("--payload-json", default="")

    p_score = sub.add_parser("startup-scorecard")
    p_score.add_argument("--scorecard-path", default="")
    p_score.add_argument("--payload-file", default="")
    p_score.add_argument("--payload-json", default="")

    p_event = sub.add_parser("jsonl-event")
    p_event.add_argument("--event-kind", required=True)
    p_event.add_argument("--source-path", required=True)
    p_event.add_argument("--payload-file", default="")
    p_event.add_argument("--payload-json", default="")

    p_latest_state = sub.add_parser("get-latest-state")
    p_latest_state.add_argument("--state-kind", required=True)
    p_latest_state.add_argument("--source-path", default="")

    p_list_events = sub.add_parser("list-events")
    p_list_events.add_argument("--event-kind", required=True)
    p_list_events.add_argument("--source-path", default="")
    p_list_events.add_argument("--date", default="")
    p_list_events.add_argument("--date-from", default="")
    p_list_events.add_argument("--date-to", default="")
    p_list_events.add_argument("--limit", type=int, default=50)

    p_runtime = sub.add_parser("list-runtime-events")
    p_runtime.add_argument("--date", default="")
    p_runtime.add_argument("--date-from", default="")
    p_runtime.add_argument("--date-to", default="")
    p_runtime.add_argument("--limit", type=int, default=50)

    p_scorecards = sub.add_parser("list-startup-scorecards")
    p_scorecards.add_argument("--date", default="")
    p_scorecards.add_argument("--date-from", default="")
    p_scorecards.add_argument("--date-to", default="")
    p_scorecards.add_argument("--limit", type=int, default=20)

    p_client_search = sub.add_parser("client-search-event")
    p_client_search.add_argument("--payload-file", default="")
    p_client_search.add_argument("--payload-json", default="")

    p_doc_field_source = sub.add_parser("document-field-source")
    p_doc_field_source.add_argument("--payload-file", default="")
    p_doc_field_source.add_argument("--payload-json", default="")

    p_model_context = sub.add_parser("model-context-event")
    p_model_context.add_argument("--payload-file", default="")
    p_model_context.add_argument("--payload-json", default="")

    p_context_source = sub.add_parser("context-source-event")
    p_context_source.add_argument("--payload-file", default="")
    p_context_source.add_argument("--payload-json", default="")

    p_list_doc_field_sources = sub.add_parser("list-document-field-sources")
    p_list_doc_field_sources.add_argument("--date", default="")
    p_list_doc_field_sources.add_argument("--date-from", default="")
    p_list_doc_field_sources.add_argument("--date-to", default="")
    p_list_doc_field_sources.add_argument("--document-kind", default="")
    p_list_doc_field_sources.add_argument("--output-label", default="")
    p_list_doc_field_sources.add_argument("--field-name", default="")
    p_list_doc_field_sources.add_argument("--source-label", default="")
    p_list_doc_field_sources.add_argument("--limit", type=int, default=50)

    p_list_model_context = sub.add_parser("list-model-context-events")
    p_list_model_context.add_argument("--date", default="")
    p_list_model_context.add_argument("--date-from", default="")
    p_list_model_context.add_argument("--date-to", default="")
    p_list_model_context.add_argument("--selected-model", default="")
    p_list_model_context.add_argument("--provider", default="")
    p_list_model_context.add_argument("--limit", type=int, default=50)

    p_list_context_sources = sub.add_parser("list-context-source-events")
    p_list_context_sources.add_argument("--date", default="")
    p_list_context_sources.add_argument("--date-from", default="")
    p_list_context_sources.add_argument("--date-to", default="")
    p_list_context_sources.add_argument("--provider", default="")
    p_list_context_sources.add_argument("--source-kind", default="")
    p_list_context_sources.add_argument("--source-label", default="")
    p_list_context_sources.add_argument("--limit", type=int, default=50)

    p_list_client_search = sub.add_parser("list-client-search-events")
    p_list_client_search.add_argument("--date", default="")
    p_list_client_search.add_argument("--date-from", default="")
    p_list_client_search.add_argument("--date-to", default="")
    p_list_client_search.add_argument("--limit", type=int, default=50)

    return parser.parse_args()


def _bootstrap_val_env() -> None:
    try:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from env_bootstrap import load_repo_secrets

        load_repo_secrets()
    except Exception:
        pass


def main() -> int:
    _bootstrap_val_env()
    args = _parse_args()
    if args.cmd == "ensure-db":
        print(str(ensure_database()))
        return 0
    if args.cmd == "flush-to-postgres":
        conn_str = (
            (getattr(args, "conn_str", "") or "").strip()
            or os.getenv("CASEFORGE_CLIENTDB_PG_URL", "").strip()
            or os.getenv("LOCAL_SQL_CONNECTION_STRING", "").strip()
            or os.getenv("AZURE_SQL_CONNECTION_STRING", "").strip()
        )
        print(json.dumps(flush_telemetry_to_postgres(conn_str), ensure_ascii=False), flush=True)
        return 0
    if args.cmd == "print-db-path":
        print(str(resolve_db_path()))
        return 0
    if args.cmd == "backfill-hourly":
        print(json.dumps(backfill_hourly(apply=bool(args.apply)), ensure_ascii=False), flush=True)
        return 0
    if args.cmd == "maintenance":
        print(json.dumps(run_maintenance(), ensure_ascii=False), flush=True)
        return 0
    if args.cmd == "prune-state-snapshots":
        print(
            json.dumps(
                prune_state_snapshots(retention_days=args.retention_days, apply=bool(args.apply)),
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    if args.cmd == "vacuum":
        print(
            json.dumps(
                vacuum_db(apply=bool(args.apply), min_reclaim_bytes=args.min_reclaim_bytes),
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    if args.cmd == "runtime-event":
        record_runtime_event(_load_payload(args))
        return 0
    if args.cmd == "frequency-snapshot":
        record_frequency_snapshot(_load_payload(args))
        return 0
    if args.cmd == "graph-api-call":
        record_graph_api_call(_load_payload(args))
        return 0
    if args.cmd == "state-snapshot":
        record_state_snapshot(args.state_kind, args.source_path, _load_payload(args), observed_utc=args.observed_utc)
        return 0
    if args.cmd == "startup-scorecard":
        print(json.dumps({"scorecard_path": record_startup_scorecard(args.scorecard_path, _load_payload(args))}, ensure_ascii=False))
        return 0
    if args.cmd == "jsonl-event":
        record_jsonl_event(args.event_kind, args.source_path, _load_payload(args))
        return 0
    if args.cmd == "client-search-event":
        print(json.dumps({"event_id": record_client_search_event(_load_payload(args))}, ensure_ascii=False))
        return 0
    if args.cmd == "document-field-source":
        print(json.dumps({"event_id": record_document_field_source(_load_payload(args))}, ensure_ascii=False))
        return 0
    if args.cmd == "model-context-event":
        print(json.dumps({"event_id": record_model_context_event(_load_payload(args))}, ensure_ascii=False))
        return 0
    if args.cmd == "context-source-event":
        print(json.dumps({"event_id": record_context_source_event(_load_payload(args))}, ensure_ascii=False))
        return 0
    if args.cmd == "get-latest-state":
        print(json.dumps(get_latest_state(args.state_kind, source_path=args.source_path), ensure_ascii=False))
        return 0
    if args.cmd == "list-events":
        print(
            json.dumps(
                list_events(
                    args.event_kind,
                    source_path=args.source_path,
                    date_value=args.date,
                    date_from=args.date_from,
                    date_to=args.date_to,
                    limit=args.limit,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.cmd == "list-runtime-events":
        print(
            json.dumps(
                list_runtime_events(
                    date_value=args.date,
                    date_from=args.date_from,
                    date_to=args.date_to,
                    limit=args.limit,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.cmd == "list-startup-scorecards":
        print(
            json.dumps(
                list_startup_scorecards(
                    date_value=args.date,
                    date_from=args.date_from,
                    date_to=args.date_to,
                    limit=args.limit,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.cmd == "list-client-search-events":
        print(
            json.dumps(
                list_client_search_events(
                    date_value=args.date,
                    date_from=args.date_from,
                    date_to=args.date_to,
                    limit=args.limit,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.cmd == "list-document-field-sources":
        print(
            json.dumps(
                list_document_field_sources(
                    date_value=args.date,
                    date_from=args.date_from,
                    date_to=args.date_to,
                    document_kind=args.document_kind,
                    output_label=args.output_label,
                    field_name=args.field_name,
                    source_label=args.source_label,
                    limit=args.limit,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.cmd == "list-model-context-events":
        print(
            json.dumps(
                list_model_context_events(
                    date_value=args.date,
                    date_from=args.date_from,
                    date_to=args.date_to,
                    selected_model=args.selected_model,
                    provider=args.provider,
                    limit=args.limit,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.cmd == "list-context-source-events":
        print(
            json.dumps(
                list_context_source_events(
                    date_value=args.date,
                    date_from=args.date_from,
                    date_to=args.date_to,
                    provider=args.provider,
                    source_kind=args.source_kind,
                    source_label=args.source_label,
                    limit=args.limit,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    raise SystemExit(f"Unsupported command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
