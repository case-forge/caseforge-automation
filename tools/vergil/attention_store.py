#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import re
import sys
import uuid
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import clientdb_sql

MIGRATION_PATH = TOOLS_DIR / "sql" / "migrations" / "0030_attention_items.sql"

KINDS = ("update", "complaint", "switchboard", "scope_creep", "settlement", "counsel_accepted", "counsel_rejected", "court_order", "court_rejected", "new_client")
ID_PREFIX = "a:"

_COLUMNS = (
    "item_id, kind, matter_id, who, subject, summary, deadline, importance, label, complaint_domain, "
    "complaint_topic, settlement_stage, sender_domain, web_link, message_key, created_utc, status, done_by, done_utc, "
    "counsel_names, chambers_name"
)
_SELECT = _COLUMNS + ", severity"
_COLUMN_NAMES = tuple(c.strip() for c in _COLUMNS.split(","))


class AttentionError(ValueError):
    pass


class AttentionNotFound(AttentionError):
    pass


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
    _ensure_topic_column(cursor)
    _ensure_late_columns(cursor)
    _ensured.add(key)


def _ensure_topic_column(cursor) -> None:
    if clientdb_sql._using_sqlite():
        cursor.execute("PRAGMA table_info(attention_items)")
        if "complaint_topic" not in {row[1] for row in cursor.fetchall()}:
            cursor.execute("ALTER TABLE attention_items ADD COLUMN complaint_topic TEXT NOT NULL DEFAULT ''")
    else:
        cursor.execute("ALTER TABLE attention_items ADD COLUMN IF NOT EXISTS complaint_topic TEXT NOT NULL DEFAULT ''")


_LATE_COLUMNS = ("counsel_names", "chambers_name", "conversation_id", "received_utc", "done_reason", "reply_sent_utc", "severity")


def _ensure_late_columns(cursor) -> None:
    if clientdb_sql._using_sqlite():
        cursor.execute("PRAGMA table_info(attention_items)")
        have = {row[1] for row in cursor.fetchall()}
        for name in _LATE_COLUMNS:
            if name not in have:
                cursor.execute(f"ALTER TABLE attention_items ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
    else:
        for name in _LATE_COLUMNS:
            cursor.execute(f"ALTER TABLE attention_items ADD COLUMN IF NOT EXISTS {name} TEXT NOT NULL DEFAULT ''")


def _utc(when: dt.datetime | None) -> str:
    moment = (when or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _rows(cursor) -> list[dict[str, Any]]:
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def item_task_id(item_id: str) -> str:
    return f"{ID_PREFIX}{item_id}"


def parse_task_id(task_id: str) -> str:
    text = str(task_id or "").strip()
    if not text.startswith(ID_PREFIX) or len(text) == len(ID_PREFIX):
        raise AttentionError("only items from the attention store can be completed here")
    return text[len(ID_PREFIX):]


def record(
    *,
    kind: str,
    message_key: str,
    matter_id: Any = "",
    who: str = "",
    subject: str = "",
    summary: str = "",
    deadline: str = "",
    importance: str = "normal",
    label: str = "",
    complaint_domain: str = "",
    complaint_topic: str = "",
    settlement_stage: str = "",
    sender_domain: str = "",
    web_link: str = "",
    counsel_names: str = "",
    chambers_name: str = "",
    conversation_id: str = "",
    received_utc: str = "",
    severity: str = "",
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise AttentionError(f"kind must be one of {list(KINDS)}, got {kind!r}")
    key = _clean(message_key, 80)
    if not key:
        raise AttentionError("message_key is required")
    sev = _clean(severity, 10).lower()
    if sev not in ("", "soft", "hard"):
        raise AttentionError("severity must be soft or hard")
    item_id = uuid.uuid4().hex
    values = (
        item_id, kind, _clean(matter_id, 60), _clean(who, 200), _clean(subject, 300), _clean(summary, 300),
        _clean(deadline, 60), _clean(importance, 12) or "normal", _clean(label, 40), _clean(complaint_domain, 40),
        _clean(complaint_topic, 60),
        _clean(settlement_stage, 40), _clean(sender_domain, 120).lower(), _clean(web_link, 1000), key,
        _utc(now), "open", "", None, _clean(counsel_names, 300), _clean(chambers_name, 200),
    )
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(f"SELECT {_SELECT} FROM attention_items WHERE message_key = ?", (key,))
        existing = _rows(cursor)
        if existing:
            return {**existing[0], "created": False}
        cursor.execute(
            f"INSERT INTO attention_items ({_COLUMNS}) VALUES ({', '.join('?' for _ in _COLUMN_NAMES)})",
            values,
        )
        if conversation_id or received_utc or sev:
            cursor.execute(
                "UPDATE attention_items SET conversation_id = ?, received_utc = ?, severity = ? WHERE item_id = ?",
                (_clean(conversation_id, 400), _clean(received_utc, 40), sev, item_id),
            )
    return {**dict(zip(_COLUMN_NAMES, values)), "severity": sev, "created": True}


def make_urgent(message_key: str, *, label: str = "") -> bool:
    key = _clean(message_key, 80)
    if not key:
        return False
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT label FROM attention_items WHERE message_key = ? AND status = 'open' AND importance <> 'high'", (key,))
        row = cursor.fetchone()
        if not row:
            return False
        cursor.execute(
            "UPDATE attention_items SET importance = 'high', label = ? WHERE message_key = ? AND status = 'open'",
            (str(row[0] or "") or _clean(label, 40), key),
        )
        return True


_EXTRA = "conversation_id, received_utc, done_reason, reply_sent_utc"


def conversation_items(conversation_id: str, *, kind: str, status: str) -> list[dict[str, Any]]:
    conv = _clean(conversation_id, 400)
    if not conv:
        return []
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_SELECT}, {_EXTRA} FROM attention_items "
            "WHERE conversation_id = ? AND kind = ? AND status = ?",
            (conv, kind, status),
        )
        return _rows(cursor)


def latest_conversation_summary(conversation_id: str, *, exclude_message_key: str = "") -> str:
    conv = _clean(conversation_id, 400)
    if not conv:
        return ""
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT summary, message_key FROM attention_items WHERE conversation_id = ? AND summary <> '' "
            "ORDER BY created_utc DESC",
            (conv,),
        )
        for summary, key in cursor.fetchall():
            if key != _clean(exclude_message_key, 80):
                return str(summary or "")
    return ""


def close_replied(item_id: str, reason: str, reply_sent_utc: str, *, by: str = "CaseForge", now: dt.datetime | None = None) -> bool:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM attention_items WHERE item_id = ? AND status = 'open'", (str(item_id),))
        if not cursor.fetchone():
            return False
        cursor.execute(
            "UPDATE attention_items SET status = 'done', done_by = ?, done_utc = ?, done_reason = ?, reply_sent_utc = ? "
            "WHERE item_id = ? AND status = 'open'",
            (_clean(by, 60), _utc(now), _clean(reason, 200), _clean(reply_sent_utc, 40), str(item_id)),
        )
        return True


def close_opened(message_key: str, *, now: dt.datetime | None = None) -> int:
    key = _clean(message_key, 80)
    if not key:
        return 0
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM attention_items WHERE message_key = ? AND status = 'open'", (key,))
        count = int((cursor.fetchone() or [0])[0] or 0)
        if count:
            cursor.execute(
                "UPDATE attention_items SET status = 'done', done_by = 'Mailbox', done_utc = ?, "
                "done_reason = 'A person opened the email' WHERE message_key = ? AND status = 'open'",
                (_utc(now), key),
            )
        return count


def reopen(item_id: str) -> bool:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM attention_items WHERE item_id = ? AND status = 'done'", (str(item_id),))
        if not cursor.fetchone():
            return False
        cursor.execute(
            "UPDATE attention_items SET status = 'open', done_by = '', done_utc = NULL, done_reason = '', reply_sent_utc = '' "
            "WHERE item_id = ? AND status = 'done'",
            (str(item_id),),
        )
        return True


def relabel(item_id: str, kind: str, label: str, topic: str) -> bool:
    if kind not in KINDS:
        raise AttentionError(f"kind must be one of {list(KINDS)}, got {kind!r}")
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM attention_items WHERE item_id = ? AND kind = 'complaint'", (str(item_id),))
        if not cursor.fetchone():
            return False
        cursor.execute(
            "UPDATE attention_items SET kind = ?, label = ?, complaint_topic = ?, severity = 'soft' "
            "WHERE item_id = ? AND kind = 'complaint'",
            (kind, _clean(label, 60), _clean(topic, 120), str(item_id)),
        )
        return True


def refresh_summary(message_key: str, summary: str) -> bool:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        key = _clean(message_key, 80)
        cursor.execute("SELECT 1 FROM attention_items WHERE message_key = ? AND status = 'open'", (key,))
        if not cursor.fetchone():
            return False
        cursor.execute("UPDATE attention_items SET summary = ? WHERE message_key = ? AND status = 'open'", (_clean(summary, 300), key))
        return True


def list_open(*, kinds: tuple[str, ...] | None = None, matter_id: Any = None, limit: int = 500) -> list[dict[str, Any]]:
    clauses = ["status = 'open'"]
    params: list[Any] = []
    if kinds:
        bad = [k for k in kinds if k not in KINDS]
        if bad:
            raise AttentionError(f"unknown kinds {bad}")
        clauses.append(f"kind IN ({', '.join('?' for _ in kinds)})")
        params += list(kinds)
    if matter_id not in (None, ""):
        clauses.append("matter_id = ?")
        params.append(_clean(matter_id, 60))
    limit = max(1, min(int(limit), 2000))
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_SELECT} FROM attention_items WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_utc DESC LIMIT {limit}",
            tuple(params),
        )
        return _rows(cursor)


def complete(item_id: str, by: str, *, now: dt.datetime | None = None) -> dict[str, Any]:
    who = _clean(by, 60)
    if not who:
        raise AttentionError("by (your name) is required")
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(f"SELECT {_SELECT} FROM attention_items WHERE item_id = ?", (str(item_id),))
        rows = _rows(cursor)
        if not rows:
            raise AttentionNotFound(f"no such item: {item_id}")
        row = rows[0]
        if row["status"] == "done":
            return row
        stamp = _utc(now)
        cursor.execute(
            "UPDATE attention_items SET status = 'done', done_by = ?, done_utc = ? WHERE item_id = ?",
            (who, stamp, str(item_id)),
        )
    return {**row, "status": "done", "done_by": who, "done_utc": stamp}


def list_for_matter(matter_id: Any, *, limit: int = 100) -> list[dict[str, Any]]:
    mid = _clean(matter_id, 60)
    if not mid:
        return []
    limit = max(1, min(int(limit), 500))
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_SELECT} FROM attention_items WHERE matter_id = ? "
            f"ORDER BY created_utc DESC LIMIT {limit}",
            (mid,),
        )
        return _rows(cursor)


def existing_keys(keys: list[str]) -> set[str]:
    wanted = sorted({_clean(k, 80) for k in keys if _clean(k, 80)})
    found: set[str] = set()
    if not wanted:
        return found
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cursor = conn.cursor()
        for start in range(0, len(wanted), 400):
            chunk = wanted[start:start + 400]
            cursor.execute(
                f"SELECT message_key FROM attention_items WHERE message_key IN ({', '.join('?' for _ in chunk)})",
                tuple(chunk),
            )
            found.update(str(r[0]) for r in cursor.fetchall())
    return found


def new_client_notice(matter_id: Any, client_name: str, *, now: dt.datetime | None = None) -> dict[str, Any]:
    mid = _clean(matter_id, 60)
    return record(
        kind="new_client",
        message_key=f"new-client:{mid}",
        matter_id=mid,
        who=client_name,
        subject="New referrer referral",
        summary="A new referrer client has come in.",
        label="NEW REFERRAL",
        now=now,
    )
