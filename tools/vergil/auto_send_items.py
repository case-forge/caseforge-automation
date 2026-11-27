from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Callable

LEAVING_SOON, LEFT, CANCELLED, BLOCKED = "leaving_soon", "left", "cancelled", "blocked"
LOOKBACK_DAYS = 30
BLOCKED_DAYS = 7
COUNTDOWN_GRACE = dt.timedelta(minutes=17)
_NOT_ARMED = "not armed: "

CLASS_LABELS = {
    "Letter of Authority & Statement for Signature": "First statement email",
    "Your Witness Statement for Signature": "Statement for signature",
    "Your Amended Statement for Signature": "Amended statement",
}


def _parse(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _z(value: Any) -> str:
    parsed = _parse(value)
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if parsed else ""


def _recipients(raw: Any) -> list[str]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


CLASS_NAMES = {"court-application-chaser": "Court chaser (8am)"}


def _label(subject: str, mail_class: str) -> str:
    return CLASS_LABELS.get(subject.strip(), CLASS_NAMES.get(mail_class, mail_class or "Email"))


def _blocked_reason(row: dict[str, Any], effective: Callable[[str], bool]) -> str:
    note = str(row.get("arm_note") or "").strip()
    if note.startswith(_NOT_ARMED):
        note = note[len(_NOT_ARMED):].strip()
    if note and note != "arming":
        return note[:280]
    if note == "arming":
        return "Being armed now, or arming was interrupted"
    return "Waiting to be armed" if effective(str(row["matter_id"])) else "Case flow is on Manual for this client"


def build_items(
    rows: list[dict[str, Any]], names: dict[str, str], *, effective: Callable[[str], bool], now: dt.datetime | None = None
) -> list[dict[str, Any]]:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    items: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("status") or "")
        created = _parse(row.get("created_utc"))
        armed, sends = _parse(row.get("armed_utc")), _parse(row.get("sends_at"))
        sent = _parse(row.get("sent_utc"))
        subject = str(row.get("subject") or "")
        item = {
            "id": str(row["draft_id"]),
            "matter_id": str(row["matter_id"]),
            "client_name": names.get(str(row["matter_id"]), ""),
            "subject": subject,
            "recipients": _recipients(row.get("recipients")),
            "class": _label(subject, str(row.get("class") or "")),
            "armed_utc": _z(armed),
            "leaves_utc": _z(sends),
            "sent_utc": "",
            "stopped_utc": "",
            "stopped_reason": "",
            "body_text": "",
            "outlook_link": str(row.get("web_link") or ""),
            "sharepoint_link": "",
        }
        if status == "sent" and armed:
            item.update(state=LEFT, sent_utc=_z(sent))
        elif status == "sent":
            reason = _blocked_reason(row, lambda _m: False) if str(row.get("arm_note") or "").strip() else "Not armed"
            item.update(state=BLOCKED, sent_utc=_z(sent), stopped_reason=f"{reason}. Sent by a person.", stopped_utc=_z(sent))
        elif status == "stopped":
            item.update(state=CANCELLED, stopped_utc=_z(sends or created), stopped_reason=str(row.get("stopped_reason") or "Stopped"))
        elif status == "draft" and armed:
            if sends and now <= sends + COUNTDOWN_GRACE:
                item.update(state=LEAVING_SOON)
            else:
                item.update(state=CANCELLED, stopped_utc=_z(sends), stopped_reason="The countdown ended and it did not leave")
        elif status == "draft":
            if created and now - created > dt.timedelta(days=BLOCKED_DAYS):
                continue
            item.update(state=BLOCKED, stopped_utc=_z(created), stopped_reason=_blocked_reason(row, effective))
        else:
            continue
        items.append(item)
    return items


def load_items(*, db_path: str | Path | None = None, now: dt.datetime | None = None) -> list[dict[str, Any]]:
    import ops_db

    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = (now - dt.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with ops_db.connect(db_path) as conn:
            conn.row_factory = None
            cur = conn.execute(
                "SELECT matter_id, class, draft_id, subject, recipients, web_link, created_utc, sent_utc, status, stopped_reason, "
                "armed_utc, sends_at, arm_note FROM pipeline_sent_watch WHERE auto_send = 1 AND created_utc >= ? ORDER BY watch_id",
                (cutoff,),
            )
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:
        return []
    names: dict[str, str] = {}
    try:
        import clientdb_sql

        found = clientdb_sql.get_clients_by_matter_ids(sorted({str(r["matter_id"]) for r in rows}))
        names = {str(k): str((v or {}).get("client_name") or "") for k, v in (found or {}).items()}
    except Exception:
        names = {}
    try:
        from onboarding import pipeline as pl

        effective: Callable[[str], bool] = lambda m: pl.effective_mode(m, db_path=db_path) == "auto"
    except Exception:
        effective = lambda m: False
    return build_items(rows, names, effective=effective, now=now)
