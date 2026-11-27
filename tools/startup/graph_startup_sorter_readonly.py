#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo


_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from email_sorter_common import (
    CHAMBERS_DOMAINS,
    COURT_DOMAINS,
    REFERRALPARTNER_ADDRESSES,
    any_address_match,
    any_domain_match,
    configure_stdout_utf8,
    is_auto_reply,
    is_ccms_allocation,
    is_drug_test,
    is_generic_vendor_marketing,
    is_gp,
    is_junk_subject,
    is_legal_aid,
    is_newsletter,
    is_police,
    is_process_server,
    is_school,
    is_work_experience,
    match_other_correspondence_route,
)
from caseforge_cli.chambers_finder import load_finder_data
from env_bootstrap import load_repo_secrets
from graph_mail_safe_ops import GraphClient, GraphError, _must
from startup.startup_scoring import score_startup_email
from telemetry_sqlite import record_state_snapshot


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LONDON_TZ = ZoneInfo("Europe/London")
DEFAULT_STATE_PATH = "telemetry/graph-startup-last-run.json"
DEFAULT_OUTPUT_DIR = "telemetry/graph-startup"
DEFAULT_CLIENT_STATUS_STATE = "/dev/shm/caseforge/client-live-status.json"
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
COURT_OR_MATTER_REF_RE = re.compile(
    r"\b([A-Z]{1,3}\d{2}[A-Z]\d{5}|[A-Z]{2}\d{2}[A-Z]\d{5}|\d{4}-\d{4}-\d{4}-\d{4})\b",
    re.IGNORECASE,
)
COMMON_NAME_FALSE_POSITIVES = {
    "dear",
    "family",
    "court",
    "justice",
    "solicitors",
    "application",
    "respondent",
    "applicant",
    "notice",
    "hearing",
    "order",
}


def _firm_name_words() -> frozenset[str]:
    try:
        import firm_profile

        return firm_profile.firm_name_words()
    except Exception:
        return frozenset()


COMMON_NAME_FALSE_POSITIVES |= _firm_name_words()
PARTY_V_RE = re.compile(
    r"\b([A-Z][A-Z' -]{1,80}?)\s*-?\s*V(?:S|ERSUS)?\.?\s*-?\s*([A-Z][A-Z' -]{1,80}?)(?=\s*(?:\||$|,|;))",
    re.IGNORECASE,
)
HEARING_DATE_TOKEN_RE = re.compile(
    r"(?P<token>\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+\d{4}\b)",
    re.IGNORECASE,
)
COUNSEL_ACCEPT_KEYWORDS = (
    "available",
    "can cover",
    "can do",
    "happy to accept",
    "able to assist",
    "able to cover",
    "counsel available",
    "we can assist",
    "booked",
    "accepted",
)
COUNSEL_REJECT_KEYWORDS = (
    "unable",
    "unavailable",
    "cannot",
    "can't",
    "no counsel available",
    "do not have counsel",
    "don't have counsel",
    "decline",
    "declined",
    "conflict",
    "not able to assist",
    "no counsel",
)
OBSERVER_ENV_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("GRAPH_OBSERVER_CLIENT_ID", "GRAPH_OBSERVER_CLIENT_SECRET"),
    ("GRAPH_OBSERVER_APP_ID", "GRAPH_OBSERVER_APP_SECRET"),
)
GRAPH_CREDENTIAL_SLOTS: Tuple[Tuple[Tuple[str, ...], Tuple[str, ...]], ...] = (
    (("GRAPH_OBSERVER_APP_ID", "GRAPH_OBSERVER_CLIENT_ID"), ("GRAPH_OBSERVER_APP_SECRET", "GRAPH_OBSERVER_CLIENT_SECRET")),
    (("GRAPH_MAIL_CLIENT_ID",), ("GRAPH_MAIL_CLIENT_SECRET",)),
    (("GRAPH_CLIENT_ID",), ("GRAPH_CLIENT_SECRET",)),
)


def _env_group_present(group: Sequence[str]) -> bool:
    return any(os.getenv(key, "").strip() for key in group)


def _credential_slot_present() -> bool:
    return any(_env_group_present(ids) and _env_group_present(secrets) for ids, secrets in GRAPH_CREDENTIAL_SLOTS)


def bootstrap_runtime_env() -> List[str]:

    if _env_group_present(("GRAPH_TENANT_ID",)) and _env_group_present(("GRAPH_MAILBOX_UPN",)) and _credential_slot_present():
        return []
    return load_repo_secrets(repo_root=REPO_ROOT, required_keys=())


@dataclass(frozen=True)
class ClientMatch:
    name: str
    matter_id: str = ""
    live_matter_folder: str = ""


def parse_args() -> argparse.Namespace:
    bootstrap_runtime_env()
    parser = argparse.ArgumentParser(description="Read-only Graph startup sorter")
    parser.add_argument("--repo-root", default=str(Path.cwd()), help="Repository root")
    parser.add_argument("--folder", default="Inbox", help="Mailbox folder")
    parser.add_argument("--top", type=int, default=250, help="Number of latest emails to inspect")
    parser.add_argument("--since-iso", default="", help="UTC ISO timestamp override (e.g. 2026-03-05T09:34:48Z)")
    parser.add_argument("--until-iso", default="", help="Stop at this UTC ISO timestamp — backfill upper bound (e.g. 2026-03-31T00:00:00Z)")
    parser.add_argument("--state-file", default=DEFAULT_STATE_PATH, help="State file used for incremental scans")
    parser.add_argument(
        "--client-status-state",
        default=DEFAULT_CLIENT_STATUS_STATE,
        help="Persistent per-client live status state derived from mailbox changes",
    )
    parser.add_argument("--no-write-state", action="store_true", help="Do not update state file")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for reports")
    parser.add_argument("--no-md-report", action="store_true", help="Skip markdown report output")
    parser.add_argument("--max-retries", type=int, default=5, help="Retry attempts for transient failures")
    parser.add_argument("--retry-base-seconds", type=float, default=0.8, help="Base retry delay in seconds")
    parser.add_argument(
        "--credential-preference",
        default="mail,read,shared",
        help="Credential slot order to try (mail,read,shared)",
    )

    parser.add_argument("--tenant-id", default="", help="Entra tenant ID")
    parser.add_argument("--client-id", default="", help="Graph app client ID")
    parser.add_argument("--client-secret", default="", help="Graph app client secret")
    parser.add_argument("--mailbox-upn", default="", help="Mailbox UPN")
    return parser.parse_args()


def _observer_credential_from_env() -> Tuple[str, str]:
    for id_name, secret_name in OBSERVER_ENV_PAIRS:
        client_id = os.getenv(id_name, "").strip()
        client_secret = os.getenv(secret_name, "").strip()
        if client_id and client_secret:
            return client_id, client_secret
    return "", ""


def resolve_graph_credential_candidates(args: argparse.Namespace) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    explicit_client_id = (args.client_id or "").strip()
    explicit_client_secret = (args.client_secret or "").strip()
    if explicit_client_id and explicit_client_secret:
        candidates.append(
            {
                "slot": "explicit",
                "client_id": explicit_client_id,
                "client_secret": explicit_client_secret,
            }
        )
        seen.add((explicit_client_id, explicit_client_secret))

    for raw_slot in str(args.credential_preference or "").split(","):
        slot = raw_slot.strip().lower()
        if not slot:
            continue
        if slot == "read":
            client_id, client_secret = _observer_credential_from_env()
        elif slot == "mail":
            client_id = os.getenv("GRAPH_MAIL_CLIENT_ID", "").strip()
            client_secret = os.getenv("GRAPH_MAIL_CLIENT_SECRET", "").strip()
        elif slot == "shared":
            client_id = os.getenv("GRAPH_CLIENT_ID", "").strip()
            client_secret = os.getenv("GRAPH_CLIENT_SECRET", "").strip()
        else:
            continue

        if not client_id or not client_secret:
            continue
        fingerprint = (client_id, client_secret)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        candidates.append(
            {
                "slot": slot,
                "client_id": client_id,
                "client_secret": client_secret,
            }
        )

    return candidates


def parse_graph_dt(raw: str) -> Optional[dt.datetime]:
    if not raw:
        return None
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse_last_check_utc(repo_root: Path) -> Optional[dt.datetime]:
    path = repo_root / "tools" / "startup" / "last-check.txt"
    if not path.exists():
        return None
    payload = read_json(path)
    raw = str(payload.get("timestamp", "")).strip()
    if not raw:
        return None
    try:
        local = dt.datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    local_aware = local.replace(tzinfo=LONDON_TZ)
    return local_aware.astimezone(dt.timezone.utc)


def resolve_since_utc(repo_root: Path, state_path: Path, since_iso: str) -> dt.datetime:
    if since_iso.strip():
        parsed = parse_graph_dt(since_iso.strip())
        if parsed:
            return parsed

    if state_path.exists():
        state = read_json(state_path)
        state_ts = parse_graph_dt(str(state.get("last_scan_utc", "")).strip())
        if state_ts:
            return state_ts

    from_last_check = parse_last_check_utc(repo_root)
    if from_last_check:
        return from_last_check

    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)


def recipients_to_text(rows: List[Dict[str, Any]]) -> str:
    values: List[str] = []
    for row in rows or []:
        email_obj = (row or {}).get("emailAddress", {}) or {}
        name = str(email_obj.get("name", "")).strip()
        addr = str(email_obj.get("address", "")).strip()
        if name and addr:
            values.append(f"{name} <{addr}>")
        elif addr:
            values.append(addr)
    return "; ".join(values)


def infer_category(meta: Dict[str, str]) -> str:
    subject = meta.get("subject", "")
    fields = [meta.get("from", ""), meta.get("to", ""), meta.get("cc", ""), meta.get("bcc", "")]

    if is_auto_reply(subject):
        return "Junk/Auto Replies"
    if is_newsletter(subject):
        return "Junk/Newsletters"
    if is_junk_subject(subject):
        return "Junk"
    if is_generic_vendor_marketing(meta):
        return "Junk"
    if is_ccms_allocation(meta):
        return "CCMS Allocation"
    if is_work_experience(meta):
        return "Work Experience"
    if is_legal_aid(meta):
        return "Legal Aid Confirmation"
    if is_process_server(fields, subject):
        return "Process Server"
    if is_drug_test(fields, subject):
        return "Drug Test Labs"
    if is_gp(fields, subject):
        return "GP"
    other_route = match_other_correspondence_route(fields, subject, meta.get("body", ""))
    if other_route:
        return other_route
    if is_school(fields, subject):
        return "School"
    if is_police(fields):
        return "Police"
    if any_domain_match(fields, COURT_DOMAINS):
        return "Court"
    if any_domain_match(fields, CHAMBERS_DOMAINS):
        return "Counsel"
    if any_address_match([meta.get("from", "")], REFERRALPARTNER_ADDRESSES):
        return "ReferralPartner"
    return "Clients"


def mailbox_position(mailbox_upn: str, to_text: str, cc_text: str, bcc_text: str) -> str:
    probe = mailbox_upn.lower().strip()
    if probe and probe in to_text.lower():
        return "To"
    if probe and probe in cc_text.lower():
        return "CC"
    if probe and probe in bcc_text.lower():
        return "BCC"
    return "BCC/Implicit"


def normalise_subject(subject: str) -> str:
    cleaned = re.sub(r"\s+", " ", subject.strip())
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "", cleaned)
    return cleaned[:120] if cleaned else "untitled"


def split_mail_folders(raw: str) -> List[str]:
    values = [part.strip() for part in str(raw or "").split(",") if part.strip()]
    return values or ["Inbox"]


def normalise_client_key(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", (value or "").strip().lower())
    return re.sub(r"\s+", " ", text).strip()


def normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dedupe_keep_order(values: List[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        cleaned = normalise_space(value)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _client_candidate_terms(meta: Dict[str, str], snippet: str) -> List[str]:
    terms: List[str] = []
    header_blob = " ".join([meta.get("subject", ""), meta.get("from", ""), meta.get("to", ""), meta.get("cc", "")])
    full_blob = f"{header_blob}\n{snippet[:3000]}"

    terms.extend(match.group(1) for match in COURT_OR_MATTER_REF_RE.finditer(full_blob))
    terms.extend(match.group(0) for match in EMAIL_RE.finditer(header_blob))
    for match in PARTY_V_RE.finditer(meta.get("subject", "")):
        for side in (match.group(1), match.group(2)):
            cleaned = normalise_space(re.sub(r"[^A-Z' -]", " ", side, flags=re.IGNORECASE)).title()
            words = {part.lower() for part in cleaned.split()}
            if cleaned and not words & COMMON_NAME_FALSE_POSITIVES:
                terms.append(cleaned)

    subject = re.sub(r"^(re|fw|fwd):\s*", "", meta.get("subject", ""), flags=re.IGNORECASE).strip()
    subject = re.sub(r"\b(case|matter|ref|reference|applicant|respondent|hearing|order|application)\b[:#]?", " ", subject, flags=re.IGNORECASE)
    subject = normalise_space(subject)
    if 4 <= len(subject) <= 90:
        terms.append(subject)

    name_probe = f"{meta.get('subject', '')} {meta.get('from', '')}"
    for match in re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b", name_probe):
        candidate = normalise_space(match.group(0))
        words = {part.lower() for part in candidate.split()}
        if words & COMMON_NAME_FALSE_POSITIVES:
            continue
        terms.append(candidate)

    return _dedupe_keep_order(terms)[:25]


_CLIENT_MATCH_SEARCH_CACHE: Dict[str, List[dict]] = {}


def _normalise_search_term(term: str) -> str:
    return " ".join(str(term or "").split()).casefold()


def reset_client_match_cache() -> None:
    _CLIENT_MATCH_SEARCH_CACHE.clear()


def match_client_from_sql(repo_root: Path, meta: Dict[str, str], snippet: str) -> Optional[ClientMatch]:
    terms = _client_candidate_terms(meta, snippet)
    if not terms:
        return None
    tools_dir = str(repo_root / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import agwu
    except Exception:
        return None

    for term in terms:
        cache_key = _normalise_search_term(term)
        if cache_key in _CLIENT_MATCH_SEARCH_CACHE:
            rows = _CLIENT_MATCH_SEARCH_CACHE[cache_key]
        else:
            try:
                rows = [
                    m.row
                    for m in agwu.resolve_client(
                        term, limit=3, caller="graph_startup_sorter_readonly.match_client_from_sql"
                    ).matches
                ]
            except Exception:
                continue
            _CLIENT_MATCH_SEARCH_CACHE[cache_key] = rows
        if not rows:
            continue
        by_matter: dict[str, dict] = {}
        for row in rows:
            key = str(row.get("matter_id") or "").strip()
            if not key:
                key = "|".join(
                    str(row.get(field) or "").strip().lower()
                    for field in ("client_name", "matter_name", "company_reference")
                )
            by_matter.setdefault(key, row)
        if len(by_matter) != 1:
            continue
        row = next(iter(by_matter.values()))
        name = normalise_space(str(row.get("client_name") or row.get("matter_name") or ""))
        if not name:
            continue
        return ClientMatch(
            name=name,
            matter_id=str(row.get("matter_id") or "").strip(),
            live_matter_folder=normalise_space(str(row.get("live_matter_folder") or "")),
        )
    return None


def load_counsel_watchlist(repo_root: Path) -> List[Dict[str, Any]]:
    payload = load_finder_data()
    if payload is None:
        return []
    rows = payload.get("chambers", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    watchlist: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = normalise_space(str(row.get("name", "")))
        email = normalise_space(str(row.get("email", ""))).lower()
        domain = email.split("@", 1)[1] if "@" in email else ""
        raw_barristers = row.get("watchBarristers", [])
        barristers: List[Dict[str, str]] = []
        if isinstance(raw_barristers, list):
            for item in raw_barristers:
                display = normalise_space(str(item))
                if not display:
                    continue
                barristers.append({"display": display, "needle": display.lower()})
        if not bool(row.get("doNotUse")) and not barristers:
            continue
        watchlist.append(
            {
                "name": name,
                "name_lower": name.lower(),
                "domain": domain,
                "do_not_use": bool(row.get("doNotUse")),
                "watch_barristers": barristers,
            }
        )
    return watchlist


def iso_utc(value: Optional[dt.datetime]) -> str:
    if value is None:
        return ""
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def subject_snippet(subject: str, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", (subject or fallback or "").strip())
    if len(text) > 160:
        return text[:157] + "..."
    return text


def parse_hearing_date_token(value: str) -> Optional[dt.date]:
    text = re.sub(r"\s+", " ", (value or "").strip())
    if not text:
        return None
    match = HEARING_DATE_TOKEN_RE.search(text)
    if not match:
        return None
    token = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", match.group("token"), flags=re.IGNORECASE)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%y", "%d-%m-%y", "%d %B %Y"):
        try:
            parsed = dt.datetime.strptime(token, fmt)
            if parsed.year < 100:
                parsed = parsed.replace(year=2000 + parsed.year)
            return parsed.date()
        except ValueError:
            continue
    return None


def sanitise_next_hearing_value(value: str, reference_dt: Optional[dt.datetime]) -> str:
    text = subject_snippet(value)
    if not text:
        return ""
    hearing_date = parse_hearing_date_token(text)
    if hearing_date is None or reference_dt is None:
        return text
    if hearing_date < reference_dt.date():
        return ""
    return text


def fetch_folder_messages(
    graph_client: GraphClient,
    folder: str,
    top: int,
    since_utc: Optional[dt.datetime] = None,
) -> List[Dict[str, Any]]:
    SELECT_FIELDS = (
        "id,subject,receivedDateTime,sentDateTime,from,toRecipients,ccRecipients,bccRecipients,"
        "categories,hasAttachments,importance,internetMessageId,webLink,bodyPreview,body"
    )
    folder_encoded = urllib.parse.quote(folder, safe="")
    base_path = graph_client.mailbox_path(f"/mailFolders/{folder_encoded}/messages")
    extra_headers = {"Prefer": 'outlook.body-content-type="text"'}
    rows: List[Dict[str, Any]] = []

    if since_utc is not None:
        since_str = since_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "$filter": f"receivedDateTime gt {since_str}",
            "$select": SELECT_FIELDS,
            "$top": "50",
        }
        page = graph_client.graph("GET", base_path, params=params, extra_headers=extra_headers)
        while True:
            page_rows = page.get("value", [])
            for row in page_rows:
                row["_source_folder"] = folder
            rows.extend(page_rows)
            next_link = page.get("@odata.nextLink")
            if not next_link or not page_rows:
                break
            page = graph_client.graph("GET", next_link, extra_headers=extra_headers)
    else:
        params = {
            "$top": str(max(1, int(top))),
            "$orderby": "receivedDateTime desc",
            "$select": SELECT_FIELDS,
        }
        page = graph_client.graph("GET", base_path, params=params, extra_headers=extra_headers)
        rows = list(page.get("value", []))
        for row in rows:
            row["_source_folder"] = folder

    return rows


def default_client_status(client_name: str, name_key: str) -> Dict[str, Any]:
    return {
        "client": client_name,
        "name_key": name_key,
        "last_email_received_utc": "",
        "last_email_subject": "",
        "last_email_category": "",
        "last_email_folder": "",
        "last_client_chase_utc": "",
        "last_client_chase_subject": "",
        "last_client_notification_utc": "",
        "last_client_notification_subject": "",
        "last_client_ack_utc": "",
        "last_client_ack_subject": "",
        "last_counsel_request_utc": "",
        "last_counsel_request_subject": "",
        "counsel_response_status": "",
        "last_counsel_response_utc": "",
        "last_counsel_response_subject": "",
        "last_counsel_watch_utc": "",
        "last_counsel_watch_subject": "",
        "counsel_watch_alerts": [],
        "order_status": "",
        "sealed_order_status": "",
        "service_status": "",
        "next_hearing": "",
        "awaiting": "",
        "latest_live_status": "",
        "status_last_changed_utc": "",
        "attention_flags": [],
    }


def load_client_status_state(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    raw_clients = payload.get("clients", {}) if isinstance(payload, dict) else {}
    result: Dict[str, Dict[str, Any]] = {}
    if not isinstance(raw_clients, dict):
        return result
    for key, value in raw_clients.items():
        if isinstance(value, dict):
            result[str(key)] = dict(value)
    return result


def sync_client_status_to_local_sqlite(status_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    sqlite_path = os.getenv("LOCAL_SQLITE_PATH", "").strip()
    if not sqlite_path:
        return {"skipped": "LOCAL_SQLITE_PATH not set"}
    path = Path(sqlite_path)
    if not path.exists():
        return {"skipped": f"LOCAL_SQLITE_PATH not found: {sqlite_path}"}

    updated = 0
    unmatched: list[str] = []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS matter_live_status (
                matter_id INTEGER PRIMARY KEY,
                latest_live_status TEXT,
                order_status TEXT,
                sealed_order_status TEXT,
                service_status TEXT,
                next_hearing_text TEXT,
                awaiting_next_step TEXT,
                last_client_chase TEXT,
                last_material_email_received TEXT,
                last_material_email_subject TEXT,
                status_changed_at TEXT,
                created_utc TEXT,
                updated_utc TEXT,
                draft_order_status TEXT,
                waiting_for_sealed_order INTEGER
            )
            """
        )
        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        for status in status_map.values():
            client_name = str(status.get("client", "") or "").strip()
            if not client_name:
                continue
            row = conn.execute(
                """
                SELECT m.matter_id
                FROM matters m
                JOIN people p ON p.person_id = m.primary_person_id
                WHERE lower(p.canonical_name) = lower(?)
                   OR lower(m.canonical_name) = lower(?)
                ORDER BY m.updated_utc DESC, m.matter_id DESC
                LIMIT 1
                """,
                (client_name, client_name),
            ).fetchone()
            if row is None:
                unmatched.append(client_name)
                continue
            matter_id = row["matter_id"]
            conn.execute(
                """
                INSERT INTO matter_live_status (
                    matter_id, latest_live_status, order_status, sealed_order_status,
                    service_status, next_hearing_text, awaiting_next_step,
                    last_client_chase, last_material_email_received,
                    last_material_email_subject, status_changed_at, created_utc,
                    updated_utc, draft_order_status, waiting_for_sealed_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(matter_id) DO UPDATE SET
                    latest_live_status = excluded.latest_live_status,
                    order_status = excluded.order_status,
                    sealed_order_status = excluded.sealed_order_status,
                    service_status = excluded.service_status,
                    next_hearing_text = excluded.next_hearing_text,
                    awaiting_next_step = excluded.awaiting_next_step,
                    last_client_chase = excluded.last_client_chase,
                    last_material_email_received = excluded.last_material_email_received,
                    last_material_email_subject = excluded.last_material_email_subject,
                    status_changed_at = excluded.status_changed_at,
                    updated_utc = excluded.updated_utc,
                    draft_order_status = excluded.draft_order_status,
                    waiting_for_sealed_order = excluded.waiting_for_sealed_order
                """,
                (
                    matter_id,
                    str(status.get("latest_live_status", "") or ""),
                    str(status.get("order_status", "") or ""),
                    str(status.get("sealed_order_status", "") or ""),
                    str(status.get("service_status", "") or ""),
                    str(status.get("next_hearing", "") or ""),
                    str(status.get("awaiting", "") or ""),
                    str(status.get("last_client_chase_utc", "") or ""),
                    str(status.get("last_email_received_utc", "") or ""),
                    str(status.get("last_email_subject", "") or ""),
                    str(status.get("status_last_changed_utc", "") or ""),
                    now,
                    now,
                    str(status.get("draft_order_status", "") or ""),
                    1 if str(status.get("sealed_order_status", "") or "").lower() == "awaiting sealed order" else 0,
                ),
            )
            updated += 1
        conn.commit()
    return {"updated": updated, "unmatched": unmatched[:50], "unmatched_count": len(unmatched), "sqlite_path": str(path)}


def load_root_card_next_hearing(repo_root: Path, client_name: str, received_dt: dt.datetime) -> str:
    return ""


def detect_next_hearing(text: str, received_dt: dt.datetime) -> str:
    patterns = [
        r"(?:new\s+hearing\s+date|hearing(?: date)?|return hearing|listed(?: for)?|hearing on)\s*(?:of|on|for|at)?\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        r"(?:new\s+hearing\s+date|hearing(?: date)?|return hearing|listed(?: for)?|hearing on)\s*(?:of|on|for|at)?\s*[:\-]?\s*((?:\d{1,2}(?:st|nd|rd|th)?\s+)?[A-Z][a-z]+\s+\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return sanitise_next_hearing_value(match.group(1), received_dt)
    if re.search(r"\bhearing today\b|\bhrg today\b|\blisted today\b", text, flags=re.IGNORECASE):
        return received_dt.astimezone(dt.timezone.utc).strftime("%d %B %Y") + " (today)"
    return ""


def detect_order_status(text_lower: str, folder: str) -> str:
    if re.search(r"\b(not granted|refused|dismissed|declined)\b", text_lower):
        return "not granted"
    if "granted ex parte" in text_lower or "granted on an ex parte basis" in text_lower or "granted without notice" in text_lower:
        return "granted ex parte"
    if "made final" in text_lower:
        return "made final"
    if "order made" in text_lower or re.search(r"\bgranted\b", text_lower):
        return "granted"
    if "application has been filed with the court" in text_lower:
        return "application filed"
    if folder.lower() == "sentitems" and "application for a non-molestation order" in text_lower and "place the attached applications" in text_lower:
        return "application filed"
    if "without notice" in text_lower and re.search(r"\blisted\b|\bhearing\b", text_lower):
        return "without notice listed"
    return ""


def detect_sealed_order_status(text_lower: str, category: str, has_attachments: bool) -> str:
    if re.search(r"\b(awaiting|await|once received|upon receipt|pending)\b.*sealed order|sealed order.*\b(awaiting|await|pending)\b", text_lower):
        return "awaiting sealed order"
    if "sealed order" in text_lower and ("attached" in text_lower or "please see" in text_lower or has_attachments or category == "Court"):
        return "received"
    if category == "Court" and has_attachments and re.search(r"\border\b", text_lower) and "draft order" not in text_lower:
        return "received"
    return ""


def detect_service_status(text_lower: str, folder: str, category: str) -> str:
    if re.search(r"\b(not served yet|not yet served|has not been served|this has not been served)\b", text_lower):
        return "not yet served"
    if re.search(r"\b(attempted service|attempted to serve|unable to serve|could not serve|service unsuccessful)\b", text_lower):
        return "attempted not served"
    if "statement of service" in text_lower and (folder.lower() == "sentitems" or "filing" in text_lower or "attached" in text_lower):
        return "statement of service filed"
    if re.search(r"\bserved by whatsapp\b|\balready been served\b|\bhas been served\b|\bserved on the respondent\b", text_lower):
        return "served"
    if folder.lower() == "sentitems" and re.search(r"\bpersonal service\b|\bfor service on the respondent\b|\border for personal service\b", text_lower):
        return "sent for service"
    if category == "Court" and re.search(r"\bfor service on the respondent\b|\bplease serve a copy on the respondent\b", text_lower):
        return "service directed"
    return ""


def is_client_chase(category: str, from_text: str, mailbox_upn: str, text_lower: str) -> bool:
    if category != "Clients":
        return False
    probe = mailbox_upn.lower().strip()
    if probe and probe in from_text.lower():
        return False
    return bool(
        re.search(
            r"\b(update|any update|any news|chasing|heard anything|what is happening|where are we up to|served|sealed order|hearing)\b",
            text_lower,
        )
    )


def is_client_notification_out(category: str, folder: str, text_lower: str) -> bool:
    if category != "Clients" or folder.lower() != "sentitems":
        return False
    return any(
        keyword in text_lower
        for keyword in (
            "notice of hearing",
            "hearing link",
            "cvp",
            "cloud video platform",
            "teams link",
            "order attached",
            "attached order",
            "sealed order",
            "return hearing",
            "final hearing",
            "hearing on ",
            "please find attached your order",
            "please find attached the order",
            "please find attached your notice of hearing",
            "please find attached the notice of hearing",
        )
    )


def is_client_acknowledgement(
    category: str,
    folder: str,
    from_text: str,
    mailbox_upn: str,
    text_lower: str,
    last_notification_utc: str,
    received_dt: dt.datetime,
) -> bool:
    if category != "Clients" or folder.lower() == "sentitems":
        return False
    probe = mailbox_upn.lower().strip()
    if probe and probe in from_text.lower():
        return False
    last_notification_dt = parse_graph_dt(last_notification_utc)
    if last_notification_dt is not None and received_dt < last_notification_dt:
        return False
    ack_hit = any(
        phrase in text_lower
        for phrase in (
            "thank you",
            "thanks",
            "ok thanks",
            "okay thanks",
            "noted",
            "understood",
            "received",
            "i have received",
            "i've received",
            "i have got it",
            "got it",
            "seen",
            "i will attend",
            "i can attend",
        )
    )
    notice_hit = any(
        keyword in text_lower
        for keyword in (
            "order",
            "notice of hearing",
            "hearing",
            "cvp",
            "teams",
            "link",
        )
    )
    if ack_hit and notice_hit:
        return True
    if ack_hit and len(text_lower.strip()) <= 240:
        return True
    return False


def is_counsel_request_out(category: str, folder: str, text_lower: str) -> bool:
    return category == "Counsel" and folder.lower() == "sentitems" and "request for counsel" in text_lower


def detect_counsel_reply_status(category: str, folder: str, text_lower: str) -> str:
    if category != "Counsel" or folder.lower() == "sentitems":
        return ""
    if any(keyword in text_lower for keyword in COUNSEL_REJECT_KEYWORDS):
        return "rejected"
    if any(keyword in text_lower for keyword in COUNSEL_ACCEPT_KEYWORDS):
        return "accepted"
    if "counsel" in text_lower or "clerk" in text_lower or "fee note" in text_lower:
        return "replied"
    return ""


def working_days_until_next_hearing(status: Dict[str, Any]) -> Optional[int]:
    hearing_date = parse_hearing_date_token(str(status.get("next_hearing", "")).strip())
    if hearing_date is None:
        return None
    today = dt.datetime.now(dt.timezone.utc).date()
    if hearing_date < today:
        return None
    count = 0
    cursor = today
    while cursor < hearing_date:
        if cursor.weekday() < 5:
            count += 1
        cursor += dt.timedelta(days=1)
    return count


def update_counsel_tracking(
    status: Dict[str, Any],
    *,
    category: str,
    folder: str,
    text_lower: str,
    received_dt: dt.datetime,
    subject: str,
    changed_fields: set[str],
) -> None:
    if is_counsel_request_out(category, folder, text_lower):
        request_utc = iso_utc(received_dt)
        status["last_counsel_request_utc"] = request_utc
        status["last_counsel_request_subject"] = subject
        if str(status.get("counsel_response_status", "")).strip().lower() != "awaiting response":
            changed_fields.add("counsel_response_status")
        status["counsel_response_status"] = "awaiting response"
        status["last_counsel_response_utc"] = ""
        status["last_counsel_response_subject"] = ""
        status["last_counsel_watch_utc"] = ""
        status["last_counsel_watch_subject"] = ""
        status["counsel_watch_alerts"] = []
        status["status_last_changed_utc"] = request_utc
        return

    reply_status = detect_counsel_reply_status(category, folder, text_lower)
    if not reply_status:
        return
    last_request = parse_graph_dt(str(status.get("last_counsel_request_utc", "")).strip())
    if last_request and received_dt < last_request:
        return
    if str(status.get("counsel_response_status", "")).strip().lower() != reply_status:
        changed_fields.add("counsel_response_status")
        status["status_last_changed_utc"] = iso_utc(received_dt)
    status["counsel_response_status"] = reply_status
    status["last_counsel_response_utc"] = iso_utc(received_dt)
    status["last_counsel_response_subject"] = subject


def detect_counsel_watch_alerts(
    *,
    category: str,
    folder: str,
    subject: str,
    text_lower: str,
    from_text: str,
    to_text: str,
    cc_text: str,
    watchlist: List[Dict[str, Any]],
) -> List[str]:
    if category != "Counsel" or folder.lower() == "sentitems" or not watchlist:
        return []
    haystack = " ".join(part for part in (subject, from_text, to_text, cc_text, text_lower) if part).lower()
    alerts: List[str] = []
    for entry in watchlist:
        chamber_name = str(entry.get("name", "")).strip()
        chamber_hit = False
        domain = str(entry.get("domain", "")).strip().lower()
        name_lower = str(entry.get("name_lower", "")).strip().lower()
        if domain and domain in haystack:
            chamber_hit = True
        if name_lower and name_lower in haystack:
            chamber_hit = True
        if chamber_hit and bool(entry.get("do_not_use")):
            alerts.append(f"Owner review: do-not-use chambers involved - {chamber_name}")
        for barrister in entry.get("watch_barristers", []):
            if not isinstance(barrister, dict):
                continue
            needle = str(barrister.get("needle", "")).strip().lower()
            display = str(barrister.get("display", "")).strip()
            if not needle or needle not in haystack:
                continue
            if any(keyword in text_lower for keyword in COUNSEL_ACCEPT_KEYWORDS):
                alerts.append(f"Owner review: {display} offered by {chamber_name}")
            else:
                alerts.append(f"Owner review: {display} mentioned in {chamber_name} thread")
    return list(dict.fromkeys(alerts))


def update_counsel_watch_tracking(
    status: Dict[str, Any],
    *,
    alerts: List[str],
    received_dt: dt.datetime,
    subject: str,
    changed_fields: set[str],
) -> None:
    if not alerts:
        return
    previous = [str(item).strip() for item in status.get("counsel_watch_alerts", []) if str(item).strip()]
    merged = list(dict.fromkeys(previous + alerts))
    if previous != merged:
        changed_fields.add("counsel_watch_alerts")
        status["status_last_changed_utc"] = iso_utc(received_dt)
    status["counsel_watch_alerts"] = merged
    status["last_counsel_watch_utc"] = iso_utc(received_dt)
    status["last_counsel_watch_subject"] = subject


def derive_awaiting(status: Dict[str, Any]) -> str:
    service_status = str(status.get("service_status", "")).strip().lower()
    order_status = str(status.get("order_status", "")).strip().lower()
    sealed_order_status = str(status.get("sealed_order_status", "")).strip().lower()
    next_hearing = str(status.get("next_hearing", "")).strip()

    if service_status in {"service directed", "sent for service", "not yet served", "attempted not served"}:
        return "service / statement of service"
    if order_status in {"application filed", "without notice listed"} and sealed_order_status != "received":
        return "court order / listing"
    if sealed_order_status == "received" and not service_status:
        return "service arrangements"
    if next_hearing:
        return f"hearing on {next_hearing}"
    return ""


def build_attention_flags(status: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    order_status = str(status.get("order_status", "")).strip().lower()
    sealed_order_status = str(status.get("sealed_order_status", "")).strip().lower()
    service_status = str(status.get("service_status", "")).strip().lower()
    next_hearing = str(status.get("next_hearing", "")).strip()
    last_client_chase = str(status.get("last_client_chase_utc", "")).strip()

    if order_status in {"granted", "granted ex parte", "made final"} and not sealed_order_status:
        flags.append("Sealed order not yet recorded")
    if order_status in {"granted", "granted ex parte", "made final"} and not service_status:
        flags.append("Service status not yet recorded")
    if service_status in {"service directed", "sent for service", "not yet served", "attempted not served"}:
        flags.append("Service still pending completion")
    if order_status and not next_hearing and order_status in {"granted", "granted ex parte", "made final", "without notice listed"}:
        flags.append("Next hearing/date not yet recorded")

    counsel_status = str(status.get("counsel_response_status", "")).strip().lower()
    last_counsel_request = parse_graph_dt(str(status.get("last_counsel_request_utc", "")).strip())
    hearing_working_days = working_days_until_next_hearing(status)
    today = dt.datetime.now(dt.timezone.utc).date()
    if last_counsel_request:
        if counsel_status in {"", "awaiting response"}:
            flags.append("Counsel request awaiting reply")
            if last_counsel_request.date() < today and hearing_working_days is not None and hearing_working_days <= 1:
                flags.append("Urgent counsel request unanswered; draft next chambers")
        elif counsel_status == "rejected":
            flags.append("Counsel rejected; draft next chambers")
        elif counsel_status == "replied":
            flags.append("Counsel replied; outcome unclear")

    if last_client_chase:
        flags.append("Client chased for update")
    for alert in status.get("counsel_watch_alerts", []):
        alert_text = str(alert).strip()
        if alert_text:
            flags.append(alert_text)
    return flags


def sanitise_client_status(status: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(status)
    reference_dt = parse_graph_dt(str(cleaned.get("last_email_received_utc", "")).strip()) or parse_graph_dt(
        str(cleaned.get("status_last_changed_utc", "")).strip()
    )
    next_hearing = sanitise_next_hearing_value(str(cleaned.get("next_hearing", "")).strip(), reference_dt)
    if not next_hearing and str(cleaned.get("awaiting", "")).strip().lower().startswith("hearing on "):
        cleaned["awaiting"] = "operative next hearing date confirmation"
    cleaned["next_hearing"] = next_hearing

    request_dt = parse_graph_dt(str(cleaned.get("last_counsel_request_utc", "")).strip())
    response_dt = parse_graph_dt(str(cleaned.get("last_counsel_response_utc", "")).strip())
    if request_dt and response_dt and response_dt < request_dt:
        cleaned["counsel_response_status"] = "awaiting response"
        cleaned["last_counsel_response_utc"] = ""
        cleaned["last_counsel_response_subject"] = ""
    notification_dt = parse_graph_dt(str(cleaned.get("last_client_notification_utc", "")).strip())
    ack_dt = parse_graph_dt(str(cleaned.get("last_client_ack_utc", "")).strip())
    if notification_dt and ack_dt and ack_dt < notification_dt:
        cleaned["last_client_ack_utc"] = ""
        cleaned["last_client_ack_subject"] = ""
    return cleaned


def compose_latest_live_status(status: Dict[str, Any]) -> str:
    pieces: List[str] = []
    order_status = str(status.get("order_status", "")).strip()
    sealed_order_status = str(status.get("sealed_order_status", "")).strip()
    service_status = str(status.get("service_status", "")).strip()
    next_hearing = str(status.get("next_hearing", "")).strip()
    awaiting = str(status.get("awaiting", "")).strip()
    counsel_status = str(status.get("counsel_response_status", "")).strip()
    last_counsel_request = str(status.get("last_counsel_request_utc", "")).strip()
    if order_status:
        pieces.append(f"Order: {order_status}")
    if sealed_order_status:
        pieces.append(f"Sealed order: {sealed_order_status}")
    if service_status:
        pieces.append(f"Service: {service_status}")
    if next_hearing:
        pieces.append(f"Next hearing: {next_hearing}")
    if last_counsel_request:
        counsel_display = counsel_status or "awaiting response"
        pieces.append(f"Counsel: {counsel_display}")
    watch_alerts = [str(item).strip() for item in status.get("counsel_watch_alerts", []) if str(item).strip()]
    if watch_alerts:
        pieces.append(f"Counsel review: {' / '.join(watch_alerts)}")
    if awaiting:
        pieces.append(f"Awaiting: {awaiting}")
    return "; ".join(pieces)


def update_status_field(
    status: Dict[str, Any],
    field: str,
    value: str,
    received_dt: dt.datetime,
    changed_fields: set[str],
) -> None:
    text = str(value or "").strip()
    if not text:
        return
    if str(status.get(field, "")).strip() == text:
        return
    status[field] = text
    status["status_last_changed_utc"] = iso_utc(received_dt)
    changed_fields.add(field)


def main() -> int:
    configure_stdout_utf8()
    args = parse_args()
    reset_client_match_cache()

    repo_root = Path(args.repo_root).resolve()
    counsel_watchlist = load_counsel_watchlist(repo_root)
    state_path = Path(args.state_file)
    if not state_path.is_absolute():
        state_path = repo_root / state_path
    client_status_state_path = Path(args.client_status_state)
    if not client_status_state_path.is_absolute():
        client_status_state_path = repo_root / client_status_state_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    tenant_id = _must(args.tenant_id or os.getenv("GRAPH_TENANT_ID", ""), "GRAPH_TENANT_ID / --tenant-id")
    mailbox_upn = _must(args.mailbox_upn or os.getenv("GRAPH_MAILBOX_UPN", ""), "GRAPH_MAILBOX_UPN / --mailbox-upn")

    since_utc = resolve_since_utc(repo_root, state_path, args.since_iso)
    until_utc: Optional[dt.datetime] = None
    if args.until_iso.strip():
        until_utc = parse_graph_dt(args.until_iso.strip())

    payload_rows: List[Dict[str, Any]] = []
    client: Optional[GraphClient] = None
    credential_slot = ""
    credential_errors: List[Dict[str, str]] = []
    for candidate in resolve_graph_credential_candidates(args):
        trial_client = GraphClient(
            tenant_id=tenant_id,
            client_id=candidate["client_id"],
            client_secret=candidate["client_secret"],
            mailbox_upn=mailbox_upn,
            max_retries=max(0, int(args.max_retries)),
            retry_base_seconds=max(0.1, float(args.retry_base_seconds)),
        )
        try:
            payload_rows = []
            for folder_name in split_mail_folders(args.folder):
                payload_rows.extend(
                    fetch_folder_messages(trial_client, folder_name, args.top, since_utc=since_utc)
                )
            client = trial_client
            credential_slot = candidate["slot"]
            break
        except GraphError as exc:
            credential_errors.append(
                {
                    "slot": candidate["slot"],
                    "status": str(exc.status or 0),
                    "error": str(exc),
                }
            )

    if client is None:
        if credential_errors:
            joined = "; ".join(
                f"{row['slot']}[{row['status']}]: {row['error']}" for row in credential_errors
            )
            raise SystemExit(f"Unable to read mailbox with any credential slot: {joined}")
        raise SystemExit(
            "Missing required values: provide --client-id/--client-secret or set GRAPH_MAIL_* / GRAPH_OBSERVER_* env vars."
        )

    rows: List[Dict[str, Any]] = []
    category_counts: Dict[str, int] = {}
    score_band_counts: Dict[str, int] = {}
    urgency_bucket_counts: Dict[str, int] = {}
    matched = 0
    unmatched = 0
    same_day_candidates = 0
    newest_seen: Optional[dt.datetime] = None
    previous_statuses = load_client_status_state(client_status_state_path)
    status_map: Dict[str, Dict[str, Any]] = {key: dict(value) for key, value in previous_statuses.items()}
    changed_fields_by_client: Dict[str, set[str]] = {}
    touched_name_keys: set[str] = set()

    candidate_messages: List[Tuple[dt.datetime, Dict[str, Any]]] = []
    for msg in payload_rows:
        received_raw = str(msg.get("receivedDateTime", ""))
        received_dt = parse_graph_dt(received_raw)
        if not received_dt:
            continue
        if received_dt <= since_utc:
            continue
        if until_utc and received_dt > until_utc:
            continue
        candidate_messages.append((received_dt, msg))

    candidate_messages.sort(key=lambda item: item[0])

    for received_dt, msg in candidate_messages:
        if newest_seen is None or received_dt > newest_seen:
            newest_seen = received_dt

        from_obj = (msg.get("from", {}) or {}).get("emailAddress", {}) or {}
        from_text = f"{from_obj.get('name', '').strip()} <{from_obj.get('address', '').strip()}>".strip()
        to_text = recipients_to_text(msg.get("toRecipients", []) or [])
        cc_text = recipients_to_text(msg.get("ccRecipients", []) or [])
        bcc_text = recipients_to_text(msg.get("bccRecipients", []) or [])
        body_text = str((msg.get("body", {}) or {}).get("content", "") or "")
        snippet = f"{msg.get('subject', '')}\n{msg.get('bodyPreview', '')}\n{body_text}"

        meta = {
            "subject": str(msg.get("subject", "")),
            "from": from_text,
            "to": to_text,
            "cc": cc_text,
            "bcc": bcc_text,
            "body": snippet[:8000],
        }
        source_folder = str(msg.get("_source_folder", "") or "")
        category = infer_category(meta)
        category_counts[category] = category_counts.get(category, 0) + 1

        matched_client = match_client_from_sql(repo_root, meta, snippet[:5000])

        destination = ""
        if matched_client:
            matched += 1
            if matched_client.live_matter_folder:
                subfolder = "Court Correspondence" if category == "Court" else "Correspondence"
                destination = f"{matched_client.live_matter_folder.rstrip('/')}/{subfolder}"
        else:
            unmatched += 1

        mailbox_pos = mailbox_position(mailbox_upn, to_text, cc_text, bcc_text)
        score_info = score_startup_email(
            subject=meta["subject"],
            body=snippet[:5000],
            category=category,
            received_dt=received_dt,
            has_attachments=bool(msg.get("hasAttachments")),
            importance=str(msg.get("importance", "") or ""),
            mailbox_position=mailbox_pos,
            matched_client=bool(matched_client),
            source_folder=source_folder,
            from_text=from_text,
        )
        score_band = str(score_info.get("score_band", "Low"))
        predicted_urgency = str(score_info.get("predicted_urgency", "routine"))
        score_band_counts[score_band] = score_band_counts.get(score_band, 0) + 1
        urgency_bucket_counts[predicted_urgency] = urgency_bucket_counts.get(predicted_urgency, 0) + 1
        if bool(score_info.get("requires_same_day_action")):
            same_day_candidates += 1

        if matched_client:
            name_key = normalise_client_key(matched_client.name)
            status = status_map.get(name_key, default_client_status(matched_client.name, name_key))
            changed_fields = changed_fields_by_client.setdefault(name_key, set())
            status["client"] = matched_client.name
            status["name_key"] = name_key
            status["last_email_received_utc"] = iso_utc(received_dt)
            status["last_email_subject"] = meta["subject"]
            status["last_email_category"] = category
            status["last_email_folder"] = source_folder
            touched_name_keys.add(name_key)

            text_lower = snippet.lower()
            update_status_field(status, "order_status", detect_order_status(text_lower, source_folder), received_dt, changed_fields)
            update_status_field(
                status,
                "sealed_order_status",
                detect_sealed_order_status(text_lower, category, bool(msg.get("hasAttachments"))),
                received_dt,
                changed_fields,
            )
            update_status_field(status, "service_status", detect_service_status(text_lower, source_folder, category), received_dt, changed_fields)
            update_status_field(status, "next_hearing", detect_next_hearing(snippet, received_dt), received_dt, changed_fields)
            if not str(status.get("next_hearing", "")).strip():
                update_status_field(
                    status,
                    "next_hearing",
                    load_root_card_next_hearing(repo_root, matched_client.name, received_dt),
                    received_dt,
                    changed_fields,
                )
            update_counsel_tracking(
                status,
                category=category,
                folder=source_folder,
                text_lower=text_lower,
                received_dt=received_dt,
                subject=meta["subject"],
                changed_fields=changed_fields,
            )
            update_counsel_watch_tracking(
                status,
                alerts=detect_counsel_watch_alerts(
                    category=category,
                    folder=source_folder,
                    subject=meta["subject"],
                    text_lower=text_lower,
                    from_text=from_text,
                    to_text=to_text,
                    cc_text=cc_text,
                    watchlist=counsel_watchlist,
                ),
                received_dt=received_dt,
                subject=meta["subject"],
                changed_fields=changed_fields,
            )

            if is_client_chase(category, from_text, mailbox_upn, text_lower):
                status["last_client_chase_utc"] = iso_utc(received_dt)
                status["last_client_chase_subject"] = meta["subject"]
                if not status.get("status_last_changed_utc"):
                    status["status_last_changed_utc"] = iso_utc(received_dt)

            if is_client_notification_out(category, source_folder, text_lower):
                status["last_client_notification_utc"] = iso_utc(received_dt)
                status["last_client_notification_subject"] = meta["subject"]
                status["status_last_changed_utc"] = iso_utc(received_dt)
                changed_fields.add("last_client_notification_utc")
                changed_fields.add("last_client_notification_subject")

            if is_client_acknowledgement(
                category,
                source_folder,
                from_text,
                mailbox_upn,
                text_lower,
                str(status.get("last_client_notification_utc", "")).strip(),
                received_dt,
            ):
                status["last_client_ack_utc"] = iso_utc(received_dt)
                status["last_client_ack_subject"] = meta["subject"]
                status["status_last_changed_utc"] = iso_utc(received_dt)
                changed_fields.add("last_client_ack_utc")
                changed_fields.add("last_client_ack_subject")

            status_map[name_key] = status

        rows.append(
            {
                "received_utc": received_dt.isoformat().replace("+00:00", "Z"),
                "subject": meta["subject"],
                "from": from_text,
                "to": to_text,
                "cc": cc_text,
                "mailbox_position": mailbox_pos,
                "category": category,
                "client_match": matched_client.name if matched_client else "",
                "proposed_destination_folder": destination,
                "has_attachments": bool(msg.get("hasAttachments")),
                "categories_current": msg.get("categories", []),
                "importance": msg.get("importance", ""),
                "score": int(score_info.get("score", 0)),
                "score_band": score_band,
                "predicted_urgency": predicted_urgency,
                "score_reasons": score_info.get("reasons", []),
                "score_flags": score_info.get("flags", []),
                "hearing_date": score_info.get("hearing_date", ""),
                "working_days_to_hearing": score_info.get("working_days_to_hearing"),
                "requires_same_day_action": bool(score_info.get("requires_same_day_action")),
                "web_link": msg.get("webLink", ""),
                "internet_message_id": msg.get("internetMessageId", ""),
                "message_id": msg.get("id", ""),
                "source_folder": source_folder,
            }
        )

    client_statuses: List[Dict[str, Any]] = []
    status_changes: List[Dict[str, Any]] = []
    touched_clients: List[str] = []

    for name_key in sorted(touched_name_keys):
        status = status_map.get(name_key)
        if not status:
            continue
        previous = previous_statuses.get(name_key, {})
        changed_fields = changed_fields_by_client.setdefault(name_key, set())
        sanitised_status = sanitise_client_status(status)
        if str(status.get("next_hearing", "")).strip() != str(sanitised_status.get("next_hearing", "")).strip():
            changed_fields.add("next_hearing")
        if str(status.get("awaiting", "")).strip() != str(sanitised_status.get("awaiting", "")).strip():
            changed_fields.add("awaiting")
        status = sanitised_status

        derived_awaiting = derive_awaiting(status)
        if str(status.get("awaiting", "")).strip() != derived_awaiting:
            status["awaiting"] = derived_awaiting
            changed_fields.add("awaiting")
            status["status_last_changed_utc"] = status.get("last_email_received_utc", "")

        derived_live_status = compose_latest_live_status(status)
        if str(status.get("latest_live_status", "")).strip() != derived_live_status:
            status["latest_live_status"] = derived_live_status
            changed_fields.add("latest_live_status")
            status["status_last_changed_utc"] = status.get("last_email_received_utc", "")

        derived_flags = build_attention_flags(status)
        if list(previous.get("attention_flags", [])) != derived_flags:
            changed_fields.add("attention_flags")
            status["status_last_changed_utc"] = status.get("last_email_received_utc", "")
        status["attention_flags"] = derived_flags
        status_map[name_key] = status

        touched_clients.append(str(status.get("client", "")).strip())
        status_copy = dict(status)
        status_copy["changed_fields"] = sorted(changed_fields)
        if changed_fields:
            change_summary = "; ".join(
                f"{field.replace('_', ' ')} -> {status_copy.get(field, '')}" for field in sorted(changed_fields) if field != "attention_flags"
            ).strip("; ")
            if "attention_flags" in changed_fields and derived_flags:
                suffix = "attention flags -> " + "; ".join(derived_flags)
                change_summary = f"{change_summary}; {suffix}".strip("; ")
            status_copy["change_summary"] = change_summary or "Call-ready fields updated."
            status_changes.append(status_copy)
        else:
            status_copy["change_summary"] = "New email(s) recorded; no call-ready field change."
        client_statuses.append(status_copy)

    for name_key, status in list(status_map.items()):
        if name_key in touched_name_keys:
            continue
        status_map[name_key] = sanitise_client_status(status)

    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y-%m-%d-%H%M%S")
    report_json = output_dir / f"{stamp}-graph-startup-sorter-readonly.json"
    report_md = output_dir / f"{stamp}-graph-startup-sorter-readonly.md"

    report = {
        "script": "graph_startup_sorter_readonly.py",
        "run_utc": now.isoformat().replace("+00:00", "Z"),
        "mode": "read-only",
        "credential_slot": credential_slot,
        "folder": args.folder,
        "folders": split_mail_folders(args.folder),
        "top_requested": int(args.top),
        "since_utc": since_utc.isoformat().replace("+00:00", "Z"),
        "emails_considered": len(rows),
        "matched": matched,
        "unmatched": unmatched,
        "category_counts": category_counts,
        "score_band_counts": score_band_counts,
        "urgency_bucket_counts": urgency_bucket_counts,
        "same_day_candidates": same_day_candidates,
        "credential_errors": credential_errors,
        "client_status_state": str(client_status_state_path),
        "touched_clients": touched_clients,
        "client_statuses": client_statuses,
        "status_changes": status_changes,
        "rows": rows,
    }
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    try:
        report_summary = {
            "run_utc": report.get("run_utc"),
            "since_utc": report.get("since_utc"),
            "emails_considered": report.get("emails_considered"),
            "matched": report.get("matched"),
            "unmatched": report.get("unmatched"),
            "category_counts": report.get("category_counts"),
            "score_band_counts": report.get("score_band_counts"),
            "report_file": str(report_json),
        }
        record_state_snapshot("graph_startup_report", str(report_json), report_summary, observed_utc=now.isoformat().replace("+00:00", "Z"))
    except Exception:
        pass

    lines = [
        f"# Graph Startup Sorter (Read-only) - {now.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
        "## Summary",
        "",
        f"- Folders: {', '.join(split_mail_folders(args.folder))}",
        f"- Since (UTC): {report['since_utc']}",
        f"- Emails considered: {len(rows)}",
        f"- Matched to client: {matched}",
        f"- Unmatched: {unmatched}",
        f"- Same-day candidates: {same_day_candidates}",
        "",
        "## Category Counts",
        "",
    ]
    if category_counts:
        for key in sorted(category_counts):
            lines.append(f"- {key}: {category_counts[key]}")
    else:
        lines.append("- None")

    lines.extend(["", "## Score Bands", ""])
    if score_band_counts:
        for key in sorted(score_band_counts):
            lines.append(f"- {key}: {score_band_counts[key]}")
    else:
        lines.append("- None")

    lines.extend(["", "## Client-Call Flag Changes", ""])
    if status_changes:
        for row in sorted(status_changes, key=lambda item: item.get("last_email_received_utc", ""), reverse=True)[:25]:
            lines.append(
                f"- {row.get('client') or 'TBC'} | {row.get('change_summary', '')} | "
                f"Last email: {row.get('last_email_received_utc', '')} | Flags: {', '.join(row.get('attention_flags', [])) or 'none'}"
            )
    else:
        lines.append("- No client-call flag changes in this incremental window.")

    lines.extend(["", "## Sample (first 25)", ""])
    for row in rows[:25]:
        lines.append(
            f"- {row['received_utc']} | {row['score_band']} {row['score']} | {row['category']} | {row['subject']} | "
            f"Client: {row['client_match'] or '[unmatched]'} | Position: {row['mailbox_position']}"
        )
    if not rows:
        lines.append("- No emails matched the incremental window.")
    lines.append("")
    if not args.no_md_report:
        report_md.write_text("\n".join(lines), encoding="utf-8")

    if newest_seen and not args.no_write_state:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_payload = {
            "last_scan_utc": newest_seen.isoformat().replace("+00:00", "Z"),
            "updated_utc": now.isoformat().replace("+00:00", "Z"),
            "script": "graph_startup_sorter_readonly.py",
        }
        from atomic_json import atomic_write_json
        atomic_write_json(state_path, state_payload)
        try:
            record_state_snapshot("graph_startup_last_run", str(state_path), state_payload, observed_utc=state_payload["updated_utc"])
        except Exception:
            pass
        client_status_state_path.parent.mkdir(parents=True, exist_ok=True)
        client_status_payload = {
            "updated_utc": now.isoformat().replace("+00:00", "Z"),
            "script": "graph_startup_sorter_readonly.py",
            "clients": status_map,
        }
        client_status_state_path.write_text(
            json.dumps(client_status_payload, indent=2),
            encoding="utf-8",
        )
        try:
            record_state_snapshot("client_live_status", str(client_status_state_path), client_status_payload, observed_utc=client_status_payload["updated_utc"])
        except Exception:
            pass
        try:
            local_sync = sync_client_status_to_local_sqlite(status_map)
            record_state_snapshot(
                "client_live_status_local_sqlite_sync",
                os.getenv("LOCAL_SQLITE_PATH", "") or "LOCAL_SQLITE_PATH",
                local_sync,
                observed_utc=client_status_payload["updated_utc"],
            )
            report["local_sqlite_status_sync"] = local_sync
        except Exception as exc:
            report["local_sqlite_status_sync"] = {"error": str(exc)}
        try:
            report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except Exception:
            pass

    print(f"SINCE_UTC={report['since_utc']}")
    print(f"EMAILS_CONSIDERED={len(rows)}")
    print(f"MATCHED={matched}")
    print(f"UNMATCHED={unmatched}")
    print(f"CREDENTIAL_SLOT={credential_slot}")
    print(f"REPORT_JSON={report_json}")
    print(f"CLIENT_STATUS_STATE={client_status_state_path}")
    if not args.no_md_report:
        print(f"REPORT_MD={report_md}")
    if newest_seen:
        print(f"NEWEST_SEEN_UTC={newest_seen.isoformat().replace('+00:00', 'Z')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
