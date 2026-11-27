#!/usr/bin/env python3
"Extracts bundle-chronology facts into SQL: dated events into"

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import model_backend
import clientdb_sql
from agents.ccl_pipeline import (
    GatherError,
    gather_client_facts,
    graph_files_token,
    list_ai_exp_clients,
)
from matter_fact_extraction import resolve_matter_id
from vergil.client_edits import utc_now


_VALID_CONFIDENCE = {"high", "medium", "low"}
_VALID_EVENT_TYPE = {"hearing", "application_sent", "order_granted", "order_sealed", "order_served", "unclear"}
_VALID_SOURCE_LABEL = {
    "witness_statement", "fl401", "referral_email", "notice_of_hearing", "order", "court_email", "unclear",
}


class ChronologyExtractionError(RuntimeError):
    "Raised only when the model call itself fails -- never for \"nothing"


_PROMPT_TEMPLATE = """You are extracting bundle-chronology facts from family law source documents, for a \
solicitor's own case record -- not for a court filing and not to judge the case.

Extract ONLY facts genuinely stated in the text below. Never invent, guess, or infer a name, date, or fact \
that isn't actually there. Missing fields are correct and expected -- leave them blank/empty, do not guess.

WITNESS STATEMENT:
{ws_text}

FL401 APPLICATION:
{fl401_text}

REFERRER REFERRAL EMAIL:
{referral_text}

Reply with strict JSON only, no markdown fences, no other text, in exactly this shape:
{{
  "client_dob": "YYYY-MM-DD or empty string",
  "respondent_dob": "YYYY-MM-DD or empty string",
  "relationship_start": "as stated (may be a vague date/month/year) or empty string",
  "relationship_end": "as stated (may be a vague date/month/year) or empty string",
  "events": [
    {{
      "event_date": "YYYY-MM-DD, or empty string if no date/only a vague date is given",
      "event_type": "one of: hearing, application_sent, order_granted, order_sealed, order_served, unclear",
      "hearing_type": "e.g. FHDRA, DRA, final hearing, return hearing -- empty string if not a hearing or not stated",
      "on_notice": true, false, or null if not stated (only meaningful for a hearing event),
      "event_text": "one short sentence, in the source's own terms",
      "source_label": "one of: witness_statement, fl401, referral_email, notice_of_hearing, order, court_email, unclear",
      "confidence": "high, medium, or low -- how explicitly the source states this"
    }}
  ]
}}"""


MAX_OUTPUT_TOKENS = 8000


def extract_chronology(*, fl401_text: str, ws_text: str, referral_text: str) -> dict[str, Any]:
    prompt = _PROMPT_TEMPLATE.format(
        fl401_text=fl401_text[:8000], ws_text=ws_text[:8000], referral_text=referral_text[:4000]
    )
    result = model_backend.run_model(
        model_backend.ROLE_MATTER_TIMELINE, prompt, model=model_backend.model_for_role(model_backend.ROLE_MATTER_TIMELINE, backend="openrouter"),
        backend="openrouter", timeout=90, max_tokens=MAX_OUTPUT_TOKENS,
    )
    if not result.ok:
        raise ChronologyExtractionError(
            f"chronology extraction call failed: {result.attempts[-1].error if result.attempts else 'unknown'}"
        )
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", result.text.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ChronologyExtractionError(f"chronology extraction did not return valid JSON: {exc}. Raw: {raw[:300]!r}") from exc
    if not isinstance(parsed, dict):
        raise ChronologyExtractionError(f"chronology extraction returned a non-object JSON value: {raw[:300]!r}")
    return _clean_result(parsed)


def _clean_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _clean_event(item: dict[str, Any]) -> dict[str, Any]:
    event_type = str(item.get("event_type") or "").strip().lower()
    source_label = str(item.get("source_label") or "").strip().lower()
    confidence = str(item.get("confidence") or "").strip().lower()
    return {
        "event_date": str(item.get("event_date") or "").strip(),
        "event_type": event_type if event_type in _VALID_EVENT_TYPE else "unclear",
        "hearing_type": str(item.get("hearing_type") or "").strip(),
        "on_notice": _clean_bool(item.get("on_notice")),
        "event_text": str(item.get("event_text") or "").strip(),
        "source_label": source_label if source_label in _VALID_SOURCE_LABEL else "unclear",
        "confidence": confidence if confidence in _VALID_CONFIDENCE else "low",
    }


def _clean_result(parsed: dict[str, Any]) -> dict[str, Any]:
    events = [_clean_event(e) for e in parsed.get("events") or [] if isinstance(e, dict)]
    return {
        "client_dob": str(parsed.get("client_dob") or "").strip(),
        "respondent_dob": str(parsed.get("respondent_dob") or "").strip(),
        "relationship_start": str(parsed.get("relationship_start") or "").strip(),
        "relationship_end": str(parsed.get("relationship_end") or "").strip(),
        "events": [e for e in events if e["event_date"] or e["event_text"]],
    }


def _column_is_empty(table: str, column: str, matter_or_person_id_col: str, id_value: str) -> bool:
    sql = f"SELECT {column} FROM {table} WHERE {matter_or_person_id_col} = ?"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, (id_value,))
        row = cursor.fetchone()
    return row is not None and not str(row[0] or "").strip()


def _existing_event_keys(matter_id: str) -> set[tuple[str, str]]:
    sql = "SELECT event_date, event_type, event_text FROM matter_chronology_events WHERE matter_id = ?"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, (matter_id,))
        rows = cursor.fetchall()
    keys = set()
    for event_date, event_type, event_text in rows:
        date, etype, text = str(event_date or ""), str(event_type or ""), str(event_text or "")
        keys.add((date, etype) if date else ("", text[:80]))
    return keys


def _apply_extracted_chronology(
    matter_id: str, primary_person_id: str, client_name: str, parsed: dict[str, Any], *, dry_run: bool = False
) -> dict[str, Any]:
    "Never overwrites a non-empty column -- only fills a currently-empty"
    report: dict[str, Any] = {
        "matter_id": matter_id,
        "client_name": client_name,
        "extracted": parsed,
        "scalar_fields_filled": {},
        "events_added": [],
    }

    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()

        if parsed["client_dob"] and primary_person_id and _column_is_empty("people", "dob_iso", "person_id", primary_person_id):
            report["scalar_fields_filled"]["client_dob"] = parsed["client_dob"]
            if not dry_run:
                cursor.execute("UPDATE people SET dob_iso = ?, updated_utc = ? WHERE person_id = ? AND COALESCE(dob_iso, '') = ''", (parsed["client_dob"], utc_now(), primary_person_id))

        cursor.execute("SELECT matter_party_id, dob_iso FROM matter_parties WHERE matter_id = ? AND role LIKE 'respondent'", (matter_id,))
        respondents = cursor.fetchall()
        if parsed["respondent_dob"] and len(respondents) == 1 and not str(respondents[0][1] or "").strip():
            report["scalar_fields_filled"]["respondent_dob"] = parsed["respondent_dob"]
            if not dry_run:
                cursor.execute(
                    "UPDATE matter_parties SET dob_iso = ?, updated_utc = ? WHERE matter_party_id = ? AND COALESCE(dob_iso, '') = ''",
                    (parsed["respondent_dob"], utc_now(), respondents[0][0]),
                )

        for column, label in (("relationship_start", "relationship_start"), ("relationship_end", "relationship_end")):
            new_value = parsed[label]
            if new_value and _column_is_empty("matters", column, "matter_id", matter_id):
                report["scalar_fields_filled"][label] = new_value
                if not dry_run:
                    cursor.execute(f"UPDATE matters SET {column} = ?, updated_utc = ? WHERE matter_id = ? AND COALESCE({column}, '') = ''", (new_value, utc_now(), matter_id))

        existing_events = _existing_event_keys(matter_id)
        for event in parsed["events"]:
            key = (event["event_date"], event["event_type"]) if event["event_date"] else ("", event["event_text"][:80])
            if key in existing_events:
                continue
            existing_events.add(key)
            report["events_added"].append(event)
            if dry_run:
                continue
            cursor.execute(
                "INSERT INTO matter_chronology_events "
                "(matter_id, event_date, event_type, hearing_type, on_notice, event_text, source_label, confidence, "
                "court_facing, include_in_bundle, created_utc, updated_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (matter_id, event["event_date"] or None, event["event_type"], event["hearing_type"] or None,
                 event["on_notice"], event["event_text"] or None, event["source_label"], event["confidence"],
                 True, True, utc_now(), utc_now()),
            )

    return report


def backfill_matter(client_name: str, matter_id: str, primary_person_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    facts = gather_client_facts(client_name)
    parsed = extract_chronology(
        fl401_text=facts["fl401_text"], ws_text=facts["ws_text"], referral_text=facts["referral_body_text"]
    )
    return _apply_extracted_chronology(matter_id, primary_person_id, client_name, parsed, dry_run=dry_run)


def scan(*, dry_run: bool = True, limit: int | None = None) -> dict[str, Any]:
    "Backfill every AI-EXP client that resolves to a real matter_id."
    access_token = graph_files_token()
    clients = list_ai_exp_clients(access_token=access_token)
    if limit:
        clients = clients[:limit]
    summary: dict[str, Any] = {"scanned": len(clients), "applied": [], "skipped_no_matter": [], "errored": []}
    for client_name in clients:
        matter_id = resolve_matter_id(client_name)
        if not matter_id:
            summary["skipped_no_matter"].append(client_name)
            continue
        primary_person_id = _primary_person_id(matter_id)
        try:
            result = backfill_matter(client_name, matter_id, primary_person_id, dry_run=dry_run)
        except (GatherError, ChronologyExtractionError) as exc:
            summary["errored"].append({"client_name": client_name, "matter_id": matter_id, "reason": str(exc)})
            continue
        summary["applied"].append(result)
    return summary


def _primary_person_id(matter_id: str) -> str:
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT primary_person_id FROM matters WHERE matter_id = ?", (matter_id,))
        row = cursor.fetchone()
    return str(row[0]) if row and row[0] is not None else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-name", help="AI-EXP client folder name, exactly as it appears on OneDrive")
    parser.add_argument("--matter-id", help="caseforge-clientdb matter_id to write onto")
    parser.add_argument("--scan", action="store_true", help="Backfill every AI-EXP client that resolves to a real matter_id")
    parser.add_argument("--limit", type=int, default=None, help="With --scan, cap how many clients are processed")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=None, help="Extract and report but do not write (default for --scan)")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="Actually write -- required to make --scan live")
    args = parser.parse_args(argv)

    if args.scan:
        dry_run = True if args.dry_run is None else args.dry_run
        summary = scan(dry_run=dry_run, limit=args.limit)
        print(json.dumps(summary, indent=2, default=str))
        return 1 if summary["errored"] else 0

    if not args.client_name or not args.matter_id:
        parser.error("--client-name and --matter-id (or --scan) are required")

    primary_person_id = _primary_person_id(args.matter_id)
    dry_run = bool(args.dry_run)
    try:
        result = backfill_matter(args.client_name, args.matter_id, primary_person_id, dry_run=dry_run)
    except (GatherError, ChronologyExtractionError) as exc:
        print(json.dumps({"client_name": args.client_name, "matter_id": args.matter_id, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
