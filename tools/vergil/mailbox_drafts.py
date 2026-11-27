from __future__ import annotations

import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

CACHE_TTL_SECONDS = 60
DRAFTS_LIMIT = 50
AI_TAG = "ai drafted"
_REFERENCE_RE = re.compile(r"\b\d{6}/\d{2}[A-Z]{2}\b")
_SELECT = "id,subject,toRecipients,ccRecipients,createdDateTime,hasAttachments,categories,webLink,isDraft"
_DEFERRED_SEND_PROPERTY = "SystemTime 0x3FEF"
_EXPAND = f"attachments($select=id),singleValueExtendedProperties($filter=id eq '{_DEFERRED_SEND_PROPERTY}')"
_UNSCHEDULED_FROM_YEAR = 4000

_cache: dict[str, Any] = {"at": 0.0, "result": None}


def _client():
    from agents.onboarding_loa import graph_mail_client_from_env

    return graph_mail_client_from_env()


def _names(rows: list[dict[str, Any]] | None) -> list[str]:
    out = []
    for row in rows or []:
        email = (row or {}).get("emailAddress") or {}
        name = str(email.get("name") or "").strip()
        address = str(email.get("address") or "").strip()
        out.append("" if not name or name.lower() == address.lower() else name)
    return out


def _addresses(rows: list[dict[str, Any]] | None) -> list[str]:
    return [str(((row or {}).get("emailAddress") or {}).get("address") or "").strip().lower() for row in rows or []]


def _record_for_message(message_id: str) -> dict[str, str]:
    try:
        from usage import output_feedback

        with sqlite3.connect(output_feedback.current_db_path()) as conn:
            row = conn.execute(
                "SELECT matter_ref, client_name FROM outputs WHERE path_or_message_id = ? ORDER BY id DESC LIMIT 1", (message_id,)
            ).fetchone()
    except Exception:
        return {}
    return {"matter_ref": str(row[0] or ""), "client_name": str(row[1] or "")} if row else {}


def _matter_by_reference(reference: str) -> tuple[str, str]:
    import clientdb_sql

    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT matter_id, canonical_name FROM dbo.matters WHERE company_reference = ?", (reference,))
        rows = cur.fetchall()
    return (str(rows[0][0]), str(rows[0][1] or "")) if len(rows) == 1 else ("", "")


def _matter_by_party_email(addresses: list[str]) -> tuple[str, str]:
    import clientdb_sql

    found: set[tuple[str, str]] = set()
    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        for address in [a for a in addresses if a]:
            cur.execute(
                "SELECT p.matter_id, m.canonical_name FROM dbo.matter_parties p JOIN dbo.matters m ON m.matter_id = p.matter_id "
                "WHERE lower(p.email_primary) = ?",
                (address,),
            )
            found.update((str(r[0]), str(r[1] or "")) for r in cur.fetchall())
    return next(iter(found)) if len(found) == 1 else ("", "")


def _matter_for(message: dict[str, Any]) -> tuple[str, str]:
    try:
        record = _record_for_message(str(message.get("id") or ""))
        ref = record.get("matter_ref", "")
        if ref.isdigit():
            return ref, record.get("client_name", "")
        match = _REFERENCE_RE.search(ref) or _REFERENCE_RE.search(str(message.get("subject") or ""))
        if match:
            found = _matter_by_reference(match.group(0))
            if found[0]:
                return found
        return _matter_by_party_email(_addresses(message.get("toRecipients")) + _addresses(message.get("ccRecipients")))
    except Exception:
        return "", ""


def scheduled_send(message: dict[str, Any]) -> str:
    for prop in message.get("singleValueExtendedProperties") or []:
        if str((prop or {}).get("id") or "").lower() != _DEFERRED_SEND_PROPERTY.lower():
            continue
        value = str((prop or {}).get("value") or "").strip()
        match = re.match(r"(\d{4})-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value)
        if match and int(match.group(1)) < _UNSCHEDULED_FROM_YEAR:
            return match.group(0) + "Z"
    return ""


def _is_ai_drafted(message: dict[str, Any]) -> bool:
    return AI_TAG in {str(c).strip().lower() for c in message.get("categories") or []}


def _row(message: dict[str, Any]) -> dict[str, Any]:
    matter_id, client_name = _matter_for(message)
    attachments = message.get("attachments")
    scheduled = scheduled_send(message)
    return {
        "id": str(message.get("id") or ""),
        "subject": " ".join(str(message.get("subject") or "").split()),
        "recipients": _names(message.get("toRecipients")),
        "cc": _names(message.get("ccRecipients")),
        "matter_id": matter_id,
        "client_name": client_name,
        "created_utc": str(message.get("createdDateTime") or ""),
        "attachment_count": len(attachments) if isinstance(attachments, list) else (1 if message.get("hasAttachments") else 0),
        "web_link": str(message.get("webLink") or ""),
        "scheduled_utc": scheduled,
        "human_touched": bool(scheduled),
    }


def list_drafts(*, client: Any = None) -> dict[str, Any]:
    now = time.monotonic()
    if client is None and _cache["result"] is not None and now - _cache["at"] < CACHE_TTL_SECONDS:
        return _cache["result"]
    if client is None and not os.getenv("GRAPH_MAILBOX_UPN", "").strip():
        return {"configured": False, "count": 0, "scheduled_count": 0, "items": []}
    graph = client or _client()
    payload = graph.graph(
        "GET",
        graph.mailbox_path("/mailFolders/drafts/messages"),
        params={
            "$top": str(DRAFTS_LIMIT),
            "$orderby": "createdDateTime desc",
            "$select": _SELECT,
            "$expand": _EXPAND,
        },
    )
    rows = [_row(m) for m in payload.get("value", []) or [] if isinstance(m, dict) and _is_ai_drafted(m)]
    rows.sort(key=lambda r: (not r["scheduled_utc"], r["scheduled_utc"]))
    result = {"configured": True, "count": len(rows), "scheduled_count": sum(1 for r in rows if r["scheduled_utc"]), "items": rows}
    if client is None:
        _cache.update(at=now, result=result)
    return result


def clear_cache() -> None:
    _cache.update(at=0.0, result=None)
