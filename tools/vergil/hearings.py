from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from caseforge_cli.chambers_finder import load_finder_data
from documents import court_finder as court_finder
from vergil.formatting import (
    format_hearing_time,
    parse_hearing_date,
    parse_hearing_time,
    reformat_dates,
)
from vergil.primitives import (
    REPO_ROOT,
    latest_json,
    normalise_client_key,
    normalise_space,
    prompt_lower,
    read_json,
)
import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from products.ikoro.obligation_aging import BANK_HOLIDAYS

LONDON_TZ = ZoneInfo("Europe/London")


def working_days_between(start: dt.date, end: dt.date) -> int:
    current = start + dt.timedelta(days=1)
    count = 0
    while current <= end:
        if current.weekday() < 5 and current not in BANK_HOLIDAYS:
            count += 1
        current += dt.timedelta(days=1)
    return count


def calendar_hearing_state() -> dict[str, dict]:
    payload = read_json(REPO_ROOT / "telemetry" / "startup-hearing-calendar-state.json") or {}
    clients = payload.get("clients", {}) if isinstance(payload, dict) else {}
    return clients if isinstance(clients, dict) else {}


def calendar_state_time(entry: dict) -> tuple[int, int] | None:
    hearing_key = str(entry.get("hearing_key") or "").strip()
    parts = hearing_key.split("|")
    if len(parts) >= 3:
        parsed = parse_hearing_time(parts[-1])
        if parsed:
            return parsed
    return parse_hearing_time(str(entry.get("start_local") or ""))


def latest_hearing_row(rows: list[dict], client_name: str, hearing_date: dt.date) -> dict:
    matches: list[dict] = []
    for row in rows:
        if str(row.get("client_match", "")).strip() != client_name:
            continue
        row_date = parse_hearing_date(str(row.get("hearing_date") or row.get("subject") or ""))
        if row_date != hearing_date:
            continue
        matches.append(row)
    if not matches:
        return {}

    def _sort_key(row: dict) -> tuple[int, str]:
        court_first = 0 if str(row.get("category", "")).strip().lower() == "court" else 1
        return court_first, str(row.get("received_utc", "")).strip()

    return sorted(matches, key=_sort_key)[-1]


def court_from_rows(rows: list[dict], client_name: str, hearing_date: dt.date) -> str:
    for row in rows:
        if str(row.get("client_match", "")).strip() != client_name:
            continue
        if str(row.get("category", "")).strip().lower() != "court":
            continue
        row_date = parse_hearing_date(str(row.get("hearing_date") or row.get("subject") or ""))
        if row_date and row_date != hearing_date:
            continue
        sender = sender_name(str(row.get("from") or ""))
        if sender:
            return sender
    return ""


def sender_name(sender: str) -> str:
    value = normalise_space(sender)
    if "<" in value:
        value = value.split("<", 1)[0].strip()
    return value.strip('" ')


_CHAMBERS_DOMAIN_CACHE: dict[str, str] | None = None


def chambers_name_from_sender(sender: str) -> str:
    global _CHAMBERS_DOMAIN_CACHE
    if _CHAMBERS_DOMAIN_CACHE is None:
        domains: dict[str, str] = {}
        payload = load_finder_data() or {}
        for row in payload.get("chambers", []) or []:
            if not isinstance(row, dict):
                continue
            email_addr = str(row.get("email") or "").strip().lower()
            name = str(row.get("name") or "").strip()
            if "@" in email_addr and name:
                domains[email_addr.split("@", 1)[1]] = name
        _CHAMBERS_DOMAIN_CACHE = domains
    match = re.search(r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", sender or "")
    if not match:
        return ""
    return (_CHAMBERS_DOMAIN_CACHE or {}).get(match.group(1).lower(), "")


def hearing_detail(row: dict, rows: list[dict], calendar_state: dict[str, dict]) -> dict:
    client = str(row.get("client", "Unknown")).strip() or "Unknown"
    client_key = str(row.get("name_key") or normalise_client_key(client)).strip()
    hearing_text = str(row.get("next_hearing") or row.get("next_hearing_text") or "").strip()
    hearing_date = parse_hearing_date(hearing_text)
    if hearing_date is None:
        return {}
    state_entry = calendar_state.get(client_key, {}) if isinstance(calendar_state, dict) else {}
    latest_row = latest_hearing_row(rows, client, hearing_date)
    time_value = (
        parse_hearing_time(str(latest_row.get("hearing_date") or ""))
        or parse_hearing_time(str(latest_row.get("subject") or ""))
        or parse_hearing_time(str(row.get("last_email_subject") or ""))
        or calendar_state_time(state_entry if isinstance(state_entry, dict) else {})
    )
    court = ""
    if isinstance(state_entry, dict):
        court = str(state_entry.get("location") or "").strip()
    if not court:
        court = court_from_rows(rows, client, hearing_date)
    counsel = ""
    counsel_status = str(row.get("counsel_response_status") or "").strip()
    if counsel_status:
        counsel = f"Counsel: {counsel_status}"
        sender = str(latest_row.get("from") or "")
        chambers = chambers_name_from_sender(sender)
        if chambers:
            counsel = f"{counsel} - {chambers}"
        elif sender and str(latest_row.get("category", "")).strip().lower() == "counsel":
            sender_label = sender_name(sender)
            if sender_label:
                counsel = f"{counsel} - {sender_label}"
    hearing_label = ""
    if isinstance(state_entry, dict):
        hearing_label = str(state_entry.get("hearing_label") or "").strip()
    return {
        "client": client,
        "client_key": client_key,
        "date": hearing_date,
        "time": format_hearing_time(time_value),
        "court": court,
        "counsel": counsel,
        "hearing_label": hearing_label,
        "awaiting": str(row.get("awaiting") or "").strip(),
        "row": row,
    }


def hearing_badge_counts(hearing_details: list[dict], today: dt.date) -> dict[str, int]:
    counts = {"same_day": 0, "high": 0, "normal": 0, "low": 0}
    for detail in hearing_details:
        hearing_date = detail.get("date")
        if not isinstance(hearing_date, dt.date) or hearing_date < today:
            continue
        if hearing_date == today:
            counts["same_day"] += 1
            continue
        working_days = working_days_between(today, hearing_date)
        if working_days <= 3:
            counts["high"] += 1
        elif working_days <= 7:
            counts["normal"] += 1
        elif working_days <= 14:
            counts["low"] += 1
    return counts


def redundant_awaiting(awaiting: str, hearing_date: dt.date) -> bool:
    text = prompt_lower(awaiting)
    if not text:
        return True
    date_tokens = {
        hearing_date.strftime("%d.%m.%Y").lower(),
        hearing_date.strftime("%d/%m/%Y").lower(),
        hearing_date.strftime("%-d %B %Y").lower(),
    }
    return text.startswith("hearing on") and any(token in text for token in date_tokens)


def active_case_status(row: dict) -> str:
    status = reformat_dates(str(row.get("latest_live_status") or "").strip())
    if status:
        return status
    changed = [str(item).strip() for item in row.get("changed_fields", []) or [] if str(item).strip()]
    change_summary = str(row.get("change_summary") or "").strip()
    if changed and change_summary:
        return reformat_dates(change_summary)
    counsel_status = str(row.get("counsel_response_status") or "").strip()
    if counsel_status:
        return f"Counsel: {counsel_status}"
    return ""


def court_contact_card_for_obligation(ob: dict) -> str | None:
    ref = str(ob.get("matter_ref") or "").strip()
    query = str(ob.get("client") or ref).strip()
    if not query:
        return None
    try:
        postcode_result = court_finder.resolve_client_applicant_postcode(query)
        if not postcode_result.get("ok"):
            return None
        if postcode_result.get("was_fuzzy_resolved"):
            return None
        postcode = court_finder.normalise_postcode(str(postcode_result.get("postcode") or ""))
        if not postcode:
            return None
        result = court_finder.find_nearest_courts(
            postcode,
            court_finder.service_slug_for_label(court_finder.DEFAULT_SERVICE_LABEL),
            detail_limit=court_finder.TOP_COURT_COUNT,
        )
        if not result.get("ok"):
            return None
        return court_finder.build_court_contact_card(result, ref)
    except Exception:
        return None


def calendar_finder_result_rows(result: object) -> list[dict]:
    if not isinstance(result, dict):
        return []
    rows: list[dict] = []
    if isinstance(result.get("result"), dict):
        rows.append(result["result"])
    for item in result.get("results") or []:
        if isinstance(item, dict):
            rows.append(item)
    nested = result.get("result") if isinstance(result.get("result"), dict) else {}
    if isinstance(nested, dict):
        for item in nested.get("results") or []:
            if isinstance(item, dict):
                rows.append(item)
        if isinstance(nested.get("result"), dict):
            rows.append(nested["result"])
    return rows


def build_hearing_tool_response(prompt: str) -> str | None:
    scorecard_path, scorecard = latest_json("startup-scorecards/scorecard-*.json")
    graph_path, graph = latest_json("graph-startup/*-readonly.json")
    if not scorecard and not graph:
        return None

    lines = ["Latest hearing watch from startup:"]
    if scorecard_path:
        run_utc = str((scorecard or {}).get("run_utc", "")).strip()
        if run_utc:
            lines.append(f"Startup run: {run_utc}")

    statuses = list((graph or {}).get("client_statuses", []) or [])
    graph_rows = [row for row in (graph or {}).get("rows", []) or [] if isinstance(row, dict)]
    calendar_state = calendar_hearing_state()
    dated: list[dict] = []
    for row in statuses:
        if not isinstance(row, dict):
            continue
        detail = hearing_detail(row, graph_rows, calendar_state)
        if detail:
            dated.append(detail)
    dated.sort(key=lambda item: item["date"])

    today_date = dt.datetime.now(LONDON_TZ).date()
    tranches = hearing_badge_counts(dated, today_date)
    lines.append(
        "Tranches: "
        f"same-day {tranches.get('same_day', 0)}, "
        f"high {tranches.get('high', 0)}, "
        f"normal {tranches.get('normal', 0)}, "
        f"low {tranches.get('low', 0)}."
    )

    if dated:
        lines.append("")
        lines.append("Next listed hearings:")
        for detail in dated[:6]:
            bits = [detail["date"].strftime("%A %d %B %Y")]
            if detail.get("time"):
                bits.append(str(detail["time"]))
            if detail.get("court"):
                bits.append(str(detail["court"]))
            if detail.get("counsel"):
                bits.append(str(detail["counsel"]))
            awaiting = str(detail.get("awaiting", "")).strip()
            if awaiting and not redundant_awaiting(awaiting, detail["date"]):
                bits.append(f"Awaiting: {awaiting}")
            lines.append(f"- {detail['client']}: {' | '.join(bits)}")
    elif graph_path:
        lines.append("")
        lines.append(f"No dated hearings were parsed from {graph_path.name}.")

    return "\n".join(lines).strip()
