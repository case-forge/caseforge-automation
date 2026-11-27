#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional, Tuple


_DATE_TOKEN_RE = re.compile(
    r"(?P<token>\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+\d{4}\b)",
    re.IGNORECASE,
)
_HEARING_CONTEXT_RE = re.compile(
    r"(?:new\s+hearing\s+date|hearing(?: date)?|return hearing|fact[- ]finding hearing|final hearing|fhdra|dra|directions hearing|listed(?: for)?|hearing on)"
    r"(?:\s+(?:of|on|for|at))?"
    r"[^A-Za-z0-9]{0,20}"
    r"(?P<token>\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+\d{4})",
    re.IGNORECASE,
)
_TIME_RE = re.compile(
    r"\b(?P<token>(?:[01]?\d|2[0-3]):\d{2}(?:\s?(?:am|pm))?|(?:0?\d|1[0-2])\.\d{2}\s?(?:am|pm))\b",
    re.IGNORECASE,
)
_URGENT_RE = re.compile(r"\b(urgent|immediate|asap|without delay|today please|urgent attention)\b", re.IGNORECASE)
_RELIST_RE = re.compile(r"\b(adjourned|relisted|vacated|brought forward|cancelled|rescheduled)\b", re.IGNORECASE)
_SEALED_ORDER_RE = re.compile(r"\bsealed order\b|\border attached\b|\bsealed copy\b", re.IGNORECASE)
_NOTICE_RE = re.compile(r"\bnotice of hearing\b|\bnotice of proceedings\b|\btransfer order\b", re.IGNORECASE)
_SERVICE_RE = re.compile(r"\bservice\b|\bstatement of service\b|\bserved\b|\bpersonal service\b", re.IGNORECASE)
_CLIENT_CHASE_RE = re.compile(
    r"\b(update|any update|any news|chasing|what is happening|where are we up to|have you heard|sealed order|served)\b",
    re.IGNORECASE,
)
_REMOTE_RE = re.compile(r"\b(remote|hybrid|teams|cvp|telephone hearing|video hearing)\b", re.IGNORECASE)


def _parse_date_token(token: str, received_dt: dt.datetime) -> Optional[dt.date]:
    raw = token.strip()
    raw = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", raw, flags=re.IGNORECASE)
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%y", "%d-%m-%y", "%d %B %Y"):
        try:
            parsed = dt.datetime.strptime(raw, fmt)
            if parsed.year < 100:
                parsed = parsed.replace(year=2000 + parsed.year)
            return parsed.date()
        except ValueError:
            continue
    return None


def _working_days_until(start_dt: dt.datetime, end_date: dt.date) -> Optional[int]:
    start_date = start_dt.astimezone(dt.timezone.utc).date()
    if end_date < start_date:
        return None
    cursor = start_date
    working_days = 0
    while cursor < end_date:
        cursor += dt.timedelta(days=1)
        if cursor.weekday() < 5:
            working_days += 1
    return working_days


def _normalise_time_token(token: str) -> str:
    value = str(token or "").strip().upper().replace(".", ":")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"^(\d{1,2}:\d{2})(AM|PM)$", r"\1 \2", value)
    return value


def _extract_time_near_position(text: str, anchor_start: int, anchor_end: int) -> str:
    start = max(0, anchor_start - 24)
    end = min(len(text), anchor_end + 40)
    window = text[start:end]
    match = _TIME_RE.search(window)
    if not match:
        return ""
    return _normalise_time_token(match.group("token"))


def _extract_hearing_details(text: str, received_dt: dt.datetime) -> Tuple[str, Optional[int], List[str]]:
    flags: List[str] = []
    token = ""
    token_start = -1
    token_end = -1
    match = _HEARING_CONTEXT_RE.search(text)
    if match:
        token = match.group("token")
        token_start, token_end = match.span("token")
    elif re.search(r"\bhearing today\b|\blisted today\b", text, flags=re.IGNORECASE):
        token = received_dt.strftime("%d/%m/%Y")
        flags.append("Hearing referred to as today")
    elif re.search(r"\bhearing tomorrow\b|\blisted tomorrow\b", text, flags=re.IGNORECASE):
        token = (received_dt + dt.timedelta(days=1)).strftime("%d/%m/%Y")
        flags.append("Hearing referred to as tomorrow")
    else:
        for candidate in _DATE_TOKEN_RE.finditer(text):
            window_start = max(0, candidate.start() - 24)
            context = text[window_start : candidate.end() + 24]
            if re.search(r"\bhearing\b|\blisted\b|\breturn\b|\bfhdra\b|\bdra\b", context, flags=re.IGNORECASE):
                token = candidate.group("token")
                token_start, token_end = candidate.span("token")
                break

    if not token:
        return "", None, flags

    hearing_date = _parse_date_token(token, received_dt)
    if not hearing_date:
        return "", None, flags
    if hearing_date < received_dt.astimezone(dt.timezone.utc).date():
        flags.append("Past hearing date ignored")
        return "", None, flags

    display = hearing_date.isoformat()
    hearing_time = ""
    if token_start >= 0 and token_end >= 0:
        hearing_time = _extract_time_near_position(text, token_start, token_end)
    if hearing_time:
        display = f"{display} {hearing_time}"
    working_days = _working_days_until(received_dt, hearing_date)
    return display, working_days, flags


def _band_for_score(score: int, same_day: bool, working_days_to_hearing: Optional[int]) -> str:
    if same_day:
        return "Critical"
    if working_days_to_hearing is not None and working_days_to_hearing <= 3:
        return "High"
    if working_days_to_hearing is not None and working_days_to_hearing <= 7:
        return "Medium"
    if working_days_to_hearing is not None and working_days_to_hearing <= 14:
        return "Low"
    if score >= 80:
        return "High"
    if score >= 60:
        return "Medium"
    if score >= 35:
        return "Low"
    return "Low"


def _urgency_bucket(working_days_to_hearing: Optional[int], same_day: bool) -> str:
    if same_day:
        return "same-day"
    if working_days_to_hearing is None:
        return "later"
    if working_days_to_hearing <= 3:
        return "high"
    if working_days_to_hearing <= 7:
        return "medium"
    if working_days_to_hearing <= 14:
        return "low"
    return "later"


def score_startup_email(
    *,
    subject: str,
    body: str,
    category: str,
    received_dt: dt.datetime,
    has_attachments: bool,
    importance: str,
    mailbox_position: str,
    matched_client: bool,
    source_folder: str,
    from_text: str,
) -> Dict[str, Any]:
    text = f"{subject}\n{body}"
    text_lower = text.lower()
    reasons: List[str] = []
    flags: List[str] = []
    score = 0

    hearing_date, working_days_to_hearing, hearing_flags = _extract_hearing_details(text, received_dt)
    flags.extend(hearing_flags)

    if category == "Court":
        score += 18
        reasons.append("Court email")
    elif category == "Counsel":
        score += 12
        reasons.append("Counsel email")
    elif category == "Clients" and _CLIENT_CHASE_RE.search(text):
        score += 8
        reasons.append("Client chasing for update")

    if has_attachments and category in {"Court", "Counsel", "Clients"}:
        score += 8
        reasons.append("Attachment present")

    if str(importance or "").strip().lower() == "high":
        score += 10
        reasons.append("Marked high importance")

    if mailbox_position == "To":
        score += 2

    if _URGENT_RE.search(subject) or _URGENT_RE.search(body):
        score += 18
        reasons.append("Urgent wording")

    if _RELIST_RE.search(text):
        score += 18
        reasons.append("Listing change detected")
        flags.append("Adjournment/relisting signal")

    if _SEALED_ORDER_RE.search(text):
        score += 14
        reasons.append("Sealed order signal")

    if _NOTICE_RE.search(text):
        score += 12
        reasons.append("Notice/listing signal")

    if _SERVICE_RE.search(text):
        score += 8
        reasons.append("Service signal")

    if _REMOTE_RE.search(text):
        score += 6
        flags.append("Hearing mode detail mentioned")

    if not matched_client and category in {"Court", "Counsel"}:
        score += 16
        reasons.append("Unmatched live email needs review")
        flags.append("Unmatched court/counsel email")

    if source_folder.lower() == "deleteditems" and category in {"Court", "Counsel"}:
        score += 5
        flags.append("Live email found outside Inbox")

    same_day = False
    if hearing_date and working_days_to_hearing is not None:
        reasons.append(f"Hearing detected ({hearing_date})")
        flags.append(f"Hearing date: {hearing_date}")
        if working_days_to_hearing <= 0:
            score += 38
            same_day = True
            reasons.append("Hearing is today")
        elif working_days_to_hearing == 1:
            score += 34
            reasons.append("Hearing is next working day")
        elif working_days_to_hearing <= 3:
            score += 28
            reasons.append("Hearing within 3 working days")
        elif working_days_to_hearing <= 7:
            score += 18
            reasons.append("Hearing within 7 working days")
        elif working_days_to_hearing <= 14:
            score += 8
            reasons.append("Hearing within 14 working days")

    if matched_client and category == "Clients" and _CLIENT_CHASE_RE.search(text) and mailbox_position == "To":
        flags.append("Client is asking for live status")

    score = min(score, 100)
    band = _band_for_score(score, same_day, working_days_to_hearing)
    bucket = _urgency_bucket(working_days_to_hearing, same_day)
    deduped_reasons = list(dict.fromkeys(reasons))
    deduped_flags = list(dict.fromkeys(flags))

    return {
        "score": score,
        "score_band": band,
        "predicted_urgency": bucket,
        "reasons": deduped_reasons,
        "flags": deduped_flags,
        "hearing_date": hearing_date,
        "working_days_to_hearing": working_days_to_hearing,
        "requires_same_day_action": same_day,
        "scored_from": {
            "category": category,
            "source_folder": source_folder,
            "from": from_text,
        },
    }
