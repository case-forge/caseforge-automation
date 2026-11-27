#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil_chat.vergil_chat_errors import user_safe_error

from documents.address_utils import normalise_postal_address_lines, postcode_is_last_visible_line
from documents.docx_template_fill import populate_docx_template


APPLICANT_ROLES = {"applicant", "client", "primary", "protected party"}
RESPONDENT_ROLES = {"respondent", "other party", "respondant"}
ENVELOPE_TEMPLATE_PATH = REPO_ROOT / "templates" / "Doc Templates" / "Envelope Address Letter Guide - Template.docx"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def format_manual_address(raw: str) -> dict[str, Any]:
    lines = normalise_postal_address_lines([raw], max_lines=4)
    return {
        "ok": bool(lines),
        "lines": lines,
        "warning": "" if postcode_is_last_visible_line(lines) else "Check postcode before printing.",
    }


def envelope_filename(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "", str(label or "Envelope Address")).strip(" ._-")
    return f"{cleaned or 'Envelope Address'} - Envelope Address Letter Guide.docx"


def envelope_template_data(label: str, lines: list[str]) -> dict[str, str]:
    visible = [str(line).strip() for line in lines if str(line).strip()][:4]
    visible.extend([""] * (4 - len(visible)))
    return {
        "name": str(label or "").strip(),
        "address_line_1": visible[0],
        "address_line_2": visible[1],
        "address_line_3": visible[2],
        "address_line_4": visible[3],
    }


def render_envelope_docx_bytes(label: str, lines: list[str], template_path: Path | None = None) -> bytes:
    template = template_path or ENVELOPE_TEMPLATE_PATH
    if not template.exists():
        raise FileNotFoundError(f"Envelope template not found: {template}")
    with tempfile.TemporaryDirectory(prefix="caseforge-envelope-") as tmp:
        output = Path(tmp) / "envelope-address.docx"
        populate_docx_template(template, output, envelope_template_data(label, lines))
        return output.read_bytes()


def make_envelope_address(query: str, role_choice: str, manual_address: str = "") -> dict[str, Any]:
    role = str(role_choice or "").strip().lower()
    if role == "someone else":
        result = format_manual_address(manual_address)
        if not result["ok"]:
            return {"ok": False, "message": "Enter the address to format."}
        return {"ok": True, "label": "Someone else", **result}
    if len(str(query or "").strip()) < 2:
        return {"ok": False, "message": "Enter a name, email, or reference first."}
    try:
        from clientdb_sql import get_connection
        import agwu
    except Exception as exc:
        return {"ok": False, "message": user_safe_error(exc, "The client database lookup")}
    _result = agwu.resolve_client(query, limit=5, caller="documents.envelope.make_envelope_address")
    rows = [m.row for m in _result.matches]
    if not rows:
        return {"ok": False, "message": f"No client match found for {query}."}
    was_exact = bool(_result.top and "exact_search" in _result.top.match_sources)
    matter = rows[0]
    matter_id = str(matter.get("matter_id") or "").strip()
    if not matter_id:
        return {"ok": False, "message": "Matched matter has no matter_id."}
    parties = _load_parties(get_connection, matter_id)
    picked = pick_party_address(parties, role, has_c8=bool(matter.get("has_c8")))
    if not picked.get("ok"):
        return picked
    matched_name = str(matter.get("client_name") or matter.get("matter_name") or "").strip()
    warning = str(picked.get("warning") or "")
    if not was_exact:
        guess_warning = (
            f"No exact match for '{query}' — this is the closest match"
            + (f", {matched_name}" if matched_name else "")
            + ". Check it is the right client before printing."
        )
        warning = f"{warning} {guess_warning}".strip() if warning else guess_warning
    return {
        "ok": True,
        "label": picked.get("display_name") or role_choice,
        "lines": picked.get("lines") or [],
        "warning": warning,
        "matter_id": matter_id,
        "was_fuzzy_resolved": not was_exact,
        "matched_client_name": matched_name,
    }


def _load_parties(get_connection_func, matter_id: str) -> list[dict[str, Any]]:
    from clientdb_sql import list_parties_with_address

    return list_parties_with_address(matter_id)


def pick_party_address(parties: list[dict[str, Any]], role_choice: str, *, has_c8: bool = False) -> dict[str, Any]:
    role = str(role_choice or "").strip().lower()
    wanted = APPLICANT_ROLES if role in {"applicant", "client"} else RESPONDENT_ROLES
    matches = [
        party for party in parties
        if _normalise_role(str(party.get("role") or "")) in wanted and str(party.get("address_text") or "").strip()
    ]
    shown = "client" if role in {"applicant", "client"} else "opponent" if wanted is RESPONDENT_ROLES else role_choice
    if not matches:
        return {"ok": False, "message": f"No {shown} address is recorded."}
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in matches:
        key = (_squash(row.get("display_name")), _squash(row.get("address_text")))
        unique.setdefault(key, row)
    matches = list(unique.values())
    if len(matches) > 1:
        options = "; ".join(_address_summary(row) for row in matches[:4])
        return {"ok": False, "message": f"More than one {shown} address is recorded: {options}. Correct the record, then print."}
    party = matches[0]
    lines = normalise_postal_address_lines([str(party.get("address_text") or "")], max_lines=4)
    return {
        "ok": bool(lines),
        "display_name": str(party.get("display_name") or "").strip(),
        "lines": lines,
        "warning": _address_warning(lines, has_c8=has_c8, role=role),
    }


def _squash(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _address_summary(row: dict[str, Any]) -> str:
    lines = normalise_postal_address_lines([str(row.get("address_text") or "")], max_lines=4)
    where = f"{lines[0]}, {lines[-1]}" if len(lines) > 1 else (lines[0] if lines else "")
    return f"{str(row.get('display_name') or 'party').strip()} ({where})"


def _address_warning(lines: list[str], *, has_c8: bool = False, role: str = "") -> str:
    warnings = []
    if not postcode_is_last_visible_line(lines):
        warnings.append("Check postcode before printing.")
    if has_c8 and role in {"applicant", "client"}:
        warnings.append("C8: client/applicant address must not be sent to the respondent.")
    return " ".join(warnings)


def _normalise_role(value: str) -> str:
    return re.sub(r"[^a-z ]+", " ", str(value or "").lower()).strip()
