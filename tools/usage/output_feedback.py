#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

import sys

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    import ops_db
except ModuleNotFoundError:
    from tools import ops_db
try:
    from telemetry_sqlite import resolve_db_path
except ModuleNotFoundError:
    from tools.telemetry_sqlite import resolve_db_path
try:
    import firm_profile
except ModuleNotFoundError:
    from tools import firm_profile

FIRM_SHORT_NAME = firm_profile.load_profile().firm_short_name

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH: Optional[Path] = None


def current_db_path() -> Path:
    return DB_PATH if DB_PATH is not None else resolve_db_path()


LEGACY_DB_PATH = REPO_ROOT / "DATA" / "output-feedback.sqlite"
DEFAULT_PREFERENCES_PATH = REPO_ROOT / "runtime-data" / "output-preferences.md"
FILE_OUTPUT_ARTEFACT_TYPES = {"attendance_note", "brief_to_counsel", "bundle", "document", "statement_of_service"}
RULE_MARKDOWN_RE = re.compile(
    r"^- \[(?P<strength>[^\]]+)\] (?P<rule_text>.+?) "
    r"\(scope: (?P<scope>[^;]+); reason: (?P<reason_tag>[^;]+); feedback: (?P<feedback_count>\d+); "
    r"last\s+promoted: (?P<last_promoted_at>[^)]+)\)$"
)

DISPLAY_RULE_TEXT_BY_REASON = {
    "an_title_not_one_or_two_word_house_style": (
        "Attendance-note filenames and titles use 1-2 meaningful words; remove filler words instead of simply trimming."
    ),
    "filename_attendance_note_filename_house_style_is_1_2_meaningful_words": (
        "Attendance-note filenames and titles use 1-2 meaningful words; remove filler words instead of simply trimming."
    ),
    "an_title_not_three_word_house_style": (
        "Attendance-note filenames and titles use 1-2 meaningful words; remove filler words instead of simply trimming."
    ),
    "btc_heading_and_footer_house_style": (
        "Briefs to counsel use the approved heading and footer house style, with public funding shown as Legal Aid."
    ),
    "btc_heading_spacing_and_bullet_cleanup": (
        "Brief to Counsel headings are bold with extra space above, and closing sections use ordinary paragraph formatting."
    ),
    "btc_preserve_template_spacing_and_right_aligned_closing": (
        "Briefs to counsel keep the original template spacing and right-aligned closing block."
    ),
    "c100_section7_and_urgency_checkbox_rules": (
        "For C100 forms, select Family Law Act Part IV in Section 7 only when that proceeding is current; for urgent without-notice applications, Section 6.6 is No unless informal or abridged notice is impossible; Section 3c urgency is enough where urgency is the MIAM exemption ground."
    ),
    "c1a_applicant_voice_no_hedging_no_response_section": (
        "For applicant C1A forms, write harm details in the applicant's voice without source qualifiers, and leave the response-to-allegations section blank."
    ),
    "bundle_do_not_use_blank_court_copy_ws": (
        "For bundles, use the clean signed witness-statement source when the court-copy PDF renders blank or unusable."
    ),
    "bundle_never_use_draft_or_unsigned_without_warning": (
        "For bundles, use sealed or signed documents where available; warn before building if only draft or unsigned versions can be found."
    ),
    "bundle_source_priority_sealed_then_signed_never_draft": (
        "When selecting bundle documents, prefer sealed court-stamped copies first, then signed copies."
    ),
    "bundle_page_and_toc_link_geometry_house_style": (
        "Bundle page-number buttons stay within the grey box, keep transparency, sit low enough, and TOC page numbers align centrally on the row."
    ),
    "boosted_case_summaries_reference_old_material_only": (
        "Case summaries use shared fact extraction, then render a clean outward summary for the specific audience."
    ),
    "bundle_case_summary_chronology_are_outward_court_documents": (
        "Bundle case summaries and chronologies are court-facing documents; keep internal taxonomy, model attribution, source maps, and admin/live-status sections out of them."
    ),
    "fl401_use_empty_editable_base": (
        "For FL401 PDF filling, use the court's blank FL401 (templates/PDF Templates/FL401_0223 blank.pdf) and write the firm's solicitor and firm fields from the firm profile."
    ),
    "fl401_use_val_template_constants": (
        "For FL401 PDF filling, use the court's blank FL401 (templates/PDF Templates/FL401_0223 blank.pdf) and write the firm's solicitor and firm fields from the firm profile."
    ),
    "ccl_client_letter_contact_details_allowed_for_client": (
        "For opening client care letters sent to the applicant/client, use the client's verified contact details where the template requires them; C8-protected contact details stay out of respondent-facing material."
    ),
    "ccl_address_required_or_explicit_c8_withhold": (
        "For opening client care letters sent to the applicant/client, use the client's verified contact details where the template requires them."
    ),
    "ccl_client_letter_address_even_if_c8": (
        "For opening client care letters sent to the applicant/client, C8 is not a reason to omit that client's own verified address."
    ),
    "ccl_no_repetitive_statement_relief_paragraph": (
        "Opening client care letters keep Client Instructions concise and avoid repeating the order sought or without-notice basis."
    ),
    "ccl_police_refs_clean_client_wording": (
        "Opening client care letters write known police and crime references directly in client-facing wording."
    ),
    "ccl_template_geometry_reference_signature_enc": (
        f"Opening client care letter review checks template geometry, including Our Reference at 8pt, the {FIRM_SHORT_NAME} signature mark at 24pt, and proper ENC/enclosure spacing."
    ),
    "email_body_text_not_grey": "Counsel-request email body text uses black/default house style.",
    "ccl_email_subject_repeated_case_name": (
        "Client care letter email subjects use: Client Care Letter, Terms of Business and Privacy Notice || CASE_NAME, with CASE_NAME appearing once at the end."
    ),
    "ccl_email_subject_surname_only_case_name": (
        "Client care letter email subject case names after the separator use each party's first and last name, in First Last v First Last form."
    ),
    "ccl_ai_manual_review_backup_after_lint": (
        "Opening client care letter final review checks address presence, repetition, source-citation wording, and visual template formatting before the PDF/send pack."
    ),
    "counsel_request_no_order_papers_before_acceptance": (
        "Counsel request emails are availability requests; attach order papers only after counsel agrees to take the case."
    ),
    "email_edit_body_block_only_leave_subject": (
        "For counsel-request replacement hearing blocks, edit that body block only and leave the subject unchanged unless explicitly instructed."
    ),
    "process_server_never_zip_include_noa_respondent_info": (
        "Process-server service emails attach every served document separately and visibly, include Notice of Acting and respondent information, and end with Kind regards."
    ),
}

MARKDOWN_OMIT_REASON_TAGS = {
    "ccl_address_required_or_explicit_c8_withhold",
    "ccl_client_letter_address_even_if_c8",
    "ccl_client_letter_contact_details_allowed_for_client",
    "fl401_use_empty_editable_base",
    "fl401_use_val_template_constants",
}


def utc_now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()


def migrate_legacy_database() -> None:
    tables = ("outputs", "feedback", "derived_rules")
    ops_db.migrate_legacy_tables(
        tables,
        LEGACY_DB_PATH,
        db_path=current_db_path(),
        meta_key="legacy:output_feedback:data:v1",
    )
    ops_db.migrate_legacy_tables(
        tables,
        ops_db.LEGACY_TELEMETRY_DB,
        db_path=current_db_path(),
        meta_key="legacy:output_feedback:telemetry:v1",
    )


def ensure_database() -> Path:
    current_db_path().parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(current_db_path(), timeout=30) as conn:
        ops_db.apply_connection_pragmas(conn)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                artefact_type TEXT NOT NULL,
                client_name TEXT,
                matter_ref TEXT,
                path_or_message_id TEXT,
                template_used TEXT,
                title_or_subject TEXT,
                content_hash TEXT,
                prompt_summary TEXT,
                agent_version TEXT,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                output_id INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                verdict TEXT NOT NULL,
                scope TEXT NOT NULL,
                reason_tag TEXT NOT NULL,
                comment TEXT NOT NULL,
                severity TEXT NOT NULL,
                FOREIGN KEY(output_id) REFERENCES outputs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS derived_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artefact_type TEXT NOT NULL,
                scope TEXT NOT NULL,
                reason_tag TEXT NOT NULL,
                rule_text TEXT NOT NULL,
                applies_when TEXT NOT NULL,
                strength TEXT NOT NULL,
                source_feedback_count INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                last_promoted_at TEXT NOT NULL,
                UNIQUE(artefact_type, scope, reason_tag)
            );
            """
        )
    migrate_legacy_database()
    return current_db_path()


def record_output(metadata: Dict[str, Any]) -> int:
    ensure_database()
    created_at = str(metadata.get("created_at") or utc_now_z())
    artefact_type = str(metadata.get("artefact_type") or "").strip() or "document"
    client_name = str(metadata.get("client_name") or "").strip()
    matter_ref = str(metadata.get("matter_ref") or "").strip()
    path_or_message_id = str(metadata.get("path_or_message_id") or "").strip()
    template_used = str(metadata.get("template_used") or "").strip()
    title_or_subject = str(metadata.get("title_or_subject") or "").strip()
    prompt_summary = str(metadata.get("prompt_summary") or "").strip()
    agent_version = str(metadata.get("agent_version") or "").strip()
    payload_hash = str(metadata.get("content_hash") or "").strip() or content_hash(
        artefact_type,
        client_name,
        matter_ref,
        path_or_message_id,
        template_used,
        title_or_subject,
        prompt_summary,
        agent_version,
        json_text(metadata.get("metadata", {})),
    )
    metadata_json = json_text(metadata.get("metadata", {}))
    with sqlite3.connect(current_db_path()) as conn:
        cursor = conn.execute(
            """
            INSERT INTO outputs (
                created_at, artefact_type, client_name, matter_ref, path_or_message_id,
                template_used, title_or_subject, content_hash, prompt_summary, agent_version, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                artefact_type,
                client_name,
                matter_ref,
                path_or_message_id,
                template_used,
                title_or_subject,
                payload_hash,
                prompt_summary,
                agent_version,
                metadata_json,
            ),
        )
        return int(cursor.lastrowid)


def find_output_id(*, path_or_message_id: str = "", internet_message_id: str = "", artefact_type: str = "") -> Optional[int]:
    ensure_database()
    message_ref = str(path_or_message_id or "").strip()
    internet_ref = str(internet_message_id or "").strip()
    type_ref = str(artefact_type or "").strip()
    with sqlite3.connect(current_db_path()) as conn:
        if message_ref:
            if type_ref:
                row = conn.execute(
                    "SELECT id FROM outputs WHERE path_or_message_id = ? AND artefact_type = ? ORDER BY id DESC LIMIT 1",
                    (message_ref, type_ref),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM outputs WHERE path_or_message_id = ? ORDER BY id DESC LIMIT 1",
                    (message_ref,),
                ).fetchone()
            if row is not None:
                return int(row[0])
        if internet_ref:
            like_value = f'%"internet_message_id":"{internet_ref}"%'
            if type_ref:
                row = conn.execute(
                    "SELECT id FROM outputs WHERE metadata_json LIKE ? AND artefact_type = ? ORDER BY id DESC LIMIT 1",
                    (like_value, type_ref),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM outputs WHERE metadata_json LIKE ? ORDER BY id DESC LIMIT 1",
                    (like_value,),
                ).fetchone()
            if row is not None:
                return int(row[0])
    return None


def record_output_once(metadata: Dict[str, Any]) -> Dict[str, Any]:
    output_id = find_output_id(
        path_or_message_id=str(metadata.get("path_or_message_id") or "").strip(),
        internet_message_id=str((metadata.get("metadata") or {}).get("internet_message_id") or "").strip(),
        artefact_type=str(metadata.get("artefact_type") or "").strip(),
    )
    if output_id is not None:
        return {"output_id": int(output_id), "created": False}
    return {"output_id": int(record_output(metadata)), "created": True}


def _preferred_candidate_rank(candidate: Path) -> tuple[int, int, str]:
    text = str(candidate).lower().replace("/", "\\")
    if "\\artifacts\\" in text:
        bucket = 0
    elif "\\tmp\\" in text:
        bucket = 1
    else:
        bucket = 2
    return (bucket, len(candidate.parts), text)


def _update_output_path(output_id: int, new_path: Path) -> None:
    ensure_database()
    new_path_text = str(new_path)
    with sqlite3.connect(current_db_path()) as conn:
        row = conn.execute("SELECT metadata_json FROM outputs WHERE id = ?", (int(output_id),)).fetchone()
        if row is None:
            raise ValueError(f"Output id not found: {output_id}")
        metadata = {}
        try:
            metadata = json.loads(str(row[0] or "{}"))
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}
        previous = str(metadata.get("output_path") or "").strip()
        if previous and previous != new_path_text:
            metadata["previous_output_path"] = previous
        metadata["output_path"] = new_path_text
        conn.execute(
            "UPDATE outputs SET path_or_message_id = ?, metadata_json = ? WHERE id = ?",
            (new_path_text, json_text(metadata), int(output_id)),
        )


def sync_file_output_locations(
    *,
    scan_roots: list[Path] | None = None,
    promote_export_over_temp: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    ensure_database()
    roots = [item.resolve() for item in (scan_roots or [REPO_ROOT / "artifacts", REPO_ROOT / "tmp"]) if item.exists()]
    actions: list[Dict[str, Any]] = []
    with sqlite3.connect(current_db_path()) as conn:
        rows = conn.execute(
            "SELECT id, artefact_type, path_or_message_id, metadata_json FROM outputs ORDER BY id"
        ).fetchall()
    updated = 0
    for output_id, artefact_type, path_or_message_id, metadata_json in rows:
        artefact = str(artefact_type or "").strip()
        if artefact not in FILE_OUTPUT_ARTEFACT_TYPES:
            continue
        current_path_text = str(path_or_message_id or "").strip()
        if not current_path_text or (":\\" not in current_path_text and "/" not in current_path_text):
            continue
        current_path = Path(current_path_text)
        current_exists = current_path.exists()
        try:
            metadata = json.loads(str(metadata_json or "{}"))
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}
        candidate_name = current_path.name or Path(str(metadata.get("output_path") or "")).name
        if not candidate_name:
            continue
        candidates: list[Path] = []
        for root in roots:
            try:
                candidates.extend(item.resolve() for item in root.rglob(candidate_name) if item.is_file())
            except Exception:
                continue
        unique_candidates: list[Path] = []
        seen: set[str] = set()
        for item in candidates:
            key = str(item).lower()
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(item)
        unique_candidates.sort(key=_preferred_candidate_rank)
        replacement: Path | None = None
        current_text_lower = str(current_path).lower()
        if not current_exists:
            if unique_candidates:
                replacement = unique_candidates[0]
        elif promote_export_over_temp and "\\tmp\\" in current_text_lower.replace("/", "\\"):
            preferred = [item for item in unique_candidates if "\\artifacts\\" in str(item).lower().replace("/", "\\")]
            if preferred:
                replacement = preferred[0]
        if replacement is None:
            continue
        if str(replacement).lower() == current_text_lower:
            continue
        action = {
            "output_id": int(output_id),
            "artefact_type": artefact,
            "from_path": current_path_text,
            "to_path": str(replacement),
            "reason": "missing" if not current_exists else "prefer_export_over_temp",
        }
        actions.append(action)
        if not dry_run:
            _update_output_path(int(output_id), replacement)
            updated += 1
    if not dry_run:
        rebuild_preferences_markdown(DEFAULT_PREFERENCES_PATH, write=True)
    return {
        "updated": updated,
        "actions": actions,
        "scan_roots": [str(item) for item in roots],
        "dry_run": bool(dry_run),
    }


def _slugify(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return clean or "feedback"


TITLE_FILLER_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "about",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "onto",
    "re",
    "regarding",
    "the",
    "this",
    "that",
    "to",
    "with",
}

TITLE_LOW_PRIORITY_WORDS = {
    "attendance",
    "call",
    "called",
    "email",
    "emails",
    "issue",
    "issues",
    "matter",
    "note",
    "notes",
    "order",
    "orders",
    "query",
    "today",
    "today's",
    "tomorrow",
    "tomorrow's",
    "update",
    "yesterday",
    "yesterday's",
}


def _title_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", str(text or ""))


def _meaningful_title_words(text: str) -> list[str]:
    words = _title_words(text)
    filtered = [word for word in words if word.lower() not in TITLE_FILLER_WORDS]
    return filtered or words


def _format_title_word(word: str) -> str:
    if re.fullmatch(r"[A-Z0-9/-]{2,}", word or ""):
        return word
    if re.search(r"\d", word or ""):
        return word
    return str(word or "").lower().capitalize()


def suggest_attendance_note_title(title: str, *, max_words: int = 2) -> Dict[str, Any]:
    meaningful = _meaningful_title_words(title)
    preferred = [word for word in meaningful if word.lower() not in TITLE_LOW_PRIORITY_WORDS]
    source = preferred if preferred else meaningful
    shortened = source[: max(1, int(max_words))]
    suggestion = " ".join(_format_title_word(word) for word in shortened).strip()
    return {
        "original_title": str(title or "").strip(),
        "meaningful_word_count": len(meaningful),
        "suggested_title": suggestion,
        "was_shortened": suggestion.lower() != str(title or "").strip().lower(),
        "max_words": int(max_words),
    }


def parse_feedback(comment: str, artefact_type: str = "") -> Dict[str, str]:
    text = str(comment or "").strip()
    lower = text.lower()
    scope = "overall"
    if "filename" in lower:
        scope = "filename"
    elif "calendar" in lower and ("title" in lower or "subject" in lower):
        scope = "calendar_title"
    elif "title" in lower or "subject" in lower:
        scope = "title"
    elif any(marker in lower for marker in ("folder", "saved in", "wrong place", "save location", "wrong location")):
        scope = "placement"
    elif any(marker in lower for marker in ("workflow", "behaviour", "behavior", "surface")):
        scope = "workflow"
    elif "tone" in lower:
        scope = "tone"
    elif "template" in lower:
        scope = "template"
    elif "content" in lower or "wording" in lower:
        scope = "content"

    negative_markers = ("wrong", "bad", "don't", "do not", "never", "missing", "incorrect", "failed", "issue")
    positive_markers = ("good", "correct", "fine", "keep", "use this", "prefer this")
    verdict = "do_not_prefer" if any(marker in lower for marker in negative_markers) else "prefer"
    if verdict == "prefer" and any(marker in lower for marker in positive_markers):
        verdict = "prefer"

    severity = "minor"
    if any(marker in lower for marker in ("must", "always", "never", "house style", "required", "hard rule", "exact")):
        severity = "hard_rule"
    elif any(marker in lower for marker in ("wrong", "incorrect", "missing", "important")):
        severity = "important"

    reason_tag = ""
    artefact_lower = artefact_type.lower().strip()
    title_length_markers = ("too long", "little long", "a bit long", "wordy", "shorter", "shorten", "keep it short")
    if scope in {"title", "filename", "calendar_title"} and any(marker in lower for marker in title_length_markers):
        verdict = "do_not_prefer"
        severity = "important" if severity == "minor" else severity
    if artefact_lower == "attendance_note" and any(marker in lower for marker in ("three-word", "3-word", "three word", "3 word", "two-word", "2-word", "two word", "2 word", "1-2 word", "one-two word", "one or two word")):
        reason_tag = "an_title_not_one_or_two_word_house_style"
        scope = "filename" if scope == "overall" else scope
        verdict = "do_not_prefer"
        if severity == "minor":
            severity = "hard_rule"
    elif artefact_lower == "attendance_note" and scope in {"title", "filename"} and any(marker in lower for marker in title_length_markers):
        reason_tag = "an_title_too_long"
    elif scope == "calendar_title" and "hearing type" in lower:
        reason_tag = "calendar_title_missing_hearing_type"
    elif scope == "calendar_title" and "date" in lower:
        reason_tag = "calendar_title_missing_date"
    elif scope == "calendar_title" and "time" in lower:
        reason_tag = "calendar_title_missing_time"
    elif scope == "filename":
        reason_tag = _slugify(f"filename_{lower[:60]}")
    else:
        reason_tag = _slugify(f"{scope}_{lower[:60]}")

    return {
        "verdict": verdict,
        "scope": scope,
        "reason_tag": reason_tag,
        "severity": severity,
        "comment": text,
    }


def _rule_text_for(reason_tag: str, artefact_type: str, scope: str, comment: str) -> str:
    mapped = display_rule_text(reason_tag, "")
    if mapped:
        return mapped
    if reason_tag == "an_title_not_three_word_house_style":
        return "Attendance-note filenames and titles use 1-2 meaningful words; remove filler words instead of simply trimming."
    if reason_tag == "an_title_too_long":
        return "Attendance-note filenames and titles use 1-2 meaningful words; remove filler words instead of simply trimming."
    if reason_tag == "btc_heading_and_footer_house_style":
        return "Briefs to counsel use the approved heading and footer house style, with public funding shown as Legal Aid."
    if reason_tag == "btc_heading_spacing_and_bullet_cleanup":
        return "Brief to Counsel headings are bold with extra space above, and closing sections use ordinary paragraph formatting."
    if reason_tag == "btc_preserve_template_spacing_and_right_aligned_closing":
        return "Brief to counsel should keep the original template spacing and must not be squashed together at the top. The closing block should stay right-aligned in house style. If a full rebuild breaks spacing, revert to the template-spaced version and apply only targeted corrections."
    if reason_tag == "calendar_title_missing_hearing_type":
        return "Calendar titles must include the hearing type label."
    if reason_tag == "calendar_title_missing_date":
        return "Calendar titles must include the hearing date."
    if reason_tag == "calendar_title_missing_time":
        return "Calendar titles must include the hearing time."
    if reason_tag == "bundle_do_not_use_blank_court_copy_ws":
        return "For bundles, use the clean signed witness-statement source when the court-copy PDF renders blank or unusable."
    if reason_tag == "bundle_never_use_draft_or_unsigned_without_warning":
        return "For bundles, use sealed or signed documents where available; warn before building if only draft or unsigned versions can be found."
    if reason_tag == "bundle_source_priority_sealed_then_signed_never_draft":
        return "When selecting bundle documents, prefer sealed court-stamped copies first, then signed copies."
    if reason_tag == "bundle_page_and_toc_link_geometry_house_style":
        return "Bundle page-number buttons must stay within the grey box, keep transparency, sit lower than the over-raised version, and the TOC page numbers should align centrally on the row with the surrounding text."
    if scope == "calendar_title":
        return "Calendar titles should follow the latest operator-approved house style."
    if scope == "placement":
        return comment or f"{artefact_type} outputs should be saved to the operator-approved folder and surface."
    if scope == "workflow":
        return comment or f"{artefact_type} should follow the operator-approved workflow steps and destination surface."
    return comment or f"{artefact_type} {scope} should follow operator-approved preferences."


def upsert_derived_rule(
    artefact_type: str,
    scope: str,
    reason_tag: str,
    rule_text: str,
    *,
    strength: str = "hard_rule",
    source_feedback_count: int = 1,
    applies_when: str = "",
    last_promoted_at: str = "",
) -> None:
    ensure_database()
    now = utc_now_z()
    clean_rule_text = display_rule_text(reason_tag, rule_text)
    with sqlite3.connect(current_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO derived_rules (
                artefact_type, scope, reason_tag, rule_text, applies_when,
                strength, source_feedback_count, active, last_promoted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(artefact_type, scope, reason_tag) DO UPDATE SET
                rule_text = excluded.rule_text,
                applies_when = excluded.applies_when,
                strength = excluded.strength,
                source_feedback_count = excluded.source_feedback_count,
                active = 1,
                last_promoted_at = excluded.last_promoted_at
            """,
            (
                str(artefact_type).strip(),
                str(scope).strip() or "overall",
                str(reason_tag).strip(),
                clean_rule_text,
                str(applies_when).strip() or f"scope={str(scope).strip() or 'overall'}",
                str(strength).strip() or "hard_rule",
                max(1, int(source_feedback_count or 1)),
                str(last_promoted_at).strip() or now,
            ),
        )


def seed_derived_rules_from_markdown(
    markdown_path: Path = DEFAULT_PREFERENCES_PATH,
    *,
    only_if_empty: bool = False,
) -> Dict[str, Any]:
    ensure_database()
    if only_if_empty:
        with sqlite3.connect(current_db_path()) as conn:
            row = conn.execute("SELECT COUNT(*) FROM derived_rules").fetchone()
            if int((row or [0])[0] or 0) > 0:
                return {
                    "seeded": 0,
                    "skipped": True,
                    "reason": "derived_rules already populated",
                    "markdown_path": str(markdown_path),
                }

    if not markdown_path.exists():
        return {
            "seeded": 0,
            "skipped": True,
            "reason": "markdown not found",
            "markdown_path": str(markdown_path),
        }

    current_type = ""
    seeded = 0
    for raw_line in markdown_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            current_type = line[3:].strip()
            continue
        if not line.startswith("- [") or not current_type:
            continue
        match = RULE_MARKDOWN_RE.match(line)
        if not match:
            continue
        payload = match.groupdict()
        upsert_derived_rule(
            current_type,
            payload["scope"],
            payload["reason_tag"],
            payload["rule_text"],
            strength=payload["strength"],
            source_feedback_count=int(payload["feedback_count"]),
            applies_when=f"scope={payload['scope']}",
            last_promoted_at=payload["last_promoted_at"],
        )
        seeded += 1

    rebuild_preferences_markdown(DEFAULT_PREFERENCES_PATH, write=True)
    return {
        "seeded": seeded,
        "skipped": False,
        "markdown_path": str(markdown_path),
    }


def promote_rules(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT o.artefact_type, f.scope, f.reason_tag, f.comment,
               SUM(CASE WHEN f.severity = 'hard_rule' THEN 1 ELSE 0 END) AS hard_rule_count,
               COUNT(*) AS feedback_count
        FROM feedback f
        JOIN outputs o ON o.id = f.output_id
        GROUP BY o.artefact_type, f.scope, f.reason_tag, f.comment
        """
    ).fetchall()
    now = utc_now_z()
    for artefact_type, scope, reason_tag, comment, hard_rule_count, feedback_count in rows:
        if int(hard_rule_count or 0) == 0 and int(feedback_count or 0) < 2:
            continue
        strength = "hard_rule" if int(hard_rule_count or 0) > 0 else "strong_preference"
        conn.execute(
            """
            INSERT INTO derived_rules (
                artefact_type, scope, reason_tag, rule_text, applies_when,
                strength, source_feedback_count, active, last_promoted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(artefact_type, scope, reason_tag) DO UPDATE SET
                rule_text = excluded.rule_text,
                applies_when = excluded.applies_when,
                strength = excluded.strength,
                source_feedback_count = excluded.source_feedback_count,
                active = 1,
                last_promoted_at = excluded.last_promoted_at
            """,
            (
                str(artefact_type),
                str(scope),
                str(reason_tag),
                display_rule_text(
                    str(reason_tag),
                    _rule_text_for(str(reason_tag), str(artefact_type), str(scope), str(comment)),
                ),
                f"scope={scope}",
                strength,
                int(feedback_count or 0),
                now,
            ),
        )


def record_feedback(output_id: int, comment: str, *, verdict: str = "", scope: str = "", reason_tag: str = "", severity: str = "") -> Dict[str, Any]:
    ensure_database()
    with sqlite3.connect(current_db_path()) as conn:
        row = conn.execute("SELECT artefact_type FROM outputs WHERE id = ?", (int(output_id),)).fetchone()
        if row is None:
            raise ValueError(f"Output id not found: {output_id}")
        artefact_type = str(row[0] or "")
        parsed = parse_feedback(comment, artefact_type=artefact_type)
        payload = {
            "verdict": verdict or parsed["verdict"],
            "scope": scope or parsed["scope"],
            "reason_tag": reason_tag or parsed["reason_tag"],
            "severity": severity or parsed["severity"],
            "comment": parsed["comment"],
        }
        cursor = conn.execute(
            """
            INSERT INTO feedback (output_id, recorded_at, verdict, scope, reason_tag, comment, severity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(output_id),
                utc_now_z(),
                payload["verdict"],
                payload["scope"],
                payload["reason_tag"],
                payload["comment"],
                payload["severity"],
            ),
        )
        promote_rules(conn)
        feedback_id = int(cursor.lastrowid)
    rebuild_preferences_markdown(DEFAULT_PREFERENCES_PATH, write=True)
    return {"feedback_id": feedback_id, **payload}


def rebuild_preferences_markdown(output_path: Path = DEFAULT_PREFERENCES_PATH, *, write: bool = False) -> str:
    ensure_database()
    with sqlite3.connect(current_db_path()) as conn:
        rows = conn.execute(
            """
            SELECT artefact_type, scope, reason_tag, rule_text, strength, source_feedback_count, last_promoted_at
            FROM derived_rules
            WHERE active = 1
            ORDER BY artefact_type, strength DESC, scope, reason_tag
            """
        ).fetchall()

    lines = [
        "# Output Preferences",
        "",
        "> Derived quick-read from structured operator feedback. `AGENTS.md`, `tasks/`, and `context/` remain authoritative. Promotion dates, severity, reason tags, and feedback counts stay in the output-feedback database.",
        "",
    ]
    if not rows:
        lines.append("- No derived output-preference rules have been promoted yet.")
    else:
        current_type = None
        seen_by_type: dict[str, set[str]] = {}
        for artefact_type, scope, reason_tag, rule_text, strength, feedback_count, last_promoted_at in rows:
            if str(reason_tag) in MARKDOWN_OMIT_REASON_TAGS:
                continue
            display_text = display_rule_text(str(reason_tag), str(rule_text))
            if not display_text:
                continue
            if artefact_type != current_type:
                if current_type is not None:
                    lines.append("")
                lines.append(f"## {artefact_type}")
                lines.append("")
                current_type = artefact_type
            seen = seen_by_type.setdefault(str(artefact_type), set())
            if display_text in seen:
                continue
            seen.add(display_text)
            lines.append(f"- {display_text}")
    markdown = "\n".join(lines) + "\n"
    if write:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    return markdown


def check_preflight(artefact_type: str, *, title_or_subject: str = "") -> Dict[str, Any]:
    ensure_database()
    with sqlite3.connect(current_db_path()) as conn:
        rows = conn.execute(
            """
            SELECT scope, reason_tag, rule_text, strength
            FROM derived_rules
            WHERE active = 1 AND artefact_type = ?
            ORDER BY strength DESC, scope, reason_tag
            """,
            (str(artefact_type),),
        ).fetchall()

    violations = []
    title = str(title_or_subject or "")
    lower = title.lower()
    suggestion: Optional[Dict[str, Any]] = None
    for scope, reason_tag, rule_text, strength in rows:
        reason = str(reason_tag)
        hit = False
        if reason in {"an_title_not_three_word_house_style", "an_title_not_one_or_two_word_house_style", "an_title_too_long"} and str(artefact_type) == "attendance_note":
            suggestion = suggest_attendance_note_title(title, max_words=2)
            hit = int(suggestion.get("meaningful_word_count", 0)) > 2
        elif reason == "calendar_title_missing_hearing_type":
            hit = not any(token in lower for token in ("fhdra", "fdra", "dra", "directions", "final hearing", "return hearing", "fact-finding"))
        elif reason == "calendar_title_missing_date":
            hit = re.search(r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", title) is None
        elif reason == "calendar_title_missing_time":
            hit = re.search(r"\b\d{1,2}(?::\d{2})?\s*(am|pm)\b", lower) is None
        if hit:
            violations.append(
                {
                    "scope": str(scope),
                    "reason_tag": reason,
                    "rule_text": display_rule_text(reason, str(rule_text)),
                    "strength": str(strength),
                }
            )
    return {
        "artefact_type": str(artefact_type),
        "title_or_subject": title,
        "suggestion": suggestion,
        "violations": violations,
    }


def display_rule_text(reason_tag: str, rule_text: str) -> str:

    mapped = DISPLAY_RULE_TEXT_BY_REASON.get(str(reason_tag or "").strip())
    return mapped or str(rule_text or "").strip()


def normalise_derived_rule_texts(*, write: bool = False) -> Dict[str, Any]:

    ensure_database()
    with sqlite3.connect(current_db_path()) as conn:
        rows = conn.execute(
            """
            SELECT id, reason_tag, rule_text
            FROM derived_rules
            ORDER BY id
            """
        ).fetchall()
        updates = []
        for row_id, reason_tag, rule_text in rows:
            clean = display_rule_text(str(reason_tag), str(rule_text))
            if clean and clean != str(rule_text or ""):
                updates.append(
                    {
                        "id": int(row_id),
                        "reason_tag": str(reason_tag),
                        "before": str(rule_text or ""),
                        "after": clean,
                    }
                )
        if write and updates:
            conn.executemany(
                "UPDATE derived_rules SET rule_text = ? WHERE id = ?",
                [(item["after"], item["id"]) for item in updates],
            )
    if write and updates:
        rebuild_preferences_markdown(DEFAULT_PREFERENCES_PATH, write=True)
    return {
        "checked": len(rows),
        "updated": len(updates) if write else 0,
        "candidate_count": len(updates),
        "updates": updates,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Store operator feedback for generated outputs.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ensure-db")
    sub.add_parser("print-db-path")

    p_output = sub.add_parser("record-output")
    p_output.add_argument("--payload-file", default="")
    p_output.add_argument("--payload-json", default="")

    p_output_once = sub.add_parser("record-output-once")
    p_output_once.add_argument("--payload-file", default="")
    p_output_once.add_argument("--payload-json", default="")

    p_feedback = sub.add_parser("record-feedback")
    p_feedback.add_argument("--output-id", type=int, required=True)
    p_feedback.add_argument("--comment", required=True)
    p_feedback.add_argument("--verdict", default="")
    p_feedback.add_argument("--scope", default="")
    p_feedback.add_argument("--reason-tag", default="")
    p_feedback.add_argument("--severity", default="")

    p_prefs = sub.add_parser("rebuild-preferences")
    p_prefs.add_argument("--output", default=str(DEFAULT_PREFERENCES_PATH))
    p_prefs.add_argument("--write", action="store_true")

    p_normalise = sub.add_parser("normalise-derived-rules")
    p_normalise.add_argument("--write", action="store_true")

    p_seed = sub.add_parser("seed-derived-rules-from-markdown")
    p_seed.add_argument("--markdown", default=str(DEFAULT_PREFERENCES_PATH))
    p_seed.add_argument("--only-if-empty", action="store_true")

    p_sync_files = sub.add_parser("sync-file-output-locations")
    p_sync_files.add_argument("--scan-root", action="append", default=[])
    p_sync_files.add_argument("--dry-run", action="store_true")
    p_sync_files.add_argument("--no-promote-export-over-temp", action="store_true")

    p_preflight = sub.add_parser("preflight")
    p_preflight.add_argument("--artefact-type", required=True)
    p_preflight.add_argument("--title-or-subject", default="")
    return parser.parse_args()


def load_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if getattr(args, "payload_file", ""):
        return json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    if getattr(args, "payload_json", ""):
        return json.loads(args.payload_json)
    raise SystemExit("Payload required.")


def main() -> int:
    args = parse_args()
    if args.cmd == "ensure-db":
        print(str(ensure_database()))
        return 0
    if args.cmd == "print-db-path":
        print(str(current_db_path()))
        return 0
    if args.cmd == "record-output":
        payload = load_payload(args)
        print(json.dumps({"output_id": record_output(payload)}, ensure_ascii=False))
        return 0
    if args.cmd == "record-output-once":
        payload = load_payload(args)
        print(json.dumps(record_output_once(payload), ensure_ascii=False))
        return 0
    if args.cmd == "record-feedback":
        print(
            json.dumps(
                record_feedback(
                    args.output_id,
                    args.comment,
                    verdict=args.verdict,
                    scope=args.scope,
                    reason_tag=args.reason_tag,
                    severity=args.severity,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.cmd == "rebuild-preferences":
        output_path = Path(args.output)
        print(rebuild_preferences_markdown(output_path, write=args.write))
        return 0
    if args.cmd == "normalise-derived-rules":
        print(json.dumps(normalise_derived_rule_texts(write=args.write), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.cmd == "seed-derived-rules-from-markdown":
        print(
            json.dumps(
                seed_derived_rules_from_markdown(
                    Path(args.markdown),
                    only_if_empty=bool(args.only_if_empty),
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.cmd == "sync-file-output-locations":
        scan_roots = [Path(value) for value in list(args.scan_root or []) if str(value).strip()]
        print(
            json.dumps(
                sync_file_output_locations(
                    scan_roots=scan_roots or None,
                    promote_export_over_temp=not bool(args.no_promote_export_over_temp),
                    dry_run=bool(args.dry_run),
                ),
                ensure_ascii=False,
            )
        )
        return 0
    if args.cmd == "preflight":
        print(json.dumps(check_preflight(args.artefact_type, title_or_subject=args.title_or_subject), ensure_ascii=False))
        return 0
    raise SystemExit(f"Unsupported command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
