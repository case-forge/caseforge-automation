from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Iterable

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db
import clientdb_sql

STATES = ("approved", "amend")
NOTE_MAX = 60_000
LIST_LIMIT = 100


class StatementReplyError(ValueError):
    pass


def _names(matter_ids: list[str]) -> dict[str, str]:
    if not matter_ids:
        return {}
    marks = ",".join("?" for _ in matter_ids)
    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT matter_id, canonical_name FROM dbo.matters WHERE matter_id IN ({marks})", tuple(int(m) for m in matter_ids))
        return {str(r[0]): str(r[1] or "") for r in cur.fetchall()}


COURT_STEP = "court_email"


def list_replies(state: str = "", *, limit: int = LIST_LIMIT, db_path: str | Path | None = None) -> dict[str, Any]:
    if state and state not in STATES:
        raise StatementReplyError("state must be approved or amend")
    with ops_db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT matter_id, state, note, recorded_by, recorded_utc FROM statement_replies "
            "WHERE hidden_utc IS NULL ORDER BY recorded_utc DESC, rowid DESC"
        ).fetchall()
        at_court = {str(r[0]) for r in conn.execute("SELECT matter_id FROM pipeline_step_done WHERE step = ?", (COURT_STEP,)).fetchall()}
    rows = [r for r in rows if not (r[1] == "approved" and str(r[0]) in at_court)]
    counts = {s: sum(1 for r in rows if r[1] == s) for s in STATES}
    chosen = [r for r in rows if not state or r[1] == state][: max(1, int(limit))]
    names = _names([str(r[0]) for r in chosen])
    items = [
        {"matter_id": str(r[0]), "client_name": names.get(str(r[0]), ""), "state": r[1], "note": r[2], "by": r[3], "recorded_utc": r[4]}
        for r in chosen
    ]
    return {"approved_count": counts["approved"], "amend_count": counts["amend"], "items": items}


def get_reply(matter_id: str, *, db_path: str | Path | None = None) -> dict[str, str] | None:
    with ops_db.connect(db_path) as conn:
        row = conn.execute("SELECT state, note, recorded_by, recorded_utc FROM statement_replies WHERE matter_id = ?", (str(matter_id),)).fetchone()
    return {"state": row[0], "note": row[1], "by": row[2], "recorded_utc": row[3]} if row else None


def set_reply(matter_id: str, state: str, note: str, by: str, *, db_path: str | Path | None = None) -> dict[str, str]:
    mid = str(matter_id or "").strip()
    who = str(by or "").strip()[:80]
    if not mid.isdigit():
        raise StatementReplyError("matter_id must be a matter number")
    if not who:
        raise StatementReplyError("type your name first")
    if state and state not in STATES:
        raise StatementReplyError("state must be approved, amend or empty")
    text = " ".join(str(note or "").split())[:NOTE_MAX]
    if state == "amend" and not text:
        raise StatementReplyError("say what the client wants changed")
    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM dbo.matters WHERE matter_id = ?", (int(mid),))
        if not cur.fetchone():
            raise StatementReplyError(f"no such matter: {mid}")
    with ops_db.connect(db_path) as conn:
        if state:
            conn.execute(
                "INSERT INTO statement_replies (matter_id, state, note, recorded_by, recorded_utc) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(matter_id) DO UPDATE SET state = excluded.state, note = excluded.note, "
                "recorded_by = excluded.recorded_by, recorded_utc = excluded.recorded_utc, hidden_utc = NULL, hidden_by = ''",
                (mid, state, text, who, ops_db.utc_now_z()),
            )
        else:
            conn.execute("DELETE FROM statement_replies WHERE matter_id = ?", (mid,))
        conn.commit()
    return {"matter_id": mid, "state": state}


def hide_reply(matter_id: str, by: str, *, db_path: str | Path | None = None) -> dict[str, str]:
    mid = str(matter_id or "").strip()
    who = str(by or "").strip()[:80]
    if not mid.isdigit():
        raise StatementReplyError("matter_id must be a matter number")
    if not who:
        raise StatementReplyError("type your name first")
    with ops_db.connect(db_path) as conn:
        row = conn.execute("SELECT state FROM statement_replies WHERE matter_id = ?", (mid,)).fetchone()
        if not row:
            raise StatementReplyError("there is no statement reply for this matter")
        conn.execute(
            "UPDATE statement_replies SET hidden_utc = COALESCE(hidden_utc, ?), hidden_by = CASE WHEN hidden_utc IS NULL THEN ? ELSE hidden_by END "
            "WHERE matter_id = ?",
            (ops_db.utc_now_z(), who, mid),
        )
        conn.commit()
    return {"matter_id": mid, "state": str(row[0]), "hidden": "yes"}


AUTO = "auto"

SENDER_NOT_CLIENT = "sender_not_client"
def _builtin_firm_domains() -> tuple[str, ...]:
    try:
        import firm_profile

        defaults = firm_profile.builtin_defaults()
        return tuple(d.strip().lower() for d in (defaults.firm_domains if defaults else ()) if d.strip())
    except Exception:
        return ()


FIRM_DOMAINS_FALLBACK = _builtin_firm_domains()


def _address(value: Any) -> str:
    return str(value or "").strip().strip("<>").lower()


def _firm_domains() -> tuple[str, ...]:
    try:
        import firm_profile

        profile_domains = tuple(d.strip().lower() for d in firm_profile.load_profile().firm_domains if d.strip())
    except Exception:
        profile_domains = ()
    return tuple(dict.fromkeys((*FIRM_DOMAINS_FALLBACK, *profile_domains)))


def is_firm_sender(address: Any) -> bool:
    value = _address(address)
    if not value:
        return False
    if "@" not in value:
        return True
    if value == _address(os.getenv("GRAPH_MAILBOX_UPN", "")):
        return True
    domain = value.rsplit("@", 1)[1]
    return any(domain == d or domain.endswith("." + d) for d in _firm_domains())


def client_addresses(matter_id: str) -> set[str]:
    mid = str(matter_id or "").strip()
    if not mid.isdigit():
        return set()
    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT p.email_primary FROM dbo.matters m JOIN dbo.people p ON p.person_id = m.primary_person_id WHERE m.matter_id = ?",
            (int(mid),),
        )
        rows = cur.fetchall() or []
    found = {_address(r[0]) for r in rows if r and r[0]}
    return {a for a in found if "@" in a and not is_firm_sender(a)}


def sender_is_client(matter_id: str, senders: Iterable[Any]) -> bool:
    found = [_address(s) for s in senders or () if _address(s)]
    if not found or any(is_firm_sender(a) for a in found):
        return False
    try:
        own = client_addresses(matter_id)
    except Exception:
        return False
    return bool(own) and all(a in own for a in found)


def record_auto_reply(
    matter_id: str,
    state: str,
    note: str,
    message_key: str,
    *,
    senders: Iterable[Any] = (),
    received_utc: str = "",
    db_path: str | Path | None = None,
) -> dict[str, str]:
    if state not in STATES:
        raise StatementReplyError("state must be approved or amend")
    key = " ".join(str(message_key or "").split())[:40]
    if not key:
        raise StatementReplyError("a message key is needed")
    if not sender_is_client(matter_id, senders):
        return {"matter_id": str(matter_id), "state": "", "result": SENDER_NOT_CLIENT}
    suffix = f" [auto, msg {key}]"
    existing = get_reply(matter_id, db_path=db_path)
    if existing:
        if suffix.strip() in existing["note"]:
            return {"matter_id": str(matter_id), "state": existing["state"], "result": "already_recorded"}
        if existing["by"] != AUTO and received_utc and received_utc <= existing["recorded_utc"]:
            return {"matter_id": str(matter_id), "state": existing["state"], "result": "kept_newer_human"}
    text = " ".join(str(note or "").split())
    if state == "amend" and not text:
        text = "Client asked for changes (see the email)"
    set_reply(matter_id, state, text[: NOTE_MAX - len(suffix)] + suffix, AUTO, db_path=db_path)
    return {"matter_id": str(matter_id), "state": state, "result": "recorded"}


def record_message_reply(message_key: str, state: str, *, db_path: str | Path | None = None) -> None:
    key = " ".join(str(message_key or "").split())[:40]
    if not key or state not in STATES:
        return
    with ops_db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO statement_reply_messages (message_key, state, recorded_utc) VALUES (?, ?, ?) "
            "ON CONFLICT(message_key) DO UPDATE SET state = excluded.state, recorded_utc = excluded.recorded_utc",
            (key, state, ops_db.utc_now_z()),
        )
        conn.commit()


def message_reply(message_key: str, *, db_path: str | Path | None = None) -> str:
    key = " ".join(str(message_key or "").split())[:40]
    if not key:
        return ""
    with ops_db.connect(db_path) as conn:
        row = conn.execute("SELECT state FROM statement_reply_messages WHERE message_key = ?", (key,)).fetchone()
    return str(row[0]) if row else ""
