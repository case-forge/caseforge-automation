from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Mapping

import child_age
import matter_orders
import order_codes
from field_shapes import known_value
from documents.order_text_case import normalise_order_text
from agwu import client_rows
from vergil.formatting import format_an_fast_date
from vergil.primitives import (
    REPO_ROOT,
    latest_json,
    normalise_space,
    prompt_lower,
    read_json,
)
from vergil.sql_cooldown import sql_cooldown_fail_count, sql_cooldown_until

CLIENT_EXPOSURE_REFUSAL = "CaseForge Chat cannot show that many client records in this window. Ask for one scoped matter or a non-identifying summary."
CLIENT_DB_SEARCH_FAILED = "Client DB search failed. Try again shortly."


def _log_search_failure(where: str, exc: BaseException) -> None:
    print(f"[client_search] {where} failed: {type(exc).__name__}: {exc}", file=sys.stderr)


def client_search_query(prompt: str) -> str:
    text = normalise_space(prompt)
    lowered = text.lower()
    prefixes = (
        "client search:",
        "search client:",
        "find client",
        "find a client",
        "look up client",
        "lookup client",
        "lookup:",
        "lookup ",
        "who is",
        "whose",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix):].strip(" :-")
    return text.strip()

def client_lookup_prefixes() -> tuple[str, ...]:
    return (
        "client search:",
        "search client:",
        "find client",
        "find a client",
        "look up client",
        "lookup client",
        "lookup:",
        "lookup ",
        "who is",
        "whose",
    )

COURT_REFERENCE_QUERY_RE = re.compile(r"\b[A-Z]{1,3}\s*\d{2}\s*[A-Z]\s*\d{5}\b", re.IGNORECASE)

PARTY_V_CACHE_RE = re.compile(
    r"\b([A-Z][A-Z' -]{1,60}?)\s*-?\s*V(?:S|ERSUS)?\.?\s*-?\s*([A-Z][A-Z' -]{1,60}?)\b",
    re.IGNORECASE,
)

def court_reference_from_query(query: str) -> str:
    match = COURT_REFERENCE_QUERY_RE.search(str(query or ""))
    if not match:
        return ""
    return re.sub(r"\s+", "", match.group(0)).upper()

def compact_reference_text(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())

def cache_text_matches_query(query: str, *values: object) -> bool:
    ref = court_reference_from_query(query)
    haystack = " ".join(str(value or "") for value in values)
    if ref:
        return ref in compact_reference_text(haystack)
    q_lower = normalise_space(query).lower()
    return len(q_lower) >= 3 and q_lower in normalise_space(haystack).lower()

def client_name_from_cache_key(value: object) -> str:
    text = normalise_space(str(value or "").replace("_", " "))
    if not text:
        return ""
    return text if any(char.isupper() for char in text) else text.title()

def party_lookup_terms_from_text(value: object) -> list[str]:
    text = normalise_space(str(value or ""))
    terms: list[str] = []
    for match in PARTY_V_CACHE_RE.finditer(text):
        for side in (match.group(1), match.group(2)):
            cleaned = re.sub(r"[^A-Za-z' -]+", " ", side)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in {"applicant", "respondent", "court", "family", "case"}:
                continue
            terms.append(cleaned.title() if cleaned.isupper() else cleaned)
    return list(dict.fromkeys(terms))

def client_cache_terms_from_calendar_state(query: str, payload: dict) -> list[dict]:
    clients = payload.get("clients", {}) if isinstance(payload, dict) else {}
    if not isinstance(clients, dict):
        return []
    ref = court_reference_from_query(query)
    hits: list[dict] = []
    for key, entry in clients.items():
        if not isinstance(entry, dict):
            continue
        entry_text = json.dumps(entry, ensure_ascii=False, default=str)
        if not cache_text_matches_query(query, key, entry_text):
            continue
        client_name = client_name_from_cache_key(entry.get("client") or key)
        note_bits = ["startup hearing calendar"]
        case_ref = str(entry.get("case_ref") or ref or "").strip()
        if case_ref:
            note_bits.append(case_ref)
        subject = normalise_space(str(entry.get("subject") or ""))
        if subject:
            note_bits.append(subject)
        if client_name:
            hits.append({"term": client_name, "note": " | ".join(note_bits)})
        for term in party_lookup_terms_from_text(subject):
            hits.append({"term": term, "note": " | ".join(note_bits)})
    return hits

def client_cache_terms_from_graph_payload(query: str, payload: dict, source_name: str) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    hits: list[dict] = []
    rows: list[dict] = []
    for collection_name in ("rows", "client_statuses"):
        rows.extend(row for row in payload.get(collection_name, []) or [] if isinstance(row, dict))
    for row in rows:
        relevant_values = [
            row.get("client_match"),
            row.get("client"),
            row.get("subject"),
            row.get("last_email_subject"),
            row.get("hearing_date"),
            row.get("next_hearing"),
            row.get("next_hearing_text"),
            row.get("case_ref"),
        ]
        if not cache_text_matches_query(query, *relevant_values):
            continue
        subject = normalise_space(str(row.get("subject") or row.get("last_email_subject") or ""))
        source = normalise_space(source_name)
        if subject:
            source = f"{source} | {subject}" if source else subject
        for field in ("client_match", "client"):
            client_name = normalise_space(str(row.get(field) or ""))
            if client_name:
                hits.append({"term": client_name, "note": source})
        for term in party_lookup_terms_from_text(subject):
            hits.append({"term": term, "note": source})
    return hits

def client_cache_lookup_terms(query: str, limit: int = 12) -> list[dict]:
    hits: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add_many(items: list[dict]) -> None:
        for item in items:
            term = normalise_space(str(item.get("term") or ""))
            note = normalise_space(str(item.get("note") or ""))
            if len(term) < 2:
                continue
            key = (term.lower(), note.lower())
            if key in seen:
                continue
            seen.add(key)
            hits.append({"term": term, "note": note})

    calendar_state = read_json(REPO_ROOT / "telemetry" / "startup-hearing-calendar-state.json") or {}
    add_many(client_cache_terms_from_calendar_state(query, calendar_state))

    latest_graph_path, latest_graph = latest_json("graph-startup/*-readonly.json")
    if latest_graph_path and latest_graph:
        add_many(client_cache_terms_from_graph_payload(query, latest_graph, latest_graph_path.name))

    if court_reference_from_query(query):
        graph_files = sorted((REPO_ROOT / "telemetry" / "graph-startup").glob("*-readonly.json"))
        for path in reversed(graph_files[-25:]):
            if latest_graph_path and path == latest_graph_path:
                continue
            payload = read_json(path) or {}
            add_many(client_cache_terms_from_graph_payload(query, payload, path.name))
            if len(hits) >= limit:
                break

    return hits[:limit]

def search_clients_from_cache(query: str, search_clients_func, limit: int) -> tuple[list[dict], str]:
    rows: list[dict] = []
    seen_matter_ids: set[str] = set()
    matched_labels: list[str] = []
    for hit in client_cache_lookup_terms(query):
        term = str(hit.get("term") or "").strip()
        note = str(hit.get("note") or "").strip()
        if not term:
            continue
        try:
            candidates = search_clients_func(term, limit=4)
        except Exception:
            candidates = []
        matter_ids = {
            str(row.get("matter_id") or "").strip()
            for row in candidates
            if str(row.get("matter_id") or "").strip()
        }
        if len(matter_ids) != 1:
            continue
        for candidate in candidates:
            matter_key = str(candidate.get("matter_id") or candidate.get("client_name") or "")
            if matter_key in seen_matter_ids:
                continue
            seen_matter_ids.add(matter_key)
            row = dict(candidate)
            row["_search_match_note"] = f"{court_reference_from_query(query) or query} matched in {note}".strip()
            rows.append(row)
            label = str(row.get("client_name") or row.get("matter_name") or term).strip()
            if label:
                matched_labels.append(label)
            if len(rows) >= limit:
                return rows, f"{query} -> {', '.join(dict.fromkeys(matched_labels))} (startup cache)"
    if rows:
        return rows, f"{query} -> {', '.join(dict.fromkeys(matched_labels))} (startup cache)"
    return [], query

def graph_client_search_from_cache(query: str) -> str:
    try:
        lookup_terms = client_cache_lookup_terms(query, limit=8)
        if lookup_terms:
            lines = [f"Startup cache matches for '{query}':"]
            for item in lookup_terms[:5]:
                term = str(item.get("term") or "").strip()
                note = str(item.get("note") or "").strip()
                lines.append(f"- {term}" + (f" ({note})" if note else ""))
            return "\n".join(lines)

        _, graph = latest_json("graph-startup/*-readonly.json")
        if not graph:
            return ""
        q_lower = normalise_space(query).lower()
        matches: list[dict] = []
        for row in (graph.get("rows") or []):
            match_name = str(row.get("client_match") or "").strip()
            subject = str(row.get("subject") or "").strip()
            if not match_name and not subject:
                continue
            combined = f"{match_name} {subject}".lower()
            if any(part in combined for part in q_lower.split() if len(part) >= 3):
                matches.append(row)
        if not matches:
            return ""
        lines = [f"Graph startup cache matches for '{query}':"]
        for row in matches[:5]:
            match_name = str(row.get("client_match") or "").strip()
            subject = str(row.get("subject") or "").strip()[:60]
            category = str(row.get("category") or "").strip()
            received = str(row.get("received_utc") or "").strip()[:10]
            label = match_name or subject
            detail_parts = [p for p in [category, received] if p]
            lines.append(f"- {label}" + (f" ({', '.join(detail_parts)})" if detail_parts else ""))
        return "\n".join(lines)
    except Exception:
        return ""

def compact_lookup_value(value: object, limit: int = 180) -> str:
    text = normalise_space(known_value(value))
    if not text or text.lower() in {"none", "null", "n/a", "na", "unknown"}:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."

def format_client_lookup_date(value: object) -> str:
    if isinstance(value, dt.datetime):
        return value.date().strftime("%d-%m-%Y")
    if isinstance(value, dt.date):
        return value.strftime("%d-%m-%Y")
    text = compact_lookup_value(value, limit=40)
    if not text:
        return ""
    candidate = text.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(candidate).date().strftime("%d-%m-%Y")
    except ValueError:
        pass
    try:
        return dt.date.fromisoformat(text[:10]).strftime("%d-%m-%Y")
    except ValueError:
        return text

def client_lookup_referral_source(row: dict) -> str:
    return compact_lookup_value(row.get("intake_source")) or compact_lookup_value(row.get("referral_source"))

def client_lookup_referral_date(row: dict) -> str:
    return format_client_lookup_date(row.get("referral_sent_at")) or format_client_lookup_date(row.get("source_email_sent_at"))

def client_lookup_address_display(row: dict) -> str:
    address = compact_lookup_value(row.get("address_summary"), limit=240)
    if row.get("has_c8") and address:
        return f"{address} (C8 flagged; check withheld fields before respondent-facing use)"
    if row.get("has_c8"):
        return "C8 flagged; no address recorded"
    return address

def client_lookup_intro_lines(row: dict) -> list[str]:
    lines: list[str] = []
    source = client_lookup_referral_source(row)
    referral_date = client_lookup_referral_date(row)
    intro_bits: list[str] = []
    if source:
        intro_bits.append(source)
    if referral_date:
        intro_bits.append(f"sent {referral_date}")
    if intro_bits:
        lines.append(f"Referral: {' | '.join(intro_bits)}")

    relationship_start = compact_lookup_value(row.get("relationship_start"), limit=80)
    relationship_end = compact_lookup_value(row.get("relationship_end"), limit=80)
    relationship_bits = []
    if relationship_start:
        relationship_bits.append(f"start {relationship_start}")
    if relationship_end:
        relationship_bits.append(f"end {relationship_end}")
    if relationship_bits:
        lines.append(f"Relationship: {' | '.join(relationship_bits)}")
    elif intro_bits:
        lines.append("Relationship: not recorded")
    for label, field in (
        ("Lived together", "lived_together"),
        ("Married or civil partnership", "married"),
        ("Bail conditions", "bail_conditions"),
        ("Bail conditions end", "bail_end_date"),
        ("Police crime reference(s)", "crime_refs"),
    ):
        detail = compact_lookup_value(row.get(field), limit=120)
        if detail:
            lines.append(f"{label}: {detail}")

    for label, field in (
        ("Benefits", "benefits_canonical"),
        ("Property", "property_summary"),
        ("Withheld fields", "withheld_fields"),
    ):
        detail = compact_lookup_value(row.get(field))
        if detail:
            lines.append(f"{label}: {detail}")
    return lines

def client_lookup_field_grid(fields: list[tuple[str, str]]) -> str:
    visible = [(label, compact_lookup_value(value, limit=240)) for label, value in fields]
    visible = [(label, value) for label, value in visible if value]
    if not visible:
        return ""
    cards = []
    for label, value in visible:
        cards.append(
            "<div class='client-lookup-field'>"
            f"<span class='client-lookup-label'>{html.escape(label)}</span>"
            f"<span class='client-lookup-value'>{html.escape(value)}</span>"
            "</div>"
        )
    return "<div class='client-lookup-grid'>" + "".join(cards) + "</div>"

def client_lookup_core_fields(row: dict) -> list[tuple[str, str]]:
    orders = client_order_display(row)
    refs = str(row.get("reference_summary") or row.get("case_reference") or "").strip()
    ref = str(row.get("company_reference") or "").strip()
    party_summary = str(row.get("matched_party_summary") or row.get("party_summary") or "").strip()
    address = client_lookup_address_display(row)
    return [
        ("CaseForge ref", ref),
        ("Orders", orders),
        ("DOB", format_client_lookup_date(row.get("dob_iso"))),
        ("Phone", str(row.get("phone_primary") or "").strip()),
        ("Email", str(row.get("email_primary") or "").strip()),
        ("Client role", str(row.get("client_role") or "").strip()),
        ("Parties", party_summary),
        ("Children", child_age.with_live_ages(str(row.get("children_summary") or "").strip())),
        ("Address", address),
        ("References", "" if refs == ref else refs),
        ("Matched search", str(row.get("_search_match_note") or "").strip()),
        ("Live folder", str(row.get("live_matter_folder") or "").strip()),
        ("Status", str(row.get("latest_live_status") or "").strip()),
        ("Next hearing", str(row.get("next_hearing_text") or "").strip()),
        ("Awaiting", str(row.get("awaiting_next_step") or "").strip()),
    ]

def client_lookup_intro_fields(row: dict) -> list[tuple[str, str]]:
    relationship_start = compact_lookup_value(row.get("relationship_start"), limit=80) or "Not recorded"
    relationship_end = compact_lookup_value(row.get("relationship_end"), limit=80) or "Not recorded"
    return [
        ("Source", client_lookup_referral_source(row)),
        ("Referral date", client_lookup_referral_date(row)),
        ("Relationship start", relationship_start),
        ("Relationship end", relationship_end),
        ("Benefits", str(row.get("benefits_canonical") or "").strip()),
        ("Property", str(row.get("property_summary") or "").strip()),
        ("Withheld fields", str(row.get("withheld_fields") or "").strip()),
    ]

def client_lookup_title(row: dict) -> str:
    client = str(row.get("client_name") or row.get("matter_name") or "Unknown").strip()
    matter = str(row.get("matter_name") or "").strip()
    return matter if matter and matter != client else client

def client_lookup_subtitle(row: dict) -> str:
    client = str(row.get("client_name") or "").strip()
    matter = str(row.get("matter_name") or "").strip()
    if client and matter and client != matter:
        return client
    return ""

def client_lookup_button_key(row: dict, index: int, prefix: str) -> str:
    raw = str(row.get("matter_id") or row.get("company_reference") or row.get("client_name") or index)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")[:60] or str(index)
    return f"{prefix}_{index}_{safe}"

def client_lookup_envelope_query(row: dict) -> str:
    return (
        str(row.get("company_reference") or "").strip()
        or str(row.get("client_name") or "").strip()
        or str(row.get("matter_name") or "").strip()
    )

def format_client_search_response(display_query: str, rows: list[dict]) -> str:
    lines = [f"Client DB search: {display_query}"]
    for row in rows:
        client = str(row.get("client_name") or row.get("matter_name") or "Unknown").strip()
        matter = str(row.get("matter_name") or "").strip()
        ref = str(row.get("company_reference") or "").strip()
        dob = format_client_lookup_date(row.get("dob_iso"))
        phone = str(row.get("phone_primary") or "").strip()
        email_addr = str(row.get("email_primary") or "").strip()
        orders = client_order_display(row)
        role = str(row.get("client_role") or "").strip()
        refs = str(row.get("reference_summary") or row.get("case_reference") or "").strip()
        live_folder = str(row.get("live_matter_folder") or "").strip()
        party_summary = str(row.get("party_summary") or "").strip()
        matched_party_summary = str(row.get("matched_party_summary") or "").strip()
        children = child_age.with_live_ages(str(row.get("children_summary") or "").strip())
        address = client_lookup_address_display(row)
        latest = str(row.get("latest_live_status") or "").strip()
        hearing = str(row.get("next_hearing_text") or "").strip()
        awaiting = str(row.get("awaiting_next_step") or "").strip()
        flags = []
        if row.get("has_c8"):
            flags.append("C8")
        title = matter if matter and matter != client else client
        if flags:
            title = f"{title} [{' '.join(flags)}]"
        lines.append(f"- {title}")
        details = []
        if ref:
            details.append(f"ref {ref}")
        if orders:
            details.append(orders)
        if dob:
            details.append(f"DOB {dob}")
        if phone:
            details.append(phone)
        if email_addr:
            details.append(email_addr)
        if details:
            lines.append(f"  {' | '.join(details)}")
        if role:
            lines.append(f"  Role: {role}")
        if matched_party_summary:
            lines.append(f"  Matched party: {matched_party_summary}")
        elif party_summary:
            lines.append(f"  Parties: {party_summary}")
        if children:
            lines.append(f"  Children: {children}")
        if address:
            lines.append(f"  Address: {address}")
        for intro_line in client_lookup_intro_lines(row):
            lines.append(f"  {intro_line}")
        if refs and refs != ref:
            lines.append(f"  References: {refs}")
        match_note = str(row.get("_search_match_note") or "").strip()
        if match_note:
            lines.append(f"  Matched search: {match_note}")
        if live_folder:
            lines.append(f"  Live folder: {live_folder}")
        if latest:
            lines.append(f"  Status: {latest}")
        if hearing:
            lines.append(f"  Next hearing: {hearing}")
        if awaiting:
            lines.append(f"  Awaiting: {awaiting}")
    return "\n".join(lines)

def client_order_display(row: dict, *, codes_from_text: bool = True) -> str:
    resolved = matter_orders.resolve_row(row)
    if resolved.structured:
        return "; ".join(resolved.codes)
    raw = str(row.get("order_requested_text") or "").strip()
    return normalise_client_order_display(raw) if codes_from_text else normalise_order_text(raw)

def normalise_client_order_display(raw: str) -> str:
    text = normalise_space(raw)
    if not text:
        return ""
    codes = list(order_codes.resolve_order_text(text).codes)
    if codes:
        return "; ".join(codes)
    return normalise_order_text(text)

def client_candidate_label(row: dict) -> str:
    name = str(row.get("client_name") or row.get("matter_name") or "Unknown").strip()
    dob = format_client_lookup_date(row.get("dob_iso"))
    orders = client_order_display(row)
    bits = [bit for bit in [orders, f"DOB {dob}" if dob else ""] if bit]
    return f"{name} ({' | '.join(bits)})" if bits else name

def looks_like_basic_client_search(prompt: str) -> bool:
    text = prompt_lower(prompt)
    return any(text.startswith(prefix) for prefix in client_lookup_prefixes())

def strip_client_search_messages(messages: list[dict]) -> tuple[list[dict], int]:
    from vergil.prompt_routing import is_client_search_assistant_message

    kept: list[dict] = []
    removed = 0
    idx = 0
    while idx < len(messages):
        msg = messages[idx]
        if isinstance(msg, dict) and msg.get("role") == "user" and looks_like_basic_client_search(str(msg.get("content", ""))):
            removed += 1
            if idx + 1 < len(messages) and isinstance(messages[idx + 1], dict) and is_client_search_assistant_message(messages[idx + 1]):
                removed += 1
                idx += 2
            else:
                idx += 1
            continue
        if isinstance(msg, dict) and msg.get("role") == "assistant" and is_client_search_assistant_message(msg):
            removed += 1
            idx += 1
            continue
        kept.append(msg)
        idx += 1
    return kept, removed

def client_search_message_count(messages: list[dict]) -> int:
    _kept, removed = strip_client_search_messages(messages)
    return removed

def legal_aid_queue_limit() -> int:
    try:
        return max(1, min(int(getattr(client_rows, "MAX_CLIENTS_PER_REQUEST", 10) or 10), 10))
    except Exception:
        return 10

def casework_queue_limit() -> int:
    try:
        return max(1, min(int(getattr(client_rows, "MAX_CLIENTS_PER_REQUEST", 10) or 10), 10))
    except Exception:
        return 10

def client_care_letter_queue_limit() -> int:
    return 10

def combined_folder_plan_hash(plan_result: Mapping[str, object]) -> str:
    plans = [plan for plan in plan_result.get("plans", []) if isinstance(plan, Mapping)]
    payload = {"plans": plans}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]

def recent_client_breakdown(item: Mapping | dict) -> str:
    bits = [
        format_an_fast_date(str(item.get("created_utc") or "")),
        str(item.get("orders") or "").strip(),
        str(item.get("referral_source") or "").strip(),
    ]
    return " | ".join(bit for bit in bits if bit)

def client_care_letter_breakdown(item: Mapping | dict) -> str:
    bits = [
        format_an_fast_date(str(item.get("created_utc") or "")),
        str(item.get("orders") or "").strip(),
        str(item.get("referral_source") or "").strip(),
        str(item.get("ccl_status_label") or "").strip(),
    ]
    return " | ".join(bit for bit in bits if bit)


def client_care_letter_stale_days() -> int:
    default = 7
    try:
        import os

        tools_dir = str(Path(__file__).resolve().parent.parent)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from documents.ccl_status import DEFAULT_STALE_DAYS

        default = int(DEFAULT_STALE_DAYS)
        raw = str(os.getenv("CASEFORGE_CCL_TODO_STALE_DAYS", "") or "").strip()
        return max(0, int(raw)) if raw else default
    except Exception:
        return default


_CCL_TIMESTAMP_FORMATS = (
    "%b %d %Y %I:%M%p",
    "%b %d %Y %I:%M %p",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def parse_client_care_letter_timestamp(value: str) -> dt.datetime | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    parsed: dt.datetime | None = None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in _CCL_TIMESTAMP_FORMATS:
            try:
                parsed = dt.datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    return parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed


def client_care_letter_is_stale(item: Mapping | dict, *, now: dt.datetime | None = None) -> bool:
    if str(item.get("ccl_status") or "") != "candidate":
        return False
    days = client_care_letter_stale_days()
    if days <= 0:
        return False
    created = parse_client_care_letter_timestamp(str(item.get("created_utc") or ""))
    if created is None:
        return False
    current = now or dt.datetime.now(dt.timezone.utc)
    return created <= current - dt.timedelta(days=days)


def split_client_care_letter_rows(
    rows, *, now: dt.datetime | None = None
) -> tuple[list[dict], list[dict]]:
    fresh: list[dict] = []
    stale: list[dict] = []
    for item in rows or []:
        if not isinstance(item, Mapping):
            continue
        (stale if client_care_letter_is_stale(item, now=now) else fresh).append(dict(item))
    return fresh, stale

def build_client_search_response(prompt: str, username: str | None) -> str:
    from vergil.prompt_routing import is_sql_available
    from vergil.user_state import enforce_client_exposure_budget, is_guest

    if is_guest(username):
        return "Ask a supervisor."
    query = client_search_query(prompt)
    if len(query) < 2 or query.startswith("["):
        return "Enter a client name, phone number, email address, or case/reference number."

    if not is_sql_available():
        until = sql_cooldown_until()
        header = f"Client DB is unavailable (database cooldown until {until} — {sql_cooldown_fail_count()} failure(s))." if until else "Client DB is unavailable."
        cache_text = graph_client_search_from_cache(query)
        fallback = f"\n\n{cache_text}" if cache_text else "\n\nNo cached matches found."
        return (
            f"{header} Searching startup cache instead.{fallback}\n\n"
            f"For a full live search, ask the AI assistant directly — it can search emails and live files while the client DB is unavailable."
        )

    try:
        import agwu

        _result = agwu.resolve_client(query, limit=10, caller="client_search.build_client_search_response")
        rows, display_query = [m.row for m in _result.matches], _result.display_query
    except Exception as exc:
        _log_search_failure("build_client_search_response", exc)
        return CLIENT_DB_SEARCH_FAILED
    if not rows:
        return f"No local client DB match found for: {query}"
    exposure = enforce_client_exposure_budget(str(username or ""), rows, source="client_search_response")
    if exposure.get("block"):
        return CLIENT_EXPOSURE_REFUSAL

    return format_client_search_response(display_query, rows[:6])

def build_client_search_panel(query_text: str, username: str) -> dict:
    from vergil.prompt_routing import is_sql_available
    from vergil.user_state import enforce_client_exposure_budget, is_guest

    query = client_search_query(query_text)
    candidate_rows: list[dict] = []
    response = ""
    searched = False
    if is_guest(username) or len(query) < 2 or query.startswith("[") or not is_sql_available():
        response = build_client_search_response(f"Client search: {query}", username)
    else:
        try:
            import agwu

            _result = agwu.resolve_client(query, limit=10, caller="client_search.build_client_search_panel")
            candidate_rows, display_query = [m.row for m in _result.matches], _result.display_query
            searched = True
        except Exception as exc:
            _log_search_failure("build_client_search_panel", exc)
            response = CLIENT_DB_SEARCH_FAILED
        else:
            exposure = enforce_client_exposure_budget(username, candidate_rows, source="client_search_panel")
            if exposure.get("block"):
                response = CLIENT_EXPOSURE_REFUSAL
                candidate_rows = []
            else:
                response = (
                    format_client_search_response(display_query, candidate_rows[:6])
                    if candidate_rows
                    else f"No local client DB match found for: {query}"
                )
    try:
        if not searched and not is_guest(username) and len(query) >= 2 and not query.startswith("[") and is_sql_available():
            import agwu

            _result = agwu.resolve_client(query, limit=10, caller="client_search.build_client_search_panel")
            candidate_rows, _candidate_display_query = [m.row for m in _result.matches], _result.display_query
            exposure = enforce_client_exposure_budget(username, candidate_rows, source="client_search_panel_candidates")
            if exposure.get("block"):
                candidate_rows = []
    except Exception:
        candidate_rows = []
    candidates = [
        {
            "label": client_candidate_label(row),
            "name": str(row.get("client_name") or row.get("matter_name") or "").strip(),
        }
        for row in candidate_rows
    ]
    return {
        "query": query,
        "response": response,
        "rows": candidate_rows,
        "candidates": candidates,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
