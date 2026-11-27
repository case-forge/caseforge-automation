from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
_C8_KEYS = ("c8_address", "c8_email", "c8_phone")
_C8_CONTACT_COLUMNS = (
    "client_email", "phone_primary", "client_address_text", "client_address_line1", "client_address_line2",
    "client_address_line3", "client_address_line4", "client_address_postcode",
    "address_summary", "applicant_email", "applicant_phone", "email_primary", "client_ni_number", "ni_number",
)


def _c8_known(row: object) -> bool:
    return isinstance(row, dict) and row.get("has_c8") not in (None, "")


def protected_values_for_row(row: dict) -> dict[str, set[str]]:
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from documents import c8_protection

    contact = {
        "address": " ".join(
            str(row.get(k) or "") for k in ("client_address_line1", "client_address_line2", "client_address_line3", "client_address_line4")
        ).strip(),
        "phone": row.get("phone_primary"),
        "email": row.get("client_email"),
    }
    out: dict[str, set[str]] = {"address": set(), "postcode": set(), "phone": set(), "email": set()}
    for found in (
        c8_protection.protected_values(row, contact),
        c8_protection.protected_values(str(row.get("client_address_text") or ""), str(row.get("client_address_postcode") or "")),
    ):
        for kind, values in found.items():
            out[kind] |= values
    return out


def strip_c8_values(payload: dict, matter_id: str = "", *, lookup: Optional[Callable[[str], Optional[dict]]] = None) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from documents import c8_protection

    all_rows = [h for h in (payload.get("sql_hits") or payload.get("rows") or []) if isinstance(h, dict)]
    hits = [h for h in all_rows if _c8_known(h)]
    if not hits and matter_id and lookup is not None:
        try:
            row = lookup(matter_id)
        except Exception as exc:
            print(f"[model_safe] C8 status lookup failed, treating the matter as C8: {type(exc).__name__}", file=sys.stderr)
            row = None
        if _c8_known(row):
            hits = [row]
            payload.setdefault("sql_hits", [])
    unknown = bool(matter_id) and not hits
    protected: dict = {"address": set(), "postcode": set(), "phone": set(), "email": set()}
    for hit in all_rows:
        if _c8_known(hit) and not c8_protection.detect(matter=hit)["c8"]:
            continue
        for kind, values in protected_values_for_row(hit).items():
            protected[kind] |= values
        for column in _C8_CONTACT_COLUMNS:
            if hit.get(column):
                hit[column] = c8_protection.WITHHELD
    for hit in hits:
        if hit not in all_rows and c8_protection.detect(matter=hit)["c8"]:
            for kind, values in protected_values_for_row(hit).items():
                protected[kind] |= values
    any_protected = any(protected.values())
    withheld = c8_protection.WITHHELD

    def scrub(text: str) -> str:
        if unknown:
            text = c8_protection.EMAIL_RE.sub(withheld, text)
            text = c8_protection.PHONE_RE.sub(withheld, text)
            return c8_protection.POSTCODE_RE.sub(withheld, text)
        return c8_protection.redact_text(text, protected) if any_protected else text

    def walk(node):
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items() if k not in _C8_KEYS}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            return scrub(node)
        return node

    return walk(payload)


