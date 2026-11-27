
from __future__ import annotations

import datetime as dt
import re

from hearing_calendar import hearing_dates
from london_time import london_today

DEFAULT_SCANNED_DOCS_PATH = "Company_Data/Scanned Docs"

SURNAME_SPLIT_RE = re.compile(r"\s+-\s+")
NAME_SUFFIX_RE = re.compile(r"\.(?:pdf|docx)$", re.IGNORECASE)
VALID_SURNAME_RE = re.compile(r"[A-Za-z][A-Za-z'\- ]{0,40}$")
NOT_A_SURNAME = {"TRANSCRIPT", "COPY", "SIGNED", "FINAL", "DRAFT", "REDACTED", "SCAN"}
FILENAME_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4}|\d{2})(?!\d)")
FILENAME_DATE_YMD_RE = re.compile(r"(?<!\d)(20\d{2})([.\-/_])(0[1-9]|1[0-2])\2(0[1-9]|[12]\d|3[01])(?!\d)")
_MONTH_NUMBER = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
                 "sep": 9, "oct": 10, "nov": 11, "dec": 12}
FILENAME_DATE_WRITTEN_RE = re.compile(
    r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?,?\s+(\d{4}|\d{2})(?!\d)",
    re.IGNORECASE,
)


def _iso(year: str, month: int, day: int) -> str:
    y = int(year)
    if y < 100:
        y += 2000
    try:
        return dt.date(y, month, day).isoformat()
    except ValueError:
        return ""


MIN_DOCUMENT_YEAR = 2011
MAX_YEARS_AHEAD = 2


def _numeric_date(first: str, month: str, last: str, reference: dt.date, floor_year: int) -> str:
    if len(last) == 4:
        iso = _iso(last, int(month), int(first))
        return iso if iso and int(last) >= floor_year else ""
    readings = [_iso(last, int(month), int(first))]
    if len(first) == 2:
        readings.append(_iso(first, int(month), int(last)))
    ceiling = reference.year + MAX_YEARS_AHEAD
    kept = [i for i in readings if i and floor_year <= int(i[:4]) <= ceiling]
    if not kept:
        return ""
    return min(kept, key=lambda i: abs((dt.date.fromisoformat(i) - reference).days))


def filename_date(name: str, reference: dt.date | None = None, floor_year: int = MIN_DOCUMENT_YEAR) -> str:
    text = str(name or "")
    reference = reference or london_today()
    span = filename_span(text)
    if span and span["form"] == "label":
        return span["start"]
    numeric: list[tuple[int, str]] = []
    for m in FILENAME_DATE_RE.finditer(text):
        d, mo, y = m.groups()
        iso = _numeric_date(d, mo, y, reference, floor_year)
        if iso:
            numeric.append((m.start(), iso))
    for m in FILENAME_DATE_YMD_RE.finditer(text):
        y, _sep, mo, d = m.groups()
        iso = _iso(y, int(mo), int(d))
        if iso:
            numeric.append((m.start(), iso))
    if numeric:
        return min(numeric)[1]
    for m in FILENAME_DATE_WRITTEN_RE.finditer(text):
        d, mon, y = m.groups()
        iso = _iso(y, _MONTH_NUMBER[mon[:3].lower()], int(d))
        if iso:
            return iso
    return ""


def filename_span(name: str) -> dict | None:
    found = hearing_dates.parse_span(NAME_SUFFIX_RE.sub("", str(name or "")))
    return found if found and found["form"] != "day_count" else None


def filename_surname(name: str) -> str | None:
    stem = NAME_SUFFIX_RE.sub("", str(name or "")).strip()
    parts = [p.strip() for p in SURNAME_SPLIT_RE.split(stem) if p.strip()]
    if len(parts) < 2:
        return None
    candidate = parts[-1]
    if candidate.upper() in NOT_A_SURNAME:
        return None
    if not VALID_SURNAME_RE.fullmatch(candidate):
        return None
    return candidate.upper()
