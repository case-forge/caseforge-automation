#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import logging
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

TTL_SECONDS = 24 * 3600
CHAMBERS_COUNT = 5
log = logging.getLogger(__name__)
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)


def normalise_postcode(value: Any) -> str:
    match = _POSTCODE_RE.search(" ".join(str(value or "").upper().split()))
    return f"{match.group(1)} {match.group(2)}" if match else ""


def client_postcode(matter_id: str) -> str:
    import clientdb_sql

    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT address_postcode, address_text FROM dbo.matter_parties WHERE matter_id = ? AND LOWER(role) = 'applicant'",
            (int(matter_id),),
        )
        party = cur.fetchone()
        cur.execute(
            "SELECT p.address_postcode, p.address_text FROM dbo.matters m LEFT JOIN dbo.people p ON p.person_id = m.primary_person_id "
            "WHERE m.matter_id = ?",
            (int(matter_id),),
        )
        person = cur.fetchone()
    for row in (party, person):
        if row:
            for value in row:
                found = normalise_postcode(value)
                if found:
                    return found
    return ""


def _court(postcode: str) -> tuple[dict[str, Any] | None, str]:
    from documents import court_finder as cf

    result = cf.find_nearest_courts(postcode, cf.service_slug_for_label(cf.DEFAULT_SERVICE_LABEL), limit=1, detail_limit=1)
    if not result.get("ok") or not result.get("courts"):
        return None, "The court finder found no court for this postcode."
    row = result["courts"][0]
    return {
        "name": str(row.get("name") or ""),
        "distance_miles": row.get("distance_miles"),
        "address": str(row.get("address") or ""),
        "family_emails": [str(e.get("value") or "") for e in row.get("family_emails") or [] if e.get("value")][:3],
        "url": str(row.get("govuk_url") or ""),
        "service": str(result.get("service_name") or ""),
    }, ""


def _chambers(postcode: str) -> tuple[list[dict[str, Any]], str, str]:
    from caseforge_cli import base
    from caseforge_cli.chambers_finder import ChambersFinderCLI

    try:
        found = ChambersFinderCLI().nearest(postcode, courts=1, chambers=CHAMBERS_COUNT)
    except base.PostcodeOutsideEnglandWalesError:
        return [], "", "This postcode is outside England and Wales, so no chambers are listed."
    except base.PostcodeUnknownError:
        return [], "", "The chambers finder does not recognise this postcode."
    rows = []
    for row in (found.get("chambers") or [])[:CHAMBERS_COUNT]:
        branch = row.get("branch") if isinstance(row.get("branch"), dict) else {}
        rows.append(
            {
                "name": str(row.get("name") or ""),
                "email": str(row.get("email") or ""),
                "phone": str(branch.get("phone") or row.get("phone") or ""),
                "branch": str(branch.get("name") or ""),
                "distance_miles": row.get("distanceFromPostcodeMiles", row.get("distanceMiles")),
                "website": str(row.get("website") or "") if str(row.get("website") or "").startswith("https://") else "",
            }
        )
    court = found.get("chosenCourt") if isinstance(found.get("chosenCourt"), dict) else {}
    return rows, str(court.get("name") or ""), "" if rows else "The chambers finder named no chambers near this postcode."


def nearest(postcode: str, *, now: float | None = None) -> dict[str, Any]:
    moment = time.monotonic() if now is None else now
    key = hashlib.sha256(postcode.encode("utf-8")).hexdigest()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and moment - hit[0] < TTL_SECONDS:
            return hit[1]
    try:
        court, court_error = _court(postcode)
    except Exception as exc:
        log.warning("nearest court lookup failed: %s", type(exc).__name__)
        court, court_error = None, "The court finder could not be reached."
    try:
        chambers, measured_from, chambers_error = _chambers(postcode)
    except Exception as exc:
        log.warning("nearest chambers lookup failed: %s", type(exc).__name__)
        chambers, measured_from, chambers_error = [], "", "The chambers finder could not be run."
    answer = {
        "ok": True,
        "area": postcode.split(" ")[0],
        "court": court,
        "court_error": court_error,
        "chambers": chambers,
        "chambers_measured_from": measured_from,
        "chambers_error": chambers_error,
    }
    if court is not None or chambers:
        with _LOCK:
            _CACHE[key] = (moment, answer)
    return answer


def for_matter(matter_id: Any) -> dict[str, Any]:
    mid = str(matter_id or "").strip()
    if not mid.isdigit():
        raise ValueError("matter_id must be a matter number")
    postcode = client_postcode(mid)
    if not postcode:
        return {"ok": False, "reason": "no_postcode", "message": "There is no postcode on the client's record, so nothing nearby can be found."}
    return nearest(postcode)


def clear() -> None:
    with _LOCK:
        _CACHE.clear()
