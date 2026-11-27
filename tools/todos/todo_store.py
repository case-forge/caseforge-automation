#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import re
import sys
import uuid
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import clientdb_sql

LONDON = ZoneInfo("Europe/London")
MIGRATION_PATH = TOOLS_DIR / "sql" / "migrations" / "0028_client_todos.sql"

TITLE_MAX = 300
NOTES_MAX = 4000

_COLUMNS = (
    "todo_id, title, notes, matter_id, assignee, created_by, due_utc, due_has_time, starred, my_day_date, "
    "source, source_ref, created_utc, updated_utc, done_utc, done_by, deleted_utc, draft_link, owner, migrated_from"
)
_COLUMN_NAMES = tuple(c.strip() for c in _COLUMNS.split(","))
_OPEN_ORDER = "(done_utc IS NOT NULL), (due_utc IS NULL), due_utc, created_utc DESC"
_COMPLETED_ORDER = "done_utc DESC, created_utc DESC"
_EDITABLE = {"title", "notes", "due_utc", "due_has_time", "starred", "my_day", "matter_id"}


ACTOR = "CaseForge"


class TodoError(ValueError):
    pass




def _utc(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now(now: dt.datetime | None) -> dt.datetime:
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)


def london_today(now: dt.datetime | None = None) -> str:
    return _now(now).astimezone(LONDON).date().isoformat()


def parse_due(value: Any, *, has_time: bool) -> tuple[str | None, int]:
    if value in (None, ""):
        return None, 0
    text = str(value).strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            when = dt.datetime.combine(dt.date.fromisoformat(text), dt.time(23, 59), tzinfo=LONDON)
            return _utc(when), 0
        when = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TodoError(f"due must be an ISO date or date-time, got {value!r}") from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=LONDON)
    return _utc(when), 1 if has_time else 0



_ensured: set[str] = set()


def _ddl_statements() -> list[str]:
    text = "\n".join(line for line in MIGRATION_PATH.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--"))
    text = re.sub(r"\s+--[^\n]*", "", text)
    return [stmt.strip() for stmt in text.split(";") if stmt.strip()]


def ensure_tables(conn) -> None:
    key = f"sqlite:{clientdb_sql._sqlite_path()}" if clientdb_sql._using_sqlite() else "pg"
    if key in _ensured:
        return
    cursor = conn.cursor()
    for stmt in _ddl_statements():
        cursor.execute(stmt)
    _ensure_draft_link_column(cursor)
    _ensure_owner_columns(cursor)
    _ensured.add(key)


def _ensure_draft_link_column(cursor) -> None:
    if clientdb_sql._using_sqlite():
        cursor.execute("PRAGMA table_info(client_todos)")
        if "draft_link" not in {row[1] for row in cursor.fetchall()}:
            cursor.execute("ALTER TABLE client_todos ADD COLUMN draft_link TEXT NOT NULL DEFAULT ''")
    else:
        cursor.execute("ALTER TABLE client_todos ADD COLUMN IF NOT EXISTS draft_link TEXT NOT NULL DEFAULT ''")


def _ensure_owner_columns(cursor) -> None:
    wanted = ("owner", "migrated_from")
    if clientdb_sql._using_sqlite():
        cursor.execute("PRAGMA table_info(client_todos)")
        have = {row[1] for row in cursor.fetchall()}
        for column in wanted:
            if column not in have:
                cursor.execute(f"ALTER TABLE client_todos ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    else:
        for column in wanted:
            cursor.execute(f"ALTER TABLE client_todos ADD COLUMN IF NOT EXISTS {column} TEXT NOT NULL DEFAULT ''")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_client_todos_owner ON client_todos (owner)")


def _rows(cursor) -> list[dict[str, Any]]:
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _decorate(rows: list[dict[str, Any]], now: dt.datetime) -> list[dict[str, Any]]:
    names: dict[int, str] = {}
    ids = sorted({int(r["matter_id"]) for r in rows if r.get("matter_id") is not None})
    if ids:
        try:
            with clientdb_sql.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT matter_id, canonical_name FROM matters WHERE matter_id IN ({', '.join('?' for _ in ids)})",
                    tuple(ids),
                )
                names = {int(r[0]): _clean(r[1], 200) for r in cursor.fetchall()}
        except Exception:
            names = {}
    stamp = _utc(now)
    for row in rows:
        row["starred"] = bool(row["starred"])
        row["due_has_time"] = bool(row["due_has_time"])
        row["is_done"] = bool(row["done_utc"])
        row["is_overdue"] = bool(row["due_utc"]) and not row["done_utc"] and row["due_utc"] < stamp
        row["client_name"] = names.get(int(row["matter_id"])) if row.get("matter_id") is not None else None
        row["on_my_day_today"] = row.get("my_day_date") == london_today(now)
    return rows


def _select(
    where: str, params: tuple, *, now: dt.datetime, limit: int = 1000,
    order: str = "(done_utc IS NOT NULL), (due_utc IS NULL), due_utc, created_utc DESC",
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 3000))
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_COLUMNS} FROM client_todos {where} "
            f"ORDER BY {order} "
            f"LIMIT {limit}",
            params,
        )
        rows = _rows(cursor)
    return _decorate(rows, now)



CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("court", "Court", ("court_reply_overdue", "order_after_hearing", "hearing_date_after_hearing")),
    ("bundle", "Bundle", ("final_hearing_bundle",)),
    ("signing", "Signing", ("signing_ccl", "signing_loa_ws")),
    ("statements", "Statements", ("statement_first_overdue", "statement_unanswered")),
    ("drafts", "Drafts", ("draft_unsent",)),
    ("caseflow", "Case flow", ()),
)
BLOCKED_SOURCE = "auto-blocked"
PERSONAL_VIEWS = ("my_day", "important", "planned", "tasks", "completed", "all")
VIEWS = PERSONAL_VIEWS + tuple(f"auto_{key}" for key, _, _ in CATEGORIES)
AUTO_SOURCE = "nudge"


def automatic_settings() -> tuple[bool, set[str]]:
    try:
        import app_settings

        on = bool(app_settings.get_setting("todo_show_automatic"))
        hidden = {k for k in str(app_settings.get_setting("todo_hidden_categories") or "").split(",") if k.strip()}
        return on, {k.strip() for k in hidden}
    except Exception:
        return True, set()


def _auto_clause(keys: list[str]) -> tuple[str, list[Any]]:
    refs = [rule for key, _, rules in CATEGORIES if key in keys for rule in rules]
    parts: list[str] = []
    params: list[Any] = []
    if refs:
        parts.append("(source = ? AND (" + " OR ".join("source_ref LIKE ?" for _ in refs) + "))")
        params += [AUTO_SOURCE, *[f"{r}|%" for r in refs]]
    if "caseflow" in keys:
        parts.append("source = ?")
        params.append(BLOCKED_SOURCE)
    return ("(" + " OR ".join(parts) + ")", params) if parts else ("1 = 0", [])


def visible_categories() -> list[str]:
    on, hidden = automatic_settings()
    return [key for key, _, _ in CATEGORIES if on and key not in hidden]


def category_of(task: dict[str, Any]) -> str:
    if task.get("source") == BLOCKED_SOURCE:
        return "caseflow"
    if task.get("source") != AUTO_SOURCE:
        return ""
    rule = str(task.get("source_ref") or "").split("|", 1)[0]
    return next((key for key, _, rules in CATEGORIES if rule in rules), "")


def get(
    todo_id: str, *, owner: str | None = None, automatic: bool = False, now: dt.datetime | None = None
) -> dict[str, Any] | None:
    where, params = "WHERE todo_id = ?", [str(todo_id)]
    if owner is not None:
        mine, mine_params = "(owner = ? AND source = 'manual')", [_owner(owner)]
        if automatic:
            clause, clause_params = _auto_clause(visible_categories())
            mine, mine_params = f"({mine} OR {clause})", mine_params + clause_params
        where += f" AND {mine} AND deleted_utc IS NULL"
        params += mine_params
    rows = _select(where, tuple(params), now=_now(now), limit=1)
    return rows[0] if rows else None


def _owner(value: Any) -> str:
    return " ".join(str(value or "").split()).lower()[:200]


def list_todos(
    *,
    view: str = "all",
    matter_id: int | None = None,
    include_done: bool = False,
    limit: int = 1000,
    owner: str | None = None,
    now: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    if view not in VIEWS:
        raise TodoError(f"view must be one of {list(VIEWS)}, got {view!r}")
    moment = _now(now)
    clauses = ["deleted_utc IS NULL"]
    params: list[Any] = []
    auto_view = view.startswith("auto_")
    if owner is not None:
        if not _owner(owner):
            return []
        if auto_view:
            key = view[len("auto_"):]
            clause, clause_params = _auto_clause([key] if key in visible_categories() else [])
            clauses.append(clause)
            params += clause_params
        elif view == "all" and matter_id is None:
            clause, clause_params = _auto_clause(visible_categories())
            clauses.append(f"((owner = ? AND source = 'manual') OR {clause})")
            params += [_owner(owner), *clause_params]
        else:
            clauses += ["owner = ?", "source = 'manual'"]
            params.append(_owner(owner))
    elif auto_view:
        raise TodoError(f"view {view!r} needs an owner")
    if view == "completed":
        clauses.append("done_utc IS NOT NULL")
    elif (view == "tasks" and owner is None) or auto_view or not include_done:
        clauses.append("done_utc IS NULL")
    if matter_id is not None:
        clauses.append("matter_id = ?")
        params.append(int(matter_id))
    if view == "my_day":
        clauses.append("my_day_date = ?")
        params.append(london_today(moment))
    elif view == "important":
        clauses.append("starred = 1")
    elif view == "planned":
        clauses.append("due_utc IS NOT NULL")
    elif view == "tasks" and owner is not None:
        clauses.append("done_utc IS NULL")
    order = _COMPLETED_ORDER if view == "completed" else _OPEN_ORDER
    return _select("WHERE " + " AND ".join(clauses), tuple(params), now=moment, limit=limit, order=order)


def _count_completed(owner: str | None = None) -> int:
    sql, params = "SELECT COUNT(*) FROM client_todos WHERE deleted_utc IS NULL AND done_utc IS NOT NULL", ()
    if owner is not None:
        sql += " AND owner = ? AND source = 'manual'"
        params = (_owner(owner),)
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return int(cursor.fetchone()[0])


def summary(*, owner: str | None = None, now: dt.datetime | None = None) -> dict[str, int]:
    moment = _now(now)
    mine = list_todos(view="all", limit=3000, owner=owner, now=moment) if owner is not None else list_todos(view="tasks", limit=3000, now=moment)
    personal = [r for r in mine if r["source"] == "manual"] if owner is not None else mine
    automatic = [r for r in mine if r["source"] != "manual"] if owner is not None else []
    completed = _count_completed(owner) if owner is None or _owner(owner) else 0
    end_of_today = dt.datetime.combine(moment.astimezone(LONDON).date(), dt.time(23, 59, 59), tzinfo=LONDON)
    today_limit = _utc(end_of_today)
    overdue = [r for r in personal if r["is_overdue"]]
    due_today = [r for r in personal if r["due_utc"] and not r["is_overdue"] and r["due_utc"] <= today_limit]
    on, hidden = automatic_settings()
    counts = {
        "open": len(personal),
        "tasks": len(personal),
        "completed": completed,
        "all": len(personal) + len(automatic) + completed,
        "overdue": len(overdue),
        "important": sum(1 for r in personal if r["starred"]),
        "planned": sum(1 for r in personal if r["due_utc"]),
        "my_day": sum(1 for r in personal if r["on_my_day_today"]),
        "attention": len(overdue) + len(due_today),
        "auto_on": int(on),
    }
    for key, _, _ in CATEGORIES:
        counts[f"hide_{key}"] = int(key in hidden)
        counts[f"cat_{key}"] = sum(1 for r in automatic if category_of(r) == key and not r["is_done"])
    return counts




def _matter(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TodoError(f"matter_id must be a number, got {value!r}") from exc


def create(
    title: str,
    *,
    created_by: str = "",
    matter_id: Any = None,
    due: Any = None,
    due_has_time: bool = False,
    starred: bool = False,
    my_day: bool = False,
    notes: str = "",
    source: str = "manual",
    source_ref: str = "",
    owner: str | None = None,
    draft_link: str = "",
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    title = _clean(title, TITLE_MAX)
    if owner is not None and not _owner(owner):
        raise TodoError("a personal task needs a signed-in owner")
    if not title:
        raise TodoError("a task needs a title")
    by = _clean(created_by, 60) or ACTOR
    moment = _now(now)
    due_utc, has_time = parse_due(due, has_time=due_has_time)
    todo_id = uuid.uuid4().hex
    stamp = _utc(moment)
    ref = _clean(source_ref, 200)
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        if ref:
            cursor.execute("SELECT todo_id FROM client_todos WHERE source = ? AND source_ref = ?", (_clean(source, 40), ref))
            existing = cursor.fetchone()
            if existing:
                return get(existing[0], now=moment)
        cursor.execute(
            f"INSERT INTO client_todos ({_COLUMNS}) VALUES ({', '.join('?' for _ in _COLUMN_NAMES)})",
            (
                todo_id, title, _clean(notes, NOTES_MAX), _matter(matter_id), "", by, due_utc, has_time,
                1 if starred else 0, london_today(moment) if my_day else None, _clean(source, 40) or "manual", ref,
                stamp, stamp, None, "", None, _clean(draft_link, 2000),
                _owner(owner) if owner is not None else "", "",
            ),
        )
    return get(todo_id, now=moment)


def update(todo_id: str, fields: dict[str, Any], *, by: str = "", owner: str | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    if get(todo_id, owner=owner) is None:
        raise TodoError(f"no such task: {todo_id}")
    unknown = sorted(set(fields) - _EDITABLE)
    if unknown:
        raise TodoError(f"cannot change {unknown}")
    moment = _now(now)
    sets: dict[str, Any] = {}
    if "title" in fields:
        title = _clean(fields["title"], TITLE_MAX)
        if not title:
            raise TodoError("a task needs a title")
        sets["title"] = title
    if "notes" in fields:
        sets["notes"] = _clean(fields["notes"], NOTES_MAX)
    if "matter_id" in fields:
        sets["matter_id"] = _matter(fields["matter_id"])
    if "starred" in fields:
        sets["starred"] = 1 if fields["starred"] else 0
    if "my_day" in fields:
        sets["my_day_date"] = london_today(moment) if fields["my_day"] else None
    if "due_utc" in fields:
        sets["due_utc"], sets["due_has_time"] = parse_due(fields["due_utc"], has_time=bool(fields.get("due_has_time", True)))
    elif "due_has_time" in fields:
        sets["due_has_time"] = 1 if fields["due_has_time"] else 0
    _write(todo_id, sets, moment)
    return get(todo_id, now=moment)


def complete(todo_id: str, done: bool, *, by: str = "", owner: str | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    if get(todo_id, owner=owner, automatic=True) is None:
        raise TodoError(f"no such task: {todo_id}")
    moment = _now(now)
    who = _clean(by, 60) or ACTOR
    _write(todo_id, {"done_utc": _utc(moment) if done else None, "done_by": who if done else ""}, moment)
    return get(todo_id, now=moment)


def delete(todo_id: str, *, by: str = "", owner: str | None = None, now: dt.datetime | None = None) -> None:
    task = get(todo_id, owner=owner)
    if task is None:
        raise TodoError(f"no such task: {todo_id}")
    moment = _now(now)
    if task["source"] != "manual":
        _write(todo_id, {"deleted_utc": _utc(moment)}, moment)
        return
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        conn.cursor().execute("DELETE FROM client_todos WHERE todo_id = ?", (str(todo_id),))


def set_draft_link(todo_id: str, link: str, *, owner: str | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    if get(todo_id, owner=owner) is None:
        raise TodoError(f"no such task: {todo_id}")
    moment = _now(now)
    _write(todo_id, {"draft_link": _clean(link, 2000)}, moment)
    return get(todo_id, now=moment)


def _write(todo_id: str, sets: dict[str, Any], moment: dt.datetime) -> None:
    if not sets:
        return
    sets = {**sets, "updated_utc": _utc(moment)}
    assignments = ", ".join(f"{column} = ?" for column in sets)
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        conn.cursor().execute(
            f"UPDATE client_todos SET {assignments} WHERE todo_id = ?",
            (*sets.values(), str(todo_id)),
        )
