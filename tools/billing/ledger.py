
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def normalise_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(value).lower()).strip()


def sender_address(message: dict[str, Any]) -> str:
    for field in ("from", "sender"):
        row = message.get(field)
        if not isinstance(row, dict):
            continue
        email = row.get("emailAddress")
        if isinstance(email, dict):
            address = clean_text(email.get("address") or "").lower()
            if address:
                return address
    return ""


def direction_from_sender(message: dict[str, Any]) -> str:
    from email_sorter_common import is_firm_sent

    known = clean_text(message.get("_direction") or "").lower()
    if known in ("out", "sent", "sentitems"):
        return "out"
    if known in ("in", "inbox"):
        return "in"
    return "out" if is_firm_sent(message) else "in"


def billing_group(category: str, target_folder: str = "") -> str:
    folder_name = str(target_folder or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    key = normalise_key(" ".join([category, folder_name]))
    if "other side" in key or "respondent" in key:
        return "other_side"
    if "counsel" in key or "barrister" in key:
        return "counsel"
    if "court" in key and "process server" not in key:
        return "court"
    if "laa" in key or "legal aid" in key or "ccms" in key:
        return "laa"
    if "process server" in key or "drug" in key or "gp" in key or "school" in key or "police" in key or "referralpartner" in key:
        return "other"
    if "client" in key:
        return "client"
    return "other"


def _resolve_matter_id(client_name: str) -> str:
    import agwu

    result = agwu.resolve_client(client_name, limit=2, caller="ai_exp_billing.record_ledger_item")
    top = result.top
    if result.status != "resolved" or top is None or "exact_search" not in top.match_sources:
        return ""
    return clean_text(top.row.get("matter_id"))


def _ledger_date(message: dict[str, Any], direction: str) -> str:
    import datetime as dt

    raw = clean_text(message.get("sentDateTime" if direction == "out" else "receivedDateTime"))
    try:
        when = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        when = dt.datetime.now(dt.timezone.utc)
    return when.strftime("%d.%m.%y")


def record_ledger_item(*, client_name: str, group: str, direction: str, message: dict[str, Any]) -> dict[str, Any]:
    if not clean_text(message.get("internetMessageId") or message.get("id")):
        return {"status": "skipped", "reason": "no_message_id"}
    try:
        matter_id = _resolve_matter_id(client_name)
    except Exception as exc:
        return {"status": "skipped", "reason": "error", "error": type(exc).__name__}
    if not matter_id:
        return {"status": "skipped", "reason": "no_matter_id"}
    return record_ledger_for_matter(matter_id=matter_id, client_name=client_name, group=group, direction=direction, message=message)


def is_court_email(message: dict[str, Any], direction: str) -> bool:
    if direction != "out":
        return False
    from onboarding.matter_court import is_court_address

    for to in message.get("toRecipients") or []:
        address = clean_text(((to or {}).get("emailAddress") or {}).get("address"))
        if address and is_court_address(address):
            return True
    return False


def record_court_email_ledger(
    *, matter_id: str, client_name: str, group: str, message: dict[str, Any], attachment_count: int,
    skip_attachments: int = 0, document_url: str = "",
) -> dict[str, Any]:
    try:
        message_id = clean_text(message.get("internetMessageId") or message.get("id"))
        if not message_id or not clean_text(matter_id):
            return {"status": "skipped", "reason": "no_message_id" if not message_id else "no_matter_id"}
        from billing import billing_items

        base = "email:" + hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:24]
        date = _ledger_date(message, "out")
        keys = [base] + [f"{base}:att{i}" for i in range(1, max(0, int(attachment_count) - int(skip_attachments)) + 1)]
        recorded = []
        for key in keys:
            row = billing_items.record_correspondence_item(
                matter_id=matter_id, item_date=date, direction="out", party=group, dedupe_key=key, client_name=client_name,
            )
            if row is not None:
                recorded.append(row["item_id"])
                if document_url and key == base:
                    billing_items.set_document_url(row["item_id"], document_url)
        return {"status": "recorded" if recorded else "duplicate", "letters_out": len(recorded), "item_ids": recorded}
    except Exception as exc:
        return {"status": "skipped", "reason": "error", "error": type(exc).__name__}


def record_ledger_for_matter(*, matter_id: str, client_name: str, group: str, direction: str, message: dict[str, Any], pages: int | None = None, document_url: str = "", auto_reply: bool = False) -> dict[str, Any]:
    try:
        message_id = clean_text(message.get("internetMessageId") or message.get("id"))
        if not message_id:
            return {"status": "skipped", "reason": "no_message_id"}
        if not clean_text(matter_id):
            return {"status": "skipped", "reason": "no_matter_id"}
        from billing import billing_items

        from billing import letter_notes

        if auto_reply:
            letter = billing_items.record_correspondence_item(
                matter_id=matter_id, item_date=_ledger_date(message, direction), direction=direction, party=group,
                dedupe_key="email:" + hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:24], client_name=client_name,
            )
            if letter is None:
                return {"status": "duplicate"}
            if document_url:
                billing_items.set_document_url(letter["item_id"], document_url)
            return {"status": "recorded", "item_id": letter["item_id"], "auto_reply": True}
        done = letter_notes.record_letter_with_note(
            matter_id=matter_id,
            item_date=_ledger_date(message, direction),
            direction=direction,
            party=group,
            dedupe_key="email:" + hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:24],
            pages=pages,
            client_name=client_name,
            document_url=document_url,
        )
        row = done["letter"]
        if row is None:
            return {"status": "duplicate", **({"note_item_id": done["note"]["item_id"]} if done["note"] else {})}
        return {"status": "recorded", "item_id": row["item_id"], **({"note_item_id": done["note"]["item_id"]} if done["note"] else {})}
    except Exception as exc:
        return {"status": "skipped", "reason": "error", "error": type(exc).__name__}
