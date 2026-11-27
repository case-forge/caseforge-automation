
from __future__ import annotations

import re
from typing import Any, Mapping

from agwu.client_rows import clean_text

LEGAL_AID_ALERT_CATEGORIES = {"legal aid confirmation", "ccms allocation"}
LEGAL_AID_ALERT_PATTERNS = (
    re.compile(r"\bapply\s+for\s+civil\s+legal\s+aid\b", re.I),
    re.compile(r"\blaa\s*online\b.*\bccms\s*submi+s{1,2}ions?\s+confirmation\b", re.I),
    re.compile(r"\bccms\s*submi+s{1,2}ions?\s+confirmation\b", re.I),
    re.compile(r"\bwe(?:'|’)ve\s+received\s+your\s+application\b", re.I),
    re.compile(r"\bapplication\s+(?:has\s+been\s+)?(?:submitted|received)\b", re.I),
)


def graph_row_needs_legal_aid_signature(row: Mapping[str, Any]) -> bool:
    category = clean_text(row.get("category")).lower()
    if category not in LEGAL_AID_ALERT_CATEGORIES:
        return False
    text = " ".join(
        clean_text(row.get(field))
        for field in ("subject", "from", "to", "cc")
        if clean_text(row.get(field))
    )
    return any(pattern.search(text) for pattern in LEGAL_AID_ALERT_PATTERNS)


def startup_signature_alerts(graph_payload: Mapping[str, Any], *, limit: int = 5) -> list[dict[str, str]]:
    alerts_by_client: dict[str, dict[str, str]] = {}
    for row in graph_payload.get("rows") or []:
        if not isinstance(row, Mapping) or not graph_row_needs_legal_aid_signature(row):
            continue
        client = clean_text(row.get("client_match"))
        if not client:
            continue
        key = client.lower()
        current = alerts_by_client.get(key)
        received = clean_text(row.get("received_utc"))
        if current and clean_text(current.get("received_utc")) >= received:
            continue
        alerts_by_client[key] = {
            "client": client,
            "subject": clean_text(row.get("subject")),
            "received_utc": received,
            "message_id": clean_text(row.get("message_id")),
            "web_link": clean_text(row.get("web_link")),
        }
    alerts = sorted(alerts_by_client.values(), key=lambda item: item.get("received_utc", ""), reverse=True)
    return alerts[: max(1, min(int(limit or 5), 20))]
