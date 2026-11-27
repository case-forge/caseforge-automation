from __future__ import annotations

import datetime as dt
import hashlib
import re
import sys
from pathlib import Path
from typing import Any, Iterable

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import clientdb_sql

MIGRATION_PATH = TOOLS_DIR / "sql" / "migrations" / "0043_notification_state.sql"

BELL_DAYS = 3
AUTO_DISMISS_DAYS = 7
BOARD_LIMIT = 300

STATES = ("dismissed", "hidden", "active")
SHARED_KEY = "*"
AUTO_BY = "automatic"

STATUS_BELL, STATUS_BOARD, STATUS_DISMISSED, STATUS_HIDDEN = "bell", "board", "dismissed", "hidden"

class NotificationError(ValueError):
    pass




def parse_utc(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def utc_text(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def status_for(created: Any, state: str, *, now: dt.datetime) -> tuple[str, bool]:
    if state == "dismissed":
        return STATUS_DISMISSED, False
    if state == "hidden":
        return STATUS_HIDDEN, False
    when = parse_utc(created)
    age = (now - when) if when else dt.timedelta(0)
    if age <= dt.timedelta(days=BELL_DAYS):
        return STATUS_BELL, False
    if state != "active" and age > dt.timedelta(days=AUTO_DISMISS_DAYS):
        return STATUS_DISMISSED, True
    return STATUS_BOARD, False



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
    _ensured.add(key)


def user_key(remote_user: str) -> str:
    return " ".join(str(remote_user or "").split()).lower()[:120] or "shared"


def read_states(user: str) -> dict[str, dict[str, Any]]:
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cur = conn.cursor()
        cur.execute("SELECT nid, state, set_by, set_utc, auto FROM notification_state WHERE user_key = ?", (user_key(user),))
        return {str(r[0]): {"state": str(r[1]), "set_by": str(r[2]), "set_utc": str(r[3]), "auto": bool(r[4])} for r in cur.fetchall()}


def set_state(user: str, nid: str, state: str, *, by: str = "", now: dt.datetime | None = None) -> dict[str, Any]:
    if state not in STATES:
        raise NotificationError(f"state must be one of {', '.join(STATES)}")
    key = " ".join(str(nid or "").split())[:200]
    if not key:
        raise NotificationError("nid is required")
    stamp = utc_text(now or dt.datetime.now(dt.timezone.utc))
    who = " ".join(str(by or "").split())[:80]
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        conn.cursor().execute(
            "INSERT INTO notification_state (user_key, nid, state, set_by, set_utc, auto) VALUES (?, ?, ?, ?, ?, 0) "
            "ON CONFLICT (user_key, nid) DO UPDATE SET state = excluded.state, set_by = excluded.set_by, set_utc = excluded.set_utc, auto = 0",
            (user_key(user), key, state, who, stamp),
        )
    return {"nid": key, "state": state, "set_by": who, "set_utc": stamp}


def record_auto_dismissals(user: str, nids: Iterable[str], *, now: dt.datetime | None = None) -> int:
    wanted = sorted({str(n) for n in nids if str(n)})
    if not wanted:
        return 0
    stamp = utc_text(now or dt.datetime.now(dt.timezone.utc))
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cur = conn.cursor()
        for nid in wanted:
            cur.execute(
                "INSERT INTO notification_state (user_key, nid, state, set_by, set_utc, auto) VALUES (?, ?, 'dismissed', ?, ?, 1) "
                "ON CONFLICT (user_key, nid) DO NOTHING",
                (user_key(user), nid, AUTO_BY, stamp),
            )
    return len(wanted)


def first_seen(nids: Iterable[str], *, now: dt.datetime | None = None) -> dict[str, str]:
    wanted = sorted({str(n) for n in nids if str(n)})
    if not wanted:
        return {}
    stamp = utc_text(now or dt.datetime.now(dt.timezone.utc))
    out: dict[str, str] = {}
    with clientdb_sql.get_connection() as conn:
        ensure_tables(conn)
        cur = conn.cursor()
        for start in range(0, len(wanted), 400):
            chunk = wanted[start:start + 400]
            cur.execute(
                f"SELECT nid, set_utc FROM notification_state WHERE user_key = ? AND state = 'seen' AND nid IN ({', '.join('?' for _ in chunk)})",
                (SHARED_KEY, *chunk),
            )
            out.update({str(r[0]): str(r[1]) for r in cur.fetchall()})
        for nid in wanted:
            if nid not in out:
                cur.execute(
                    "INSERT INTO notification_state (user_key, nid, state, set_by, set_utc, auto) VALUES (?, ?, 'seen', ?, ?, 0) "
                    "ON CONFLICT (user_key, nid) DO NOTHING",
                    (SHARED_KEY, nid, AUTO_BY, stamp),
                )
                out[nid] = stamp
    return out




def _short(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def obligation_nid(row: dict[str, Any]) -> str:
    return f"o:{row.get('matter_id') or ''}:{_short(str(row.get('label') or '') + '|' + str(row.get('client') or ''))}"


def _note(nid: str, source: str, category: str, created: str, matter_id: Any, client: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "nid": nid,
        "source": source,
        "category": category,
        "created": created,
        "matter_id": str(matter_id or ""),
        "client": client,
        "item": item,
    }


def collect(
    *,
    attention: dict[str, Any] | None,
    replies: dict[str, Any] | None,
    recent_intakes: list[dict[str, Any]] | None,
    new_client_matters: set[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    att = attention or {}
    buckets = ("red", "yellow", "green", "scope_creep", "counsel_accepted", "counsel_rejected", "court_order", "court_rejected")
    seen_ids: set[str] = set()
    for bucket in buckets:
        for row in att.get(bucket) or []:
            task_id = str(row.get("task_id") or "")
            if not task_id or task_id in seen_ids:
                continue
            seen_ids.add(task_id)
            kind = str(row.get("kind") or "")
            category = "task" if kind in ("update", "") else kind
            if kind == "switchboard":
                category = "switchboard"
            elif kind == "complaint" and row.get("severity") == "soft":
                category = "soft_complaint"
            out.append(_note(f"t:{task_id}", "attention", category, str(row.get("created") or ""), row.get("matter_id"), str(row.get("who") or ""), row))
    for row in att.get("obligations") or []:
        out.append(_note(obligation_nid(row), "obligation", "obligation", "", row.get("matter_id"), str(row.get("client") or ""), row))
    for row in (replies or {}).get("items") or []:
        state = str(row.get("state") or "")
        category = "statement_approved" if state == "approved" else "statement_amend"
        nid = f"s:{row.get('matter_id')}:{state}:{row.get('recorded_utc') or ''}"
        out.append(_note(nid, "statement", category, str(row.get("recorded_utc") or ""), row.get("matter_id"), str(row.get("client_name") or ""), row))
    for row in recent_intakes or []:
        mid = str(row.get("matter_id") or "")
        if not mid or mid in new_client_matters:
            continue
        out.append(_note(f"n:{mid}", "new_matter", "new_client", str(row.get("created_utc") or ""), mid, str(row.get("client_name") or ""), row))
    return out


ALWAYS_URGENT_KINDS = frozenset({"complaint", "settlement", "counsel_accepted", "counsel_rejected", "court_order", "court_rejected"})


def rings_bell(note: dict[str, Any]) -> bool:
    if note.get("source") != "attention":
        return True
    item = note.get("item") or {}
    kind = str(item.get("kind") or "")
    if kind == "new_client":
        return True
    if kind == "complaint" and item.get("severity") != "soft":
        return True
    if kind in ALWAYS_URGENT_KINDS - {"complaint"}:
        return True
    if str(item.get("label") or "").strip().upper() == "NEW REFERRAL":
        return True
    return str(item.get("importance") or "") == "high"


def classify(notes: list[dict[str, Any]], states: dict[str, dict[str, Any]], *, now: dt.datetime, dated: dict[str, str] | None = None) -> list[dict[str, Any]]:
    dated = dated or {}
    out = []
    for note in notes:
        row = states.get(note["nid"]) or {}
        state = str(row.get("state") or "")
        created = note["created"] or dated.get(note["nid"], "")
        status, auto = status_for(created, state, now=now)
        if status == STATUS_BELL and not rings_bell(note):
            status = STATUS_BOARD
        out.append({
            **note,
            "created": created,
            "status": status,
            "auto_dismissed": auto or (status == STATUS_DISMISSED and bool(row.get("auto"))),
            "state_by": str(row.get("set_by") or ""),
            "state_utc": str(row.get("set_utc") or ""),
        })
    out.sort(key=lambda n: n["created"] or "", reverse=True)
    return out


def summarise(notes: list[dict[str, Any]]) -> dict[str, int]:
    counts = {STATUS_BELL: 0, STATUS_BOARD: 0, STATUS_DISMISSED: 0, STATUS_HIDDEN: 0}
    for note in notes:
        counts[note["status"]] += 1
    return counts


def view(
    user: str,
    sources: dict[str, Any],
    *,
    scope: str = "bell",
    now: dt.datetime | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    moment = now or dt.datetime.now(dt.timezone.utc)
    notes = collect(**sources)
    dateless = [n["nid"] for n in notes if not n["created"]]
    dated = first_seen(dateless, now=moment) if persist else {}
    states = read_states(user)
    classified = classify(notes, states, now=moment, dated=dated)
    if persist:
        record_auto_dismissals(user, [n["nid"] for n in classified if n["auto_dismissed"] and n["nid"] not in states], now=moment)
    counts = summarise(classified)
    out: dict[str, Any] = {"now": utc_text(moment), "bell_days": BELL_DAYS, "auto_dismiss_days": AUTO_DISMISS_DAYS, "counts": counts}
    if scope == "bell":
        out["bell"] = [n for n in classified if n["status"] == STATUS_BELL]
        return out
    out["bell"] = [n for n in classified if n["status"] == STATUS_BELL]
    for status in (STATUS_BOARD, STATUS_DISMISSED, STATUS_HIDDEN):
        out[status] = [n for n in classified if n["status"] == status][:BOARD_LIMIT]
    return out




def robot_view(*, notices: list[dict[str, Any]], resolved: list[dict[str, Any]], ops: dict[str, Any] | None) -> dict[str, Any]:
    alerts = [a for a in (ops or {}).get("alerts") or [] if a.get("severity") != "green"]
    return {
        "open": notices,
        "resolved": resolved,
        "ops": {
            "available": bool((ops or {}).get("available")),
            "stale": bool((ops or {}).get("stale", True)),
            "overall_severity": str((ops or {}).get("overall_severity") or "unknown"),
            "generated_at": str((ops or {}).get("generated_at") or ""),
            "alerts": alerts,
        },
    }
