
from __future__ import annotations

import datetime as dt
import re
from typing import Any
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
UTC = dt.timezone.utc

_TZID_ALIASES = {
    "GMT STANDARD TIME": "Europe/London",
    "GREENWICH STANDARD TIME": "Atlantic/Reykjavik",
    "UTC": "UTC",
    "COORDINATED UNIVERSAL TIME": "UTC",
    "EUROPE/LONDON": "Europe/London",
    "W. EUROPE STANDARD TIME": "Europe/Berlin",
    "CENTRAL EUROPE STANDARD TIME": "Europe/Budapest",
    "CENTRAL EUROPEAN STANDARD TIME": "Europe/Warsaw",
    "ROMANCE STANDARD TIME": "Europe/Paris",
    "GTB STANDARD TIME": "Europe/Bucharest",
    "E. EUROPE STANDARD TIME": "Europe/Chisinau",
    "IRISH STANDARD TIME": "Europe/Dublin",
}


def unfold(text: str) -> str:
    return re.sub(r"\r?\n[ \t]", "", str(text or "").replace("\r\n", "\n").replace("\r", "\n"))


def unescape(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        char = value[i]
        if char == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append("\n" if nxt in "nN" else nxt)
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out).strip()


def _split_line(line: str) -> tuple[str, dict[str, str], str] | None:
    in_quote = False
    colon = -1
    for index, char in enumerate(line):
        if char == '"':
            in_quote = not in_quote
        elif char == ":" and not in_quote:
            colon = index
            break
    if colon < 1:
        return None
    head, value = line[:colon], line[colon + 1:]
    parts = head.split(";")
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, _, val = part.partition("=")
            params[key.upper()] = val.strip('"')
    return parts[0].upper(), params, value


def _zone(tzid: str) -> tuple[Any, bool]:
    key = tzid.strip().upper()
    name = _TZID_ALIASES.get(key, tzid.strip())
    try:
        return ZoneInfo(name), True
    except Exception:
        return LONDON, False


def _parse_datetime(value: str, params: dict[str, str]) -> tuple[dt.datetime | dt.date | None, bool, str]:
    raw = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", raw):
        try:
            return dt.datetime.strptime(raw[:8], "%Y%m%d").date(), False, ""
        except ValueError:
            return None, False, ""
    match = re.fullmatch(r"(\d{8}T\d{6})(Z?)", raw)
    if not match:
        return None, False, ""
    naive = dt.datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
    if match.group(2):
        return naive.replace(tzinfo=UTC).astimezone(LONDON), False, ""
    tzid = params.get("TZID", "")
    if tzid:
        zone, known = _zone(tzid)
        return naive.replace(tzinfo=zone).astimezone(LONDON), not known, "" if known else tzid.strip()
    return naive.replace(tzinfo=LONDON), True, ""


def parse_ics(text: str) -> list[dict[str, Any]]:
    lines = [line for line in unfold(text).split("\n") if line.strip()]
    method = ""
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    depth = 0
    for line in lines:
        parsed = _split_line(line)
        if parsed is None:
            continue
        name, params, value = parsed
        if name == "BEGIN" and value.upper() == "VEVENT":
            current, depth = {"params": {}, "tz_assumed": False, "recurring": False}, 0
            continue
        if name == "BEGIN" and current is not None:
            depth += 1
            continue
        if name == "END" and value.upper() == "VEVENT" and current is not None:
            events.append(current)
            current = None
            continue
        if name == "END" and current is not None:
            depth = max(0, depth - 1)
            continue
        if current is None:
            if name == "METHOD":
                method = value.strip().upper()
            continue
        if depth:
            continue
        if name in ("DTSTART", "DTEND"):
            parsed_value, assumed, unknown = _parse_datetime(value, params)
            current[name.lower()] = parsed_value
            current["tz_assumed"] = current["tz_assumed"] or assumed
            if unknown:
                current["tz_unknown"] = current.get("tz_unknown") or unknown
        elif name in ("SUMMARY", "LOCATION", "DESCRIPTION", "UID", "URL", "STATUS"):
            current[name.lower()] = unescape(value) if name != "STATUS" else value.strip().upper()
        elif name == "RRULE":
            current["recurring"] = True
    result: list[dict[str, Any]] = []
    for event in events:
        start, end = event.get("dtstart"), event.get("dtend")
        if start is None:
            continue
        all_day = isinstance(start, dt.date) and not isinstance(start, dt.datetime)
        end_given = end is not None
        if end is None:
            end = start if all_day else start + dt.timedelta(hours=1)
        result.append(
            {
                "uid": event.get("uid", ""),
                "summary": event.get("summary", ""),
                "location": event.get("location", ""),
                "description": event.get("description", ""),
                "url": event.get("url", ""),
                "status": event.get("status", ""),
                "method": method,
                "cancelled": method == "CANCEL" or event.get("status", "") == "CANCELLED",
                "recurring": bool(event.get("recurring")),
                "all_day": all_day,
                "start": start,
                "end": end,
                "end_given": end_given,
                "tz_assumed": bool(event.get("tz_assumed")),
                "tz_unknown": str(event.get("tz_unknown") or ""),
            }
        )
    return result


def duration_stated(event: dict[str, Any]) -> bool:
    start, end = event.get("start"), event.get("end")
    if not event.get("end_given", True):
        return False
    return isinstance(start, dt.datetime) and isinstance(end, dt.datetime) and end > start


def duration_minutes(event: dict[str, Any]) -> int:
    start, end = event.get("start"), event.get("end")
    if not isinstance(start, dt.datetime) or not isinstance(end, dt.datetime):
        return 60
    minutes = int((end - start).total_seconds() // 60)
    return max(15, min(minutes, 480)) if minutes > 0 else 60
