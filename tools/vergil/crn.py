#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import re
import subprocess
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

CRN_SUFFIX = "FL"
COMPANY_REF_RE = re.compile(r"\b(\d{6}/\d{2}FL)\b", re.IGNORECASE)
_NOA_FL401_KEYWORDS = ("notice of acting", "noa", "notice_of_acting", "fl401", "fl-401", "fl 401")


class CrnGenerationError(RuntimeError):
    pass


def normalise_company_reference(value: Any) -> str:
    match = COMPANY_REF_RE.search(re.sub(r"\s+", " ", str(value or "")).strip())
    return match.group(1).upper() if match else ""


def _parse_reference_date(*values: Any) -> Optional[dt.date]:
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            continue
        iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})(?!\d)", text)
        if iso:
            try:
                return dt.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
            except ValueError:
                pass
        uk = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d{2}|\d{2})(?!\d)", text)
        if uk:
            year = int(uk.group(3))
            if year < 100:
                year += 2000
            try:
                return dt.date(year, int(uk.group(2)), int(uk.group(1)))
            except ValueError:
                pass
    return None


def _next_company_reference_local(prefix: str, existing_values: Sequence[Any]) -> str:
    max_seq = 0
    pattern = re.compile(rf"^{re.escape(prefix)}/(\d{{2}})FL$", re.IGNORECASE)
    for value in existing_values:
        match = pattern.match(normalise_company_reference(value))
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    return f"{prefix}/{max_seq + 1:02d}FL"


def _row_to_dict(cursor, row) -> dict[str, Any]:
    cols = [col[0] for col in cursor.description]
    return dict(zip(cols, row))


def ensure_company_reference(details: Mapping[str, Any]) -> str:
    existing = normalise_company_reference(details.get("company_reference") or details.get("case_reference"))
    if existing:
        return existing
    matter_id = str(details.get("matter_id") or "").strip()
    if not matter_id:
        raise CrnGenerationError("Cannot generate a CaseForge reference without matter_id.")

    import clientdb_sql

    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()

        if clientdb_sql._using_postgres():
            cursor.execute("SELECT caseforge_ensure_company_reference(?)", (matter_id,))
            row = cursor.fetchone()
            if row and row[0]:
                return str(row[0])
            raise CrnGenerationError(f"Cannot generate a CaseForge reference for matter {matter_id}.")

        cursor.execute(
            """
            SELECT company_reference, referral_sent_at, source_email_sent_at, created_utc
            FROM matters
            WHERE matter_id = ?
            """,
            (matter_id,),
        )
        row = cursor.fetchone()
        db_row = _row_to_dict(cursor, row) if row is not None else {}
        db_ref = normalise_company_reference(db_row.get("company_reference"))
        if db_ref:
            return db_ref

        ref_date = _parse_reference_date(
            details.get("referral_sent_at"),
            details.get("source_email_sent_at"),
            details.get("created_utc"),
            db_row.get("referral_sent_at"),
            db_row.get("source_email_sent_at"),
            db_row.get("created_utc"),
        )
        if ref_date is None:
            raise CrnGenerationError("Cannot generate a CaseForge reference without a referral or created date.")

        prefix = ref_date.strftime("%y%m%d")
        like = f"{prefix}/%FL"
        existing_values: list[Any] = []
        cursor.execute("SELECT company_reference FROM matters WHERE company_reference LIKE ?", (like,))
        existing_values.extend(r[0] for r in cursor.fetchall())
        try:
            cursor.execute(
                "SELECT ref_value FROM matter_references WHERE ref_type = 'company_ref' AND ref_value LIKE ?",
                (like,),
            )
            existing_values.extend(r[0] for r in cursor.fetchall())
        except Exception:
            pass
        new_ref = _next_company_reference_local(prefix, existing_values)
        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

        cursor.execute("UPDATE matters SET company_reference = ? WHERE matter_id = ?", (new_ref, matter_id))
        ref_norm = new_ref.upper()
        try:
            cursor.execute(
                "UPDATE matter_references SET is_primary = 0, updated_utc = ? WHERE matter_id = ? AND ref_type = 'company_ref'",
                (now, matter_id),
            )
            cursor.execute(
                """
                SELECT reference_id
                FROM matter_references
                WHERE matter_id = ? AND ref_type = 'company_ref' AND ref_value_normalised = ?
                """,
                (matter_id, ref_norm),
            )
            ref_row = cursor.fetchone()
            if ref_row is None:
                cursor.execute(
                    """
                    INSERT INTO matter_references (
                        matter_id, ref_type, ref_value, ref_value_normalised, source, notes,
                        is_primary, created_utc, updated_utc
                    ) VALUES (?, 'company_ref', ?, ?, 'notice_of_acting', 'Generated by Notice of Acting tool', 1, ?, ?)
                    """,
                    (matter_id, new_ref, ref_norm, now, now),
                )
            else:
                cursor.execute(
                    """
                    UPDATE matter_references
                    SET ref_value = ?, source = 'notice_of_acting', notes = 'Generated by Notice of Acting tool',
                        is_primary = 1, updated_utc = ?
                    WHERE reference_id = ?
                    """,
                    (new_ref, now, ref_row[0]),
                )
        except Exception as exc:
            raise CrnGenerationError(f"Could not mirror CaseForge reference into matter_references: {exc}") from exc
    return new_ref


def company_references_by_matter_id(matter_ids: Sequence[str]) -> dict[str, str]:
    ids = [str(m).strip() for m in matter_ids if str(m or "").strip()]
    if not ids:
        return {}
    import clientdb_sql

    placeholders = ", ".join("?" for _ in ids)
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT matter_id, company_reference FROM matters WHERE CAST(matter_id AS TEXT) IN ({placeholders})",
            tuple(ids),
        )
        return {
            str(row[0]): normalise_company_reference(row[1])
            for row in cursor.fetchall()
            if normalise_company_reference(row[1])
        }


def _parse_date(raw: Any) -> Optional[dt.date]:
    try:
        ts = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return (ts.replace(tzinfo=dt.timezone.utc) if ts.tzinfo is None else ts).date()


def format_crn(referral_date: dt.date, sequence: int) -> str:
    if sequence < 1:
        raise ValueError(f"sequence must be >= 1, got {sequence}")
    return f"{referral_date.strftime('%y%m%d')}/{sequence:02d}{CRN_SUFFIX}"


def predicted_crns_by_message_id(referrals: list[Mapping[str, Any]]) -> dict[str, str]:
    by_date: dict[dt.date, list[Mapping[str, Any]]] = {}
    for rec in referrals:
        message_id = str(rec.get("message_id") or "").strip()
        referral_date = _parse_date(rec.get("ts"))
        if not message_id or referral_date is None:
            continue
        by_date.setdefault(referral_date, []).append(rec)

    out: dict[str, str] = {}
    for referral_date, day_records in by_date.items():
        day_records.sort(key=lambda r: (str(r.get("ts") or ""), str(r.get("message_id") or "")))
        for sequence, rec in enumerate(day_records, start=1):
            out[str(rec["message_id"])] = format_crn(referral_date, sequence)
    return out


def _looks_like_noa_or_fl401(name: str) -> bool:
    lower = str(name or "").lower()
    if not lower.endswith((".pdf", ".docx")):
        return False
    return any(kw in lower for kw in _NOA_FL401_KEYWORDS)


def _download_item_bytes(item: Mapping[str, Any], access_token: Optional[str]) -> bytes:
    import graph_files

    token = access_token or graph_files.token()
    drive_id = urllib.parse.quote(str(item.get("drive_id") or ""), safe="")
    item_id = urllib.parse.quote(str(item.get("item_id") or ""), safe="")
    url = f"{graph_files.GRAPH}/drives/{drive_id}/items/{item_id}/content"
    return graph_files.graph_bytes(url, token)


def _extract_document_text(item: Mapping[str, Any], access_token: Optional[str]) -> str:
    name = str(item.get("name") or "item")
    suffix = Path(name).suffix.lower()
    if suffix not in (".pdf", ".docx"):
        return ""
    data = _download_item_bytes(item, access_token)
    with tempfile.TemporaryDirectory(prefix="caseforge-crn-reconcile-") as tmp:
        local_path = Path(tmp) / f"doc{suffix}"
        local_path.write_bytes(data)
        if suffix == ".pdf":
            txt_path = local_path.with_suffix(".txt")
            try:
                subprocess.run(
                    ["pdftotext", str(local_path), str(txt_path)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60,
                )
            except subprocess.TimeoutExpired:
                return ""
            return txt_path.read_text(encoding="utf-8", errors="replace") if txt_path.exists() else ""

        from docx import Document

        doc = Document(local_path)
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    parts.extend(p.text for p in cell.paragraphs)
        return "\n".join(parts)


def reconcile_matter_crn(
    matter_id: str,
    client_name: str = "",
    *,
    access_token: Optional[str] = None,
    db_path: Any = None,
    edited_by: str = "system:crn-reconciliation",
    apply_correction: bool = False,
) -> dict[str, Any]:
    matter_id = str(matter_id or "").strip()
    if not matter_id:
        return {"matter_id": matter_id, "status": "no_matter_id", "checked": False}

    stored = company_references_by_matter_id([matter_id]).get(matter_id, "")

    from agents import onboarding_loa

    try:
        files = onboarding_loa.matter_files(matter_id, client_name, db_path=db_path)
    except Exception:
        return {"matter_id": matter_id, "status": "file_lookup_failed", "checked": False, "stored": stored}

    candidates = [f for f in files if _looks_like_noa_or_fl401(str(f.get("name") or ""))]
    if not candidates:
        return {"matter_id": matter_id, "status": "no_source_document", "checked": True, "stored": stored}

    found_refs: list[str] = []
    for item in candidates:
        try:
            text = _extract_document_text(item, access_token)
        except Exception:
            continue
        ref = normalise_company_reference(text)
        if ref:
            found_refs.append(ref)

    if not found_refs:
        return {
            "matter_id": matter_id,
            "status": "no_reference_found",
            "checked": True,
            "stored": stored,
            "documents_checked": len(candidates),
        }

    unique_refs = sorted(set(found_refs))
    if len(unique_refs) > 1:
        return {
            "matter_id": matter_id,
            "status": "ambiguous",
            "checked": True,
            "stored": stored,
            "found": unique_refs,
        }

    filed_ref = unique_refs[0]
    if filed_ref == stored:
        return {"matter_id": matter_id, "status": "matches", "checked": True, "stored": stored, "found": filed_ref}

    if not apply_correction:
        return {
            "matter_id": matter_id,
            "status": "mismatch_detected",
            "checked": True,
            "stored": stored,
            "found": filed_ref,
        }

    from vergil import client_edits

    client_edits.record_edit(
        matter_id=matter_id,
        field_name="company_reference",
        new_value=filed_ref,
        note=(
            f"NOA/FL401 filing carries {filed_ref}; correcting stored value "
            f"{stored or '(none)'} -- the filed document is canon over a predicted or stale value."
        ),
        edited_by=edited_by,
        db_path=db_path,
    )
    return {
        "matter_id": matter_id,
        "status": "corrected",
        "checked": True,
        "stored": stored,
        "found": filed_ref,
    }
