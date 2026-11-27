#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import clientdb_sql

AUTO_REVIEW_PREFIX = "auto:"
_ADDRESS_PARTS = ("address_text", "address_line1", "address_line2", "address_line3", "address_line4", "address_postcode")


def _text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def missing_fields(row: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not any(_text(row.get(part)) for part in _ADDRESS_PARTS):
        missing.append("address")
    if not _text(row.get("phone_primary")) and not _text(row.get("email_primary")):
        missing.append("telephone or email")
    if not _text(row.get("dob_iso")):
        missing.append("date of birth")
    return missing


DEFAULT_LIMIT = 100

_BLANK = "COALESCE(TRIM({col}), '') = ''"


def list_matters_missing_info(limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    with clientdb_sql.get_connection() as conn:
        if clientdb_sql._using_sqlite():
            has_closed = clientdb_sql._sqlite_column_exists(conn, "matters", "closed_at")
            has_text = clientdb_sql._sqlite_column_exists(conn, "people", "address_text")
        else:
            has_closed = has_text = True
        text_expr = "p.address_text" if has_text else "NULL"
        address_blank = " AND ".join(
            _BLANK.format(col=col)
            for col in (text_expr, "p.address_line1", "p.address_line2", "p.address_line3", "p.address_line4", "p.address_postcode")
        )
        contact_blank = " AND ".join(_BLANK.format(col=col) for col in ("p.phone_primary", "p.email_primary"))
        gap = f"(({address_blank}) OR ({contact_blank}) OR {_BLANK.format(col='p.dob_iso')})"
        where = f"WHERE m.closed_at IS NULL AND {gap}" if has_closed else f"WHERE {gap}"
        limit = max(1, int(limit))
        sqlite = clientdb_sql._using_sqlite()
        top_sql = "" if sqlite else f"TOP ({limit})"
        limit_sql = f"LIMIT {limit}" if sqlite else ""
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT {top_sql} m.matter_id, p.dob_iso, p.phone_primary, p.email_primary,
                   {text_expr} AS address_text, p.address_line1, p.address_line2,
                   p.address_line3, p.address_line4, p.address_postcode
            FROM matters m
            JOIN people p ON p.person_id = m.primary_person_id
            {where}
            ORDER BY m.matter_id
            {limit_sql}
            """
        )
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, record)) for record in cursor.fetchall()]
    found = []
    for row in rows:
        missing = missing_fields(row)
        if missing:
            found.append({"matter_id": str(row["matter_id"]), "missing": missing})
    return found


def list_matters_missing_referral(limit: int = DEFAULT_LIMIT) -> list[str]:
    from onboarding.pipeline import markers

    ids = markers.matters_without_referral()
    if not ids:
        return []
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        marks = ", ".join("?" for _ in ids)
        cursor.execute(f"SELECT matter_id FROM matters WHERE closed_at IS NULL AND matter_id IN ({marks})", tuple(ids))
        open_ids = {str(r[0]) for r in cursor.fetchall()}
    return [i for i in ids if i in open_ids][: max(1, int(limit))]


def list_matters_no_folder(limit: int = DEFAULT_LIMIT) -> dict[str, list[str]]:
    from onboarding.pipeline import markers

    found = {reason: markers.matters_unsearchable(reason) for reason in markers.UNSEARCHABLE_REASONS}
    ids = sorted({i for v in found.values() for i in v})
    if not ids:
        return {}
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        marks = ", ".join("?" for _ in ids)
        cursor.execute(f"SELECT matter_id FROM matters WHERE closed_at IS NULL AND matter_id IN ({marks})", tuple(ids))
        open_ids = {str(r[0]) for r in cursor.fetchall()}
    cap = max(1, int(limit))
    return {reason: [i for i in v if i in open_ids][:cap] for reason, v in found.items()}


def no_folder_entry(matter_id: str, reason: str) -> dict[str, Any]:
    from onboarding.pipeline import markers

    label = markers.UNSEARCHABLE_REASONS.get(reason, "No folder recorded")
    return {
        **review_entry({"matter_id": matter_id, "missing": []}),
        "field_name": "no_folder_for_referral",
        "field_label": label,
        "note": label,
    }


def referral_entry(matter_id: str) -> dict[str, Any]:
    return {
        **review_entry({"matter_id": matter_id, "missing": []}),
        "field_name": "missing_referral_form",
        "field_label": "Missing referral form",
        "note": "Missing referral form",
    }


def review_entry(item: dict[str, Any]) -> dict[str, Any]:
    matter_id = str(item["matter_id"])
    return {
        "review_id": f"{AUTO_REVIEW_PREFIX}{matter_id}",
        "matter_id": matter_id,
        "client_name": "",
        "field_name": "missing_information",
        "field_label": "Missing information",
        "value_snapshot": "",
        "note": "Missing: " + ", ".join(item["missing"]),
        "flagged_by": "Automatic",
        "flagged_at": "",
        "resolved_by": None,
        "resolved_at": None,
    }
