#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from env_bootstrap import load_repo_secrets


LEADING_WITHHELD_RE = re.compile(
    r"^\s*(?:"
    r"w\s*[./\\-]\s*h(?:old)?"
    r"|w\s+h(?:old)?"
    r"|w\s+hold"
    r"|whold"
    r"|withheld"
    r"|withhold"
    r"|c8"
    r"|confidential"
    r"|protected"
    r")\b",
    re.IGNORECASE,
)
CONTACT_LABEL_RE = re.compile(
    r"^\s*(?:address|addr|add|phone|telephone|tel|number|mobile|email|e-mail|mail)\b\s*",
    re.IGNORECASE,
)
SEPARATOR_RE = re.compile(r"^\s*[:;.,/\\-]+\s*")
NO_CONTACT_AFTER_MARKER_RE = re.compile(
    r"^(?:by|under|per|due|because|for|c8|confidential|protected|address|phone|email)\b",
    re.IGNORECASE,
)
APPLICANT_ROLES = {"applicant", "client", "primary", "protected party"}
WITHHELD_LABELS = {
    "address_text": "Applicant address",
    "phone_primary": "Applicant phone",
    "email_primary": "Applicant email",
}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def sha8(value: Any) -> str:
    text = str(value or "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8] if text else ""


def phone_digits(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if digits.startswith("44") and len(digits) == 12:
        return "0" + digits[2:]
    return digits


def normalise_role(value: Any) -> str:
    return re.sub(r"[^a-z ]+", " ", str(value or "").lower()).strip()


def is_applicant_role(value: Any) -> bool:
    role = normalise_role(value)
    return role in APPLICANT_ROLES or "applicant" in role or "client" in role


def split_withheld_fields(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    lowered = text.lower()
    labels: list[str] = []
    if "address" in lowered:
        labels.append("Applicant address")
    if "phone" in lowered or "number" in lowered or "mobile" in lowered:
        labels.append("Applicant phone")
    if "email" in lowered or "e-mail" in lowered or "mail" in lowered:
        labels.append("Applicant email")
    raw_parts = [clean_text(part) for part in re.split(r"[;,|]", text) if clean_text(part)]
    for part in raw_parts:
        if part.lower() in {"address", "phone", "number", "email", "address withheld", "number withheld", "email withheld"}:
            continue
        if part not in labels and part.lower() not in {label.lower() for label in labels}:
            labels.append(part)
    return labels


def merge_withheld_fields(existing: Any, labels: Iterable[str]) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for label in [*split_withheld_fields(existing), *labels]:
        clean = clean_text(label)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(clean)
    return "; ".join(merged)


def strip_leading_withheld_marker(value: Any) -> tuple[str, bool]:
    text = clean_text(value)
    if not text:
        return "", False
    match = LEADING_WITHHELD_RE.match(text)
    if not match:
        return text, False
    rest = text[match.end() :]
    marker = match.group(0).strip().lower()
    bare_wh = bool(re.fullmatch(r"w\s+h(?:old)?", marker, flags=re.IGNORECASE))
    ambiguous_bare = marker in {"c8", "confidential", "protected"}
    had_label = bool(CONTACT_LABEL_RE.match(rest))
    had_separator = bool(SEPARATOR_RE.match(rest))
    rest = CONTACT_LABEL_RE.sub("", rest)
    rest = SEPARATOR_RE.sub("", rest)
    rest = clean_text(rest)
    if bare_wh and not had_label and not had_separator and rest and not rest[0].isdigit():
        return text, False
    if not rest or NO_CONTACT_AFTER_MARKER_RE.match(rest):
        return "", True
    second = LEADING_WITHHELD_RE.match(rest)
    if second:
        return "", True
    if ambiguous_bare and not had_label:
        return text, False
    return rest, True


def column_exists(cursor: Any, table: str, column: str, *, sqlite_mode: bool) -> bool:
    if sqlite_mode:
        cursor.execute(f"PRAGMA table_info({table})")
        return any(str(row[1]) == column for row in cursor.fetchall())
    cursor.execute(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ? AND COLUMN_NAME = ?
        """,
        (table, column),
    )
    return cursor.fetchone() is not None


def execute(cursor: Any, sql: str, params: Iterable[Any] = ()) -> None:
    values = tuple(params)
    try:
        cursor.execute(sql, values)
    except TypeError:
        cursor.execute(sql, *values)


def row_dict(cursor: Any, row: Any) -> dict[str, Any]:
    cols = [col[0] for col in cursor.description]
    return dict(zip(cols, row))


def matter_parties(cursor: Any, *, sqlite_mode: bool) -> list[dict[str, Any]]:
    table = "matter_parties" if sqlite_mode else "dbo.matter_parties"
    cursor.execute(
        f"""
        SELECT matter_party_id, matter_id, role, address_text, phone_primary, email_primary
        FROM {table}
        WHERE NULLIF(address_text, '') IS NOT NULL
           OR NULLIF(phone_primary, '') IS NOT NULL
           OR NULLIF(email_primary, '') IS NOT NULL
        """
    )
    return [row_dict(cursor, row) for row in cursor.fetchall()]


def people_contacts(cursor: Any, *, sqlite_mode: bool) -> list[dict[str, Any]]:
    people = "people" if sqlite_mode else "dbo.people"
    matters = "matters" if sqlite_mode else "dbo.matters"
    cursor.execute(
        f"""
        SELECT p.person_id, p.phone_primary, p.email_primary, m.matter_id
        FROM {people} p
        INNER JOIN {matters} m ON m.primary_person_id = p.person_id
        WHERE NULLIF(p.phone_primary, '') IS NOT NULL
           OR NULLIF(p.email_primary, '') IS NOT NULL
        """
    )
    return [row_dict(cursor, row) for row in cursor.fetchall()]


def matter_flags(cursor: Any, matter_ids: Iterable[Any], *, sqlite_mode: bool) -> dict[str, dict[str, Any]]:
    ids = [str(mid) for mid in dict.fromkeys(str(item) for item in matter_ids if str(item or "").strip())]
    if not ids:
        return {}
    table = "matters" if sqlite_mode else "dbo.matters"
    result: dict[str, dict[str, Any]] = {}
    for mid in ids:
        execute(cursor, f"SELECT matter_id, has_c8, withheld_fields FROM {table} WHERE matter_id = ?", (mid,))
        row = cursor.fetchone()
        if row is not None:
            result[mid] = row_dict(cursor, row)
    return result


def update_matter_flag(
    cursor: Any,
    matter_id: Any,
    withheld_fields: str,
    *,
    sqlite_mode: bool,
) -> None:
    table = "matters" if sqlite_mode else "dbo.matters"
    updated_expr = "datetime('now')" if sqlite_mode else "SYSUTCDATETIME()"
    execute(
        cursor,
        f"""
        UPDATE {table}
        SET has_c8 = 1,
            withheld_fields = ?,
            updated_utc = {updated_expr}
        WHERE matter_id = ?
        """,
        (withheld_fields, matter_id),
    )


def update_party_field(
    cursor: Any,
    row: dict[str, Any],
    field: str,
    cleaned: str,
    *,
    sqlite_mode: bool,
) -> None:
    table = "matter_parties" if sqlite_mode else "dbo.matter_parties"
    assignments = [f"{field} = ?"]
    params: list[Any] = [cleaned or None]
    if field == "phone_primary":
        assignments.append("phone_digits = ?")
        digits = phone_digits(cleaned)
        params.append(digits or None)
        if column_exists(cursor, "matter_parties", "phone_digits_key", sqlite_mode=sqlite_mode):
            assignments.append("phone_digits_key = ?")
            params.append(digits)
    elif field == "email_primary":
        cleaned = cleaned.lower()
        params[0] = cleaned or None
        if column_exists(cursor, "matter_parties", "email_primary_key", sqlite_mode=sqlite_mode):
            assignments.append("email_primary_key = ?")
            params.append(cleaned)
    assignments.append("updated_utc = " + ("datetime('now')" if sqlite_mode else "SYSUTCDATETIME()"))
    params.append(row["matter_party_id"])
    execute(
        cursor,
        f"UPDATE {table} SET {', '.join(assignments)} WHERE matter_party_id = ?",
        params,
    )


def update_people_field(
    cursor: Any,
    row: dict[str, Any],
    field: str,
    cleaned: str,
    *,
    sqlite_mode: bool,
) -> None:
    table = "people" if sqlite_mode else "dbo.people"
    assignments = [f"{field} = ?"]
    params: list[Any] = [(cleaned.lower() or None) if field == "email_primary" else (cleaned or None)]
    if field == "phone_primary":
        assignments.append("phone_digits = ?")
        params.append(phone_digits(cleaned) or None)
    assignments.append("updated_utc = " + ("datetime('now')" if sqlite_mode else "SYSUTCDATETIME()"))
    params.append(row["person_id"])
    execute(cursor, f"UPDATE {table} SET {', '.join(assignments)} WHERE person_id = ?", params)


def clean_contacts(*, apply: bool = False) -> dict[str, Any]:
    from clientdb_sql import _using_sqlite, get_connection

    with get_connection() as conn:
        sqlite_mode = bool(_using_sqlite())
        cursor = conn.cursor()
        party_rows = matter_parties(cursor, sqlite_mode=sqlite_mode)
        people_rows = people_contacts(cursor, sqlite_mode=sqlite_mode)
        flags = matter_flags(
            cursor,
            [row.get("matter_id") for row in party_rows] + [row.get("matter_id") for row in people_rows],
            sqlite_mode=sqlite_mode,
        )
        party_updates: list[dict[str, Any]] = []
        people_updates: list[dict[str, Any]] = []
        c8_updates: dict[str, set[str]] = {}
        skipped_non_applicant = 0

        for row in party_rows:
            applicant = is_applicant_role(row.get("role"))
            for field in ("address_text", "phone_primary", "email_primary"):
                original = clean_text(row.get(field))
                cleaned, changed = strip_leading_withheld_marker(original)
                if not changed:
                    continue
                if applicant:
                    c8_updates.setdefault(str(row.get("matter_id")), set()).add(WITHHELD_LABELS[field])
                else:
                    skipped_non_applicant += 1
                party_updates.append(
                    {
                        "matter_id": str(row.get("matter_id")),
                        "row_hash": sha8(row.get("matter_party_id")),
                        "role": clean_text(row.get("role")),
                        "field": field,
                        "old_len": len(original),
                        "new_len": len(cleaned),
                        "applicant_role": applicant,
                    }
                )
                if apply:
                    update_party_field(cursor, row, field, cleaned, sqlite_mode=sqlite_mode)

        for row in people_rows:
            for field, label in (("phone_primary", "Applicant phone"), ("email_primary", "Applicant email")):
                original = clean_text(row.get(field))
                cleaned, changed = strip_leading_withheld_marker(original)
                if not changed:
                    continue
                c8_updates.setdefault(str(row.get("matter_id")), set()).add(label)
                people_updates.append(
                    {
                        "matter_id": str(row.get("matter_id")),
                        "row_hash": sha8(row.get("person_id")),
                        "field": field,
                        "old_len": len(original),
                        "new_len": len(cleaned),
                    }
                )
                if apply:
                    update_people_field(cursor, row, field, cleaned, sqlite_mode=sqlite_mode)

        c8_summary: list[dict[str, Any]] = []
        for mid, labels in sorted(c8_updates.items(), key=lambda item: item[0]):
            current = flags.get(mid, {})
            merged = merge_withheld_fields(current.get("withheld_fields"), sorted(labels))
            c8_summary.append(
                {
                    "matter_id": mid,
                    "had_c8": bool(current.get("has_c8")),
                    "labels_added": sorted(labels),
                    "withheld_fields_hash": sha8(merged),
                }
            )
            if apply:
                update_matter_flag(cursor, mid, merged, sqlite_mode=sqlite_mode)

        if not apply:
            try:
                conn.rollback()
            except Exception:
                pass
        return {
            "applied": bool(apply),
            "sqlite_mode": sqlite_mode,
            "party_contact_updates": len(party_updates),
            "people_contact_updates": len(people_updates),
            "matter_c8_updates": len(c8_summary),
            "non_applicant_marker_fields": skipped_non_applicant,
            "party_updates": party_updates[:50],
            "people_updates": people_updates[:50],
            "c8_updates": c8_summary[:50],
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean leading W/H-style markers from SQL contact fields.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-local-sqlite",
        action="store_true",
        help="Allow cleaning the local SQLite mirror. By default the tool forces caseforge-clientdb (Postgres).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_repo_secrets(repo_root=REPO_ROOT, required_keys=())
    if not args.allow_local_sqlite:
        os.environ["CASEFORGE_SQL_DISABLE_LOCAL_SQLITE_DEFAULT"] = "1"
        os.environ.pop("LOCAL_SQLITE_PATH", None)
    result = clean_contacts(apply=bool(args.apply))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
