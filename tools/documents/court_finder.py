#!/usr/bin/env python3
from __future__ import annotations

import html
import os
import re
import sys
import datetime as dt
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil_chat.vergil_chat_errors import user_safe_error

from documents.envelope import pick_party_address


BASE_URL = os.getenv("CASEFORGE_COURT_FINDER_BASE_URL", "https://www.find-court-tribunal.service.gov.uk").rstrip("/")
TIMEOUT_SECONDS = float(os.getenv("CASEFORGE_COURT_FINDER_TIMEOUT", "8"))

SERVICE_AREA_CHOICES: dict[str, str] = {
    "Domestic abuse / non-molestation": "domestic-abuse",
    "Child arrangements / C100": "childcare-arrangements",
}
DEFAULT_SERVICE_LABEL = "Domestic abuse / non-molestation"
PUBLIC_SEARCH_PATHS: dict[str, str] = {
    "domestic-abuse": "/services/harm-and-abuse/domestic-abuse/nearest/search-by-postcode",
    "childcare-arrangements": "/services/children/childcare-arrangements/nearest/search-by-postcode",
    "forced-marriage": "/services/harm-and-abuse/forced-marriage/nearest/search-by-postcode",
}
NOTE_FILENAME = "Court Finder - 5 nearest courts.txt"
TOP_COURT_COUNT = 5

POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)


def normalise_postcode(value: str) -> str:
    match = POSTCODE_RE.search(" ".join(str(value or "").upper().split()))
    if not match:
        return ""
    return f"{match.group(1)} {match.group(2)}"


def compact_postcode(value: str) -> str:
    postcode = normalise_postcode(value)
    return postcode.replace(" ", "")


def service_slug_for_label(label: str) -> str:
    slug = SERVICE_AREA_CHOICES.get(str(label or "").strip(), "")
    return slug or SERVICE_AREA_CHOICES[DEFAULT_SERVICE_LABEL]


def find_nearest_courts(
    postcode_text: str,
    service_area: str,
    *,
    limit: int = 10,
    detail_limit: int = 3,
) -> dict[str, Any]:
    postcode = normalise_postcode(postcode_text)
    if not postcode:
        return {"ok": False, "message": "Enter a valid UK postcode."}

    service_slug = str(service_area or "").strip()
    if service_slug not in set(SERVICE_AREA_CHOICES.values()):
        return {"ok": False, "message": "Choose a supported family court search type."}

    url = f"{BASE_URL}/v2/proxy/search/postcode/{quote(compact_postcode(postcode))}/serviceArea/{quote(service_slug)}"
    try:
        payload = _fetch_json(url)
    except Exception as exc:
        return {"ok": False, "message": user_safe_error(exc, "Court finder lookup")}

    courts = payload.get("courts") if isinstance(payload, dict) else []
    if not isinstance(courts, list) or not courts:
        _record_lookup(service_slug, 0)
        return {
            "ok": False,
            "message": "No court finder results were returned for that postcode and case type.",
            "postcode": postcode,
            "service_area": service_slug,
        }

    rows: list[dict[str, Any]] = []
    for source_rank, row in enumerate(courts[: max(1, min(int(limit or 10), 20))], start=1):
        if not isinstance(row, dict):
            continue
        normalised = _normalise_result(row)
        normalised["source_rank"] = source_rank
        normalised["display_rank"] = source_rank
        rows.append(normalised)
    nearest_rows = sorted(rows, key=lambda row: int(row.get("source_rank") or 999))

    for row in nearest_rows[: max(0, min(int(detail_limit or 0), len(nearest_rows)))]:
        slug = str(row.get("slug") or "").strip()
        if not slug:
            continue
        try:
            details = _fetch_json(f"{BASE_URL}/v2/proxy/search/slug/{quote(slug)}")
        except Exception as exc:
            row["detail_error"] = type(exc).__name__
            continue
        _merge_details(row, details if isinstance(details, dict) else {})

    _record_lookup(service_slug, len(rows))
    return {
        "ok": True,
        "postcode": postcode,
        "service_area": service_slug,
        "service_name": str(payload.get("name") or _label_for_slug(service_slug)),
        "courts": nearest_rows,
        "nearest_courts": nearest_rows[:TOP_COURT_COUNT],
        "top_courts": nearest_rows[:TOP_COURT_COUNT],
        "court_note": format_court_finder_note(
            postcode,
            str(payload.get("name") or _label_for_slug(service_slug)),
            nearest_rows,
            _public_search_url(service_slug),
        ),
        "source_url": _public_search_url(service_slug),
    }


def court_note_for_postcode(postcode_text: str, service_area: str) -> dict[str, Any]:
    result = find_nearest_courts(postcode_text, service_area, limit=10, detail_limit=TOP_COURT_COUNT)
    if not result.get("ok"):
        return result
    return {
        "ok": True,
        "postcode": result.get("postcode"),
        "service_area": result.get("service_area"),
        "source_url": result.get("source_url"),
        "note_filename": NOTE_FILENAME,
        "note_text": result.get("court_note") or "",
        "nearest_courts": result.get("nearest_courts") or [],
        "top_courts": result.get("top_courts") or [],
    }


def format_court_finder_note(
    postcode: str,
    service_name: str,
    nearest_rows: list[dict[str, Any]],
    source_url: str,
) -> str:
    nearest = sorted(nearest_rows, key=lambda row: int(row.get("source_rank") or 999))[:TOP_COURT_COUNT]
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        "Court Finder - 5 nearest courts",
        f"Generated: {generated}",
        f"Postcode used: {normalise_postcode(postcode)}",
        f"Service area: {service_name}",
        f"Source: {source_url}",
        "",
        "Nearest courts by GOV.UK distance (top 5):",
    ]
    if nearest:
        lines.extend(_court_note_lines(nearest))
    else:
        lines.append("No GOV.UK nearest-court results returned.")

    lines.extend(
        [
            "",
            "Reminder: this is an administrative lookup only. A human must decide which court to use and confirm the assigned/listed court before filing.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_court_contact_card(result: dict[str, Any], matter_ref: str = "") -> str:
    courts = (result.get("top_courts") or result.get("courts") or [])[:5]
    ref = str(matter_ref or "").strip()
    header = f"**Nearest courts — matter {ref}**" if ref else "**Nearest courts**"
    postcode = str(result.get("postcode") or "").strip()
    lines = [header]
    if postcode:
        lines.append(f"Postcode `{postcode}`")
    lines.append("")
    if not courts:
        lines.append("_No GOV.UK nearest-court results._")
        return "\n".join(lines)
    for idx, court in enumerate(courts, start=1):
        name = str(court.get("name") or "Unnamed court").strip()
        distance = court.get("distance_miles")
        dist_txt = f" — {float(distance):.1f} mi" if isinstance(distance, (int, float)) else ""
        lines.append(f"{idx}. **{name}**{dist_txt}")
        phone = _first_contact_value(court, "phones", "phone")
        email = _first_contact_value(court, "family_emails", "") or _first_contact_value(court, "emails", "email")
        detail = [
            str(court.get("address") or "").strip(),
            (f"☎ {phone}" if phone else ""),
            email,
        ]
        detail = [bit for bit in detail if bit]
        if detail:
            lines.append("   " + " · ".join(detail))
    lines.append("")
    lines.append("_Administrative lookup — confirm the assigned court on the papers before filing._")
    return "\n".join(lines)


def record_selected_court(
    matter_id: str,
    court_name: str,
    *,
    postcode: str = "",
    service_area: str = "",
) -> dict[str, Any]:
    mid = str(matter_id or "").strip()
    name = " ".join(str(court_name or "").split())
    if not mid or not name:
        return {"ok": False, "message": "A matter and a court name are both required to record a selection."}
    try:
        from documents.court_of_record import record_court_selection

        row = record_court_selection(mid, name, postcode=postcode, service_area=service_area)
    except Exception as exc:
        return {"ok": False, "message": user_safe_error(exc, "Recording the selected court")}
    return {"ok": True, "matter_id": mid, "court": row.get("court"), "source": row.get("source")}


def _first_contact_value(court: dict[str, Any], list_key: str, singular_key: str) -> str:
    for item in court.get(list_key) or []:
        if isinstance(item, dict):
            value = str(item.get("value") or "").strip()
        else:
            value = str(item or "").strip()
        if value:
            return value
    if singular_key:
        return str(court.get(singular_key) or "").strip()
    return ""


def resolve_client_applicant_postcode(query: str) -> dict[str, Any]:
    clean_query = " ".join(str(query or "").split())
    if len(clean_query) < 2:
        return {"ok": False, "message": "Enter a client name, email, or reference first."}
    try:
        from clientdb_sql import get_connection
        import agwu
    except Exception as exc:
        return {"ok": False, "message": user_safe_error(exc, "The client database lookup")}

    _result = agwu.resolve_client(
        clean_query, limit=5, caller="documents.court_finder.resolve_client_applicant_postcode"
    )
    rows = [m.row for m in _result.matches]
    if not rows:
        return {"ok": False, "message": f"No client match found for {clean_query}."}
    was_exact = bool(_result.top and "exact_search" in _result.top.match_sources)

    matter = rows[0]
    matter_id = str(matter.get("matter_id") or "").strip()
    if not matter_id:
        return {"ok": False, "message": "Matched matter has no matter_id."}
    has_c8 = _truthy(matter.get("has_c8"))

    try:
        parties = _load_parties(get_connection, matter_id)
    except Exception as exc:
        return {"ok": False, "message": user_safe_error(exc, "Reading party addresses")}
    picked = pick_party_address(parties, "Applicant", has_c8=has_c8)
    if not picked.get("ok"):
        return picked

    postcode = normalise_postcode("\n".join(str(line) for line in picked.get("lines") or []))
    if not postcode:
        return {"ok": False, "message": "Applicant address is recorded but no valid postcode was found."}
    warnings = []
    if not was_exact:
        warnings.append(
            f"No exact match for '{clean_query}' — this postcode came from the closest "
            f"match, {str(matter.get('client_name') or '').strip() or 'the top candidate'}. "
            "Check it is the right client."
        )
    if len(rows) > 1:
        warnings.append("Multiple client matches found; using the first SQL result.")
    if has_c8:
        warnings.append(
            "C8 matter: the postcode was read from the protected applicant address for this "
            "lookup only. It is not shown and must not be put in respondent-facing material."
        )
    return {
        "ok": True,
        "postcode": postcode,
        "label": str(picked.get("display_name") or matter.get("client_name") or "Applicant").strip(),
        "matter_id": matter_id,
        "client_name": str(matter.get("client_name") or "").strip(),
        "has_c8": has_c8,
        "warning": " ".join(warnings),
        "was_fuzzy_resolved": not was_exact,
    }


def _fetch_json(url: str) -> Any:
    response = requests.get(
        url,
        headers={"Accept": "application/json", "User-Agent": "CaseForge-Automation-Court-Finder/1.0"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _normalise_result(row: dict[str, Any]) -> dict[str, Any]:
    slug = str(row.get("slug") or "").strip()
    return {
        "name": str(row.get("name") or "").strip(),
        "slug": slug,
        "open": bool(row.get("open")),
        "distance_miles": _as_float(row.get("distance")),
        "areas_of_law": [str(item) for item in row.get("areasOfLawSpoe") or [] if str(item).strip()],
        "govuk_url": f"{BASE_URL}/courts/{slug}" if slug else "",
    }


def _court_note_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for index, row in enumerate(rows[:TOP_COURT_COUNT], start=1):
        name = str(row.get("name") or "Unnamed court").strip()
        distance = row.get("distance_miles")
        distance_text = f"{float(distance):.1f} miles" if isinstance(distance, (int, float)) else "distance unavailable"
        family_emails = [str(item.get("value") or "").strip() for item in row.get("family_emails") or [] if item.get("value")]
        suffix = f" | Family email: {'; '.join(family_emails[:3])}" if family_emails else ""
        lines.append(f"{index}. {name} - {distance_text}{suffix}")
    return lines


def _merge_details(row: dict[str, Any], details: dict[str, Any]) -> None:
    row["types"] = [str(item) for item in details.get("types") or [] if str(item).strip()]
    row["address"] = _first_address(details)
    row["emails"] = _contacts(details, "emails", "address")
    row["family_emails"] = _family_email_contacts(row["emails"]) or _county_court_inbox(row["emails"], row["types"])
    row["phones"] = _contacts(details, "contacts", "number")
    if details.get("urgent_message"):
        row["urgent_message"] = _clean_html(details.get("urgent_message"))
    if details.get("info"):
        row["info"] = _clean_html(details.get("info"))[:500]


def _first_address(details: dict[str, Any]) -> str:
    addresses = [row for row in details.get("addresses") or [] if isinstance(row, dict)]
    if not addresses:
        return ""
    preferred = next((row for row in addresses if "visit" in str(row.get("type") or "").lower()), addresses[0])
    parts: list[str] = []
    parts.extend(str(line).strip() for line in preferred.get("address_lines") or [] if str(line).strip())
    if preferred.get("town"):
        parts.append(str(preferred["town"]).strip())
    if preferred.get("postcode"):
        parts.append(str(preferred["postcode"]).strip())
    return ", ".join(part for part in parts if part)


def _contacts(details: dict[str, Any], field: str, value_key: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in details.get(field) or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get(value_key) or "").strip()
        if not value:
            continue
        rows.append(
            {
                "value": value,
                "description": str(item.get("description") or "").strip(),
                "explanation": str(item.get("explanation") or "").strip(),
            }
        )
    return rows[:12] if field == "emails" else rows[:5]


def _county_court_inbox(rows: list[dict[str, str]], types: list[str]) -> list[dict[str, str]]:
    if not any(str(t).strip().lower() == "family court" for t in types):
        return []
    return [row for row in rows if str(row.get("description") or "").strip().lower() == "county court"][:1]


def _family_email_contacts(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    scored: list[tuple[int, int, dict[str, str]]] = []
    for index, row in enumerate(rows):
        value = str(row.get("value") or "").strip()
        if not value:
            continue
        text = " ".join(
            [
                value.lower(),
                str(row.get("description") or "").lower(),
                str(row.get("explanation") or "").lower(),
            ]
        )
        score = 0
        if "social security" in text or "child support" in text:
            continue
        if "public law" in text or "fpl" in value.lower() or re.search(r"(?<![a-z0-9])c5(?![0-9])", text):
            continue
        if "c100" in text or "private law" in text or "privateapps" in value.lower() or "privatelaw" in value.lower():
            score += 400
        if "family" in value.lower():
            score += 80
        if "family court" in text:
            score += 100
        if "family" in text:
            score += 50
        if score:
            if "application" in text:
                score += 300
            if re.search(r"divorce|financial remedy|public law|children in care|transcript|family orders", text):
                score -= 200
            scored.append((-score, index, row))
    return [row for _, _, row in sorted(scored)[:5]]


def _load_parties(get_connection_func, matter_id: str) -> list[dict[str, Any]]:
    from clientdb_sql import list_parties_with_address

    return list_parties_with_address(matter_id)


def _clean_html(value: Any) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(str(value or ""))).split())


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _label_for_slug(slug: str) -> str:
    return next((label for label, value in SERVICE_AREA_CHOICES.items() if value == slug), slug)


def _public_search_url(service_slug: str) -> str:
    return BASE_URL + PUBLIC_SEARCH_PATHS.get(
        service_slug,
        f"/services/{quote(service_slug)}/service-areas/nearest/search-by-postcode",
    )


def _record_lookup(service_area: str, result_count: int) -> None:
    try:
        from telemetry_sqlite import record_runtime_event, utc_now_z

        record_runtime_event(
            {
                "timestamp": utc_now_z(),
                "event_name": "caseforge_chat_court_finder_lookup",
                "runtime_label": os.getenv("CASEFORGE_RUNTIME_LABEL", ""),
                "model_label": os.getenv("CASEFORGE_MODEL_LABEL", ""),
                "command": "caseforge-chat court finder lookup",
                "files_read": ["tools/documents/court_finder.py"],
                "files_written": [],
                "metrics": {"service_area": service_area, "result_count": result_count},
            }
        )
    except Exception:
        pass
