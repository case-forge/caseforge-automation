#!/usr/bin/env python3
"Extracts dated, factual incidents into ``matter_incidents``"

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
    AI_EXP_ROOT,
    GatherError,
    _extract_crime_references,
    gather_client_facts,
    graph_files_token,
    list_ai_exp_clients,
)
from folder_surname import surname_of
from matter_fact_extraction import resolve_matter_id
from vergil.client_edits import utc_now

BACKFILL_EDITOR = "system:matter-incidents-extraction"


_VALID_CONFIDENCE = {"high", "medium", "low"}
_VALID_SOURCE_LABEL = {"witness_statement", "fl401", "referral_email", "unclear"}


class IncidentExtractionError(RuntimeError):
    "Raised when the model call itself fails -- never for \"no incidents"


_PROMPT_TEMPLATE = """You are extracting a list of dated, factual incidents from family law source documents, \
for a solicitor's own case record -- not for a court filing and not to judge the case.

Extract ONLY incidents genuinely described in the text below, one entry per distinct incident. Never invent, \
guess, or infer an incident, date, or reference that isn't actually stated. An empty list is correct and \
expected for a matter with no dated incidents in this text.

"incident_type" must be a plain description in the source's own terms (e.g. "pushed her against the wall", \
"sent threatening text messages", "breached the non-molestation order by attending the property") -- NEVER a \
coded category like "physical abuse" or "coercive control". State what happened, in a few words, not a \
classification of it.

WITNESS STATEMENT:
{ws_text}

FL401 APPLICATION:
{fl401_text}

REFERRER REFERRAL EMAIL:
{referral_text}

Reply with strict JSON only, no markdown fences, no other text -- a list of objects:
[
  {{
    "incident_date": "YYYY-MM-DD, or empty string if no date/only a vague date is given",
    "incident_type": "plain description as stated, never a coded category",
    "summary": "one or two sentences, in the source's own terms, no judgement or embellishment",
    "police_called": true, false, or null if not stated,
    "crime_reference": "the exact reference as stated, or empty string if none given",
    "arrest_status": "as stated (e.g. 'arrested and released on bail', 'no arrest made'), or empty string",
    "bail_status": "as stated, or empty string",
    "source_label": "one of: witness_statement, fl401, referral_email, unclear",
    "confidence": "high, medium, or low -- how explicitly the source states this incident"
  }}
]"""


MAX_OUTPUT_TOKENS = 8000


def extract_incidents(*, fl401_text: str, ws_text: str, referral_text: str) -> list[dict[str, Any]]:
    prompt = _PROMPT_TEMPLATE.format(
        fl401_text=fl401_text[:8000], ws_text=ws_text[:8000], referral_text=referral_text[:4000]
    )
    result = model_backend.run_model(
        model_backend.ROLE_MATTER_INCIDENTS, prompt, model=model_backend.model_for_role(model_backend.ROLE_MATTER_INCIDENTS, backend="openrouter"),
        backend="openrouter", timeout=90, max_tokens=MAX_OUTPUT_TOKENS,
    )
    if not result.ok:
        raise IncidentExtractionError(
            f"incident extraction call failed: {result.attempts[-1].error if result.attempts else 'unknown'}"
        )
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", result.text.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IncidentExtractionError(f"incident extraction did not return valid JSON: {exc}. Raw: {raw[:300]!r}") from exc
    if not isinstance(parsed, list):
        raise IncidentExtractionError(f"incident extraction returned a non-list JSON value: {raw[:300]!r}")
    return [_clean_incident(item) for item in parsed if isinstance(item, dict)]


def _clean_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _clean_incident(item: dict[str, Any]) -> dict[str, Any]:
    confidence = str(item.get("confidence") or "").strip().lower()
    source_label = str(item.get("source_label") or "").strip().lower()
    return {
        "incident_date": str(item.get("incident_date") or "").strip(),
        "incident_type": str(item.get("incident_type") or "").strip(),
        "summary": str(item.get("summary") or "").strip(),
        "police_called": _clean_bool(item.get("police_called")),
        "crime_reference": str(item.get("crime_reference") or "").strip(),
        "arrest_status": str(item.get("arrest_status") or "").strip(),
        "bail_status": str(item.get("bail_status") or "").strip(),
        "source_label": source_label if source_label in _VALID_SOURCE_LABEL else "unclear",
        "confidence": confidence if confidence in _VALID_CONFIDENCE else "low",
    }


def _has_real_content(incident: dict[str, Any]) -> bool:
    "A row with no date, no description, and no reference is not a real"
    return bool(incident["incident_date"] or incident["summary"] or incident["incident_type"] or incident["crime_reference"])


def unmatched_crime_references(*, incidents: list[dict[str, Any]], fl401_text: str, ws_text: str, referral_text: str) -> list[str]:
    "Regex-found crime/CAD references (``ccl_pipeline``'s own"
    found = _extract_crime_references(f"{ws_text}\n{fl401_text}\n{referral_text}")
    reported = {incident["crime_reference"] for incident in incidents if incident["crime_reference"]}
    return sorted(ref for ref in found if ref not in reported)


def _existing_incident_keys(matter_id: str) -> set[tuple[str, str]]:
    sql = "SELECT incident_date, crime_reference, summary FROM matter_incidents WHERE matter_id = ?"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, (matter_id,))
        rows = cursor.fetchall()
    keys = set()
    for incident_date, crime_reference, summary in rows:
        keys.add(_dedup_key({
            "incident_date": str(incident_date or ""),
            "crime_reference": str(crime_reference or ""),
            "summary": str(summary or ""),
        }))
    return keys


def _dedup_key(incident: dict[str, Any]) -> tuple[str, str]:
    "(incident_date, crime_reference) when either is real -- distinct"
    date, ref = incident["incident_date"], incident["crime_reference"]
    if date or ref:
        return (date, ref)
    return ("", incident.get("summary", "")[:80])


def add_new_incidents(matter_id: str, incidents: list[dict[str, Any]], *, dry_run: bool = False) -> list[dict[str, Any]]:
    "INSERTs one row per incident not already present for this matter --"
    real_incidents = [incident for incident in incidents if _has_real_content(incident)]
    existing_keys = _existing_incident_keys(matter_id)
    added: list[dict[str, Any]] = []
    seen_this_run: set[tuple[str, str]] = set()
    for incident in real_incidents:
        key = _dedup_key(incident)
        if key in existing_keys or key in seen_this_run:
            continue
        seen_this_run.add(key)
        added.append(incident)
        if dry_run:
            continue
        with clientdb_sql.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO matter_incidents "
                "(matter_id, incident_date, incident_type, summary, police_called, crime_reference, "
                "arrest_status, bail_status, source_label, confidence, source_date, created_utc, updated_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    matter_id,
                    incident["incident_date"] or None,
                    incident["incident_type"] or None,
                    incident["summary"] or None,
                    incident["police_called"],
                    incident["crime_reference"] or None,
                    incident["arrest_status"] or None,
                    incident["bail_status"] or None,
                    incident["source_label"],
                    incident["confidence"],
                    None,
                    utc_now(),
                    utc_now(),
                ),
            )
    return added


def backfill_matter(client_name: str, matter_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    facts = gather_client_facts(client_name)
    incidents = extract_incidents(
        fl401_text=facts["fl401_text"], ws_text=facts["ws_text"], referral_text=facts["referral_body_text"]
    )
    added = add_new_incidents(matter_id, incidents, dry_run=dry_run)
    unmatched = unmatched_crime_references(
        incidents=incidents,
        fl401_text=facts["fl401_text"],
        ws_text=facts["ws_text"],
        referral_text=facts["referral_body_text"],
    )
    return {
        "matter_id": matter_id,
        "client_name": client_name,
        "incidents_extracted": len(incidents),
        "incidents_added": added,
        "unmatched_crime_references": unmatched,
    }


def scan(*, dry_run: bool = False, limit: int | None = None) -> dict[str, Any]:
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
        try:
            result = backfill_matter(client_name, matter_id, dry_run=dry_run)
        except (GatherError, IncidentExtractionError) as exc:
            summary["errored"].append({"client_name": client_name, "matter_id": matter_id, "reason": str(exc)})
            continue
        summary["applied"].append(result)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-name", help="AI-EXP client folder name, exactly as it appears on OneDrive")
    parser.add_argument("--matter-id", help="caseforge-clientdb matter_id to write incidents onto")
    parser.add_argument("--scan", action="store_true", help="Backfill every AI-EXP client that resolves to a real matter_id")
    parser.add_argument("--limit", type=int, default=None, help="With --scan, cap how many clients are processed")
    parser.add_argument("--dry-run", action="store_true", help="Extract and report but do not write")
    args = parser.parse_args(argv)

    if args.scan:
        summary = scan(dry_run=args.dry_run, limit=args.limit)
        print(json.dumps(summary, indent=2, default=str))
        return 1 if summary["errored"] else 0

    if not args.client_name or not args.matter_id:
        parser.error("--client-name and --matter-id (or --scan) are required")

    try:
        result = backfill_matter(args.client_name, args.matter_id, dry_run=args.dry_run)
    except (GatherError, IncidentExtractionError) as exc:
        print(json.dumps({"client_name": args.client_name, "matter_id": args.matter_id, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
