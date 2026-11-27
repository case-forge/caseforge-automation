#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Iterable, Mapping

MAX_DAYS = 15
MAX_COUNT = 10
MAX_GAP_DAYS = 21

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_ORD = r"(?:st|nd|rd|th)?"
_SEP = r"(?:-|–|—|to|until|through)"
_WORD_NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _month(name: str) -> int:
    return _MONTHS[name.lower()[:3]]


def _year(text: str | int) -> int:
    y = int(text)
    return y + 2000 if y < 100 else y


def _date(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def fill_days(first: dt.date, last: dt.date) -> list[dt.date]:
    return [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]


def working_days_from(start: dt.date, count: int) -> list[dt.date]:
    out: list[dt.date] = []
    day = start
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def normalise_days(days: Iterable[dt.date]) -> list[dt.date]:
    return sorted(set(days))



_CROSS_MONTH_RE = re.compile(
    rf"(?<!\d)(\d{{1,2}}){_ORD}\s+(?:of\s+)?({_MONTH})\b\.?,?(?:\s+(\d{{4}}))?\s*{_SEP}\s*(\d{{1,2}}){_ORD}\s+(?:of\s+)?({_MONTH})\b\.?,?\s+(\d{{4}})(?!\d)",
    re.I,
)
_CHAIN_RE = re.compile(
    rf"(?<![\d.])(\d{{1,2}}){_ORD}((?:\s*(?:,|&|and|{_SEP})\s*(?:(?:mon|tues?|wed(?:nes)?|thu(?:rs?)?|fri)[a-z]*\.?\s+)?\d{{1,2}}{_ORD})+)(?:\s+of)?\s+({_MONTH})\b\.?,?\s+(\d{{4}})(?!\d)",
    re.I,
)
_FULL_DATE = rf"(\d{{1,2}}){_ORD}\s+(?:of\s+)?({_MONTH})\b\.?,?\s+(\d{{4}})"
_TWO_FULL_RE = re.compile(rf"(?<!\d){_FULL_DATE}\s*(,|&|and|{_SEP})\s*{_FULL_DATE}(?!\d)", re.I)
_NUMERIC_RANGE_RE = re.compile(
    rf"(?<![\d.])(\d{{1,2}})[./](\d{{1,2}})[./](\d{{4}}|\d{{2}})\s*{_SEP}\s*(\d{{1,2}})[./](\d{{1,2}})[./](\d{{4}}|\d{{2}})(?![\d.])", re.I
)
_LABEL_RE = re.compile(r"(?<![\d./])((?:\d{1,2}(?:\.\d{1,2})?(?:-\d{1,2}(?:\.\d{1,2})?)?,)*\d{1,2}(?:\.\d{1,2})?(?:-\d{1,2}(?:\.\d{1,2})?)?\.\d{1,2}\.(?:\d{4}|\d{2}))(?![\d.])")
_SEGMENT_RE = re.compile(r"^(\d{1,2})(?:\.(\d{1,2}))?(?:-(\d{1,2})(?:\.(\d{1,2}))?)?(?:\.(\d{4}|\d{2}))?$")
_START_RE = re.compile(rf"commenc\w*\s+(?:on\s+)?(?:\w+day\s+)?{_FULL_DATE}", re.I)
_COUNT_RES = (
    re.compile(r"\b(\d{1,2}|two|three|four|five|six|seven|eight|nine|ten)[- ]days?\b(?!\s*(?:ago|before|after|notice))", re.I),
)
_COUNT_BEFORE_RE = re.compile(r"(?:listed for|estimat\w*(?: length| duration| of)?|time estimate(?: of)?|length(?: of)?|duration(?: of)?|fixed for|allocated|sitting for)\W*(?:a |of |is )?(?:total )?(?:of )?$", re.I)
_COUNT_AFTER_RE = re.compile(r"^\W*(?:final |fact[- ]finding )?(?:hearing|trial|commencing|starting|from)\b", re.I)
_COUNT_NOT_RE = re.compile(r"(?:within|after|before|every|each|per|last|next|over|than)\W+(?:the\W+)?$", re.I)


def _result(days: list[dt.date], *, form: str, inferred: bool = False, count: int = 0) -> dict[str, Any] | None:
    days = normalise_days(days)
    if len(days) < 2 or (days[-1] - days[0]).days >= MAX_DAYS * 3:
        return None
    return {
        "start": days[0].isoformat(),
        "end": days[-1].isoformat(),
        "dates": [d.isoformat() for d in days],
        "days": count or len(days),
        "form": form,
        "end_inferred": inferred,
    }


def _chain_days(first: int, rest: str, y: int, m: int) -> list[dt.date] | None:
    tokens = re.findall(r"(,|&|and|-|–|—|to|until|through)|(\d{1,2})", re.sub(rf"(\d){_ORD}\b", r"\1", rest), re.I)
    numbers: list[int] = [first]
    ranges: list[bool] = []
    pending_range = False
    for sep, num in tokens:
        if sep:
            pending_range = sep.lower() in ("-", "–", "—", "to", "until", "through")
        elif num:
            numbers.append(int(num))
            ranges.append(pending_range)
            pending_range = False
    days: list[int] = [numbers[0]]
    for number, is_range in zip(numbers[1:], ranges):
        if number <= days[-1]:
            return None
        days.extend(range(days[-1] + 1, number + 1) if is_range else [number])
    out = [_date(y, m, d) for d in days]
    return None if any(d is None for d in out) else [d for d in out if d]


def parse_label(label: str) -> list[dt.date]:
    text = str(label or "").strip()
    segments = text.split(",")
    month = year = None
    out: list[dt.date] = []
    for seg in reversed(segments):
        found = _SEGMENT_RE.match(seg.strip())
        if not found:
            return []
        d1, m1, d2, m2, yy = found.groups()
        if yy:
            year = _year(yy)
        if year is None:
            return []
        if d2:
            end_month = int(m2) if m2 else (month if month else (int(m1) if m1 else None))
            start_month = int(m1) if m1 else end_month
        else:
            end_month = start_month = int(m1) if m1 else month
        if not end_month or not start_month:
            return []
        month = start_month
        first = _date(year if start_month <= end_month else year - 1, start_month, int(d1))
        last = _date(year, end_month, int(d2)) if d2 else first
        if first is None or last is None or last < first or (last - first).days >= MAX_DAYS * 3:
            return []
        out = fill_days(first, last) + out
    out = normalise_days(out)
    return out if len(out) >= 1 else []


def parse_span(text: str, *, start: str | dt.date | None = None) -> dict[str, Any] | None:
    raw = str(text or "")
    flat = re.sub(r"\s+", " ", raw)
    start_iso = start.isoformat() if isinstance(start, dt.date) else str(start or "")[:10]
    found = _parse_explicit(flat)
    if found is not None and (not start_iso or found["start"] == start_iso):
        return found
    if found is not None and start_iso:
        pass
    return _parse_day_count(flat, start_iso)


def _parse_explicit(flat: str) -> dict[str, Any] | None:
    for m in _CROSS_MONTH_RE.finditer(flat):
        d1, m1, y1, d2, m2, y2 = m.groups()
        month1, month2, y_end = _month(m1), _month(m2), int(y2)
        if month1 == month2 and not y1:
            continue
        first = _date(int(y1) if y1 else (y_end if month1 <= month2 else y_end - 1), month1, int(d1))
        last = _date(y_end, month2, int(d2))
        if first and last and first < last and (last - first).days < MAX_DAYS * 3:
            return _result(fill_days(first, last), form="written_cross_month")
    for m in _CHAIN_RE.finditer(flat):
        first_text, rest, month_name, year = m.groups()
        days = _chain_days(int(first_text), rest, int(year), _month(month_name))
        if days:
            return _result(days, form="written_days")
    for m in _TWO_FULL_RE.finditer(flat):
        d1, m1, y1, sep, d2, m2, y2 = m.groups()
        first, last = _date(int(y1), _month(m1), int(d1)), _date(int(y2), _month(m2), int(d2))
        if not first or not last or last <= first or (last - first).days > MAX_GAP_DAYS:
            continue
        if sep.lower() in (",", "&", "and"):
            return _result([first, last], form="written_dates")
        return _result(fill_days(first, last), form="written_range")
    for m in _NUMERIC_RANGE_RE.finditer(flat):
        d1, mo1, y1, d2, mo2, y2 = m.groups()
        first, last = _date(_year(y1), int(mo1), int(d1)), _date(_year(y2), int(mo2), int(d2))
        if first and last and first < last and (last - first).days < MAX_DAYS * 3:
            return _result(fill_days(first, last), form="numeric_range")
    for m in _LABEL_RE.finditer(flat):
        days = parse_label(m.group(1))
        if len(days) >= 2:
            return _result(days, form="label")
    return None


def day_count(text: str) -> int:
    flat = re.sub(r"\s+", " ", str(text or ""))
    for pattern in _COUNT_RES:
        for m in pattern.finditer(flat):
            before, after = flat[max(0, m.start() - 40): m.start()], flat[m.end(): m.end() + 30]
            if _COUNT_NOT_RE.search(before) or not (_COUNT_BEFORE_RE.search(before) or _COUNT_AFTER_RE.search(after)):
                continue
            raw = m.group(1).lower()
            n = _WORD_NUMBERS.get(raw) or (int(raw) if raw.isdigit() else 0)
            if 2 <= n <= MAX_COUNT:
                return n
    return 0


def _parse_day_count(flat: str, start_iso: str) -> dict[str, Any] | None:
    n = day_count(flat)
    if not n:
        return None
    first: dt.date | None = None
    commence = _START_RE.search(flat)
    if commence:
        d, mo, y = commence.groups()
        first = _date(int(y), _month(mo), int(d))
    if first is None and start_iso:
        try:
            first = dt.date.fromisoformat(start_iso)
        except ValueError:
            first = None
    if first is None:
        return None
    if start_iso and first.isoformat() != start_iso:
        return None
    days = working_days_from(first, n)
    return _result(days, form="day_count", inferred=True, count=n)




def span_days(hearing: Mapping[str, Any]) -> list[dt.date]:
    try:
        first = dt.date.fromisoformat(str(hearing.get("hearing_date") or "")[:10])
    except ValueError:
        return []
    listed: list[dt.date] = []
    for part in str(hearing.get("hearing_dates") or "").split(","):
        try:
            listed.append(dt.date.fromisoformat(part.strip()[:10]))
        except ValueError:
            continue
    if listed:
        return normalise_days([first, *listed])
    try:
        last = dt.date.fromisoformat(str(hearing.get("hearing_end_date") or "")[:10])
    except ValueError:
        return [first]
    return fill_days(first, last) if first < last and (last - first).days < MAX_DAYS * 3 else [first]


def is_multi_day(hearing: Mapping[str, Any]) -> bool:
    return len(span_days(hearing)) > 1


def last_day(hearing: Mapping[str, Any]) -> dt.date | None:
    days = span_days(hearing)
    return days[-1] if days else None


def label_for_days(days: Iterable[dt.date]) -> str:
    days = normalise_days(days)
    if not days:
        return ""
    if len(days) == 1:
        return days[0].isoformat()
    runs: list[tuple[dt.date, dt.date]] = []
    for day in days:
        if runs and (day - runs[-1][1]).days == 1:
            runs[-1] = (runs[-1][0], day)
        else:
            runs.append((day, day))
    pieces: list[tuple[str, int, int]] = []
    for a, b in runs:
        if (a.year, a.month) != (b.year, b.month):
            pieces.append((f"{a.day}.{a.month}-{b.day}", b.month, b.year))
        elif a == b:
            pieces.append((f"{a.day}", b.month, b.year))
        else:
            pieces.append((f"{a.day}-{b.day}", b.month, b.year))
    out = ""
    for i, (text, month, year) in enumerate(pieces):
        nxt = pieces[i + 1] if i + 1 < len(pieces) else None
        same_as_next = nxt is not None and (nxt[1], nxt[2]) == (month, year)
        if same_as_next:
            out += f"{text},"
        elif nxt is None:
            out += f"{text}.{month}.{year % 100:02d}"
        elif year == nxt[2]:
            out += f"{text}.{month},"
        else:
            out += f"{text}.{month}.{year % 100:02d},"
    return out


def short_date(day: dt.date) -> str:
    return f"{day.year % 100:02d}.{day.month}.{day.day}"


_YEAR_FIRST_HEARING = re.compile(r"^\s*(?:\d{1,3}\.\s+)?(\d{4}|\d{2})\.(\d{1,2})\.(\d{1,2})(?:-[A-Za-z]{2,12}){0,3}[-.]hearing(?=[-\s_]|$)(.*)$", re.I | re.S)


def year_first_start(name: str, today: dt.date | None = None) -> tuple[dt.date, str] | None:
    found = _YEAR_FIRST_HEARING.match(str(name or ""))
    if not found:
        return None
    first, month, last = int(found.group(1)), int(found.group(2)), int(found.group(3))
    try:
        year_first = dt.date(first + 2000 if first < 100 else first, month, last)
    except ValueError:
        return None
    rest = found.group(4).strip(" -_")
    if len(found.group(1)) == 2:
        try:
            day_first = dt.date(last + 2000, month, first)
        except ValueError:
            return year_first, rest
        from london_time import london_today

        today = today or london_today()

        def distance(day: dt.date) -> int:
            return (today - day).days if day <= today else (day - today).days * 2

        if distance(day_first) < distance(year_first):
            return None
    return year_first, rest


def folder_label(hearing: Mapping[str, Any]) -> str:
    days = span_days(hearing)
    if len(days) == 1:
        return short_date(days[0])
    return hearing_label(hearing)


def folder_name(hearing: Mapping[str, Any], surname: str) -> str:
    if is_multi_day(hearing):
        return f"{hearing_label(hearing)} Hearing - {surname}"
    return f"{folder_label(hearing)}-Hearing-{surname}"


def hearing_label(hearing: Mapping[str, Any]) -> str:
    days = span_days(hearing)
    if not days:
        return str(hearing.get("hearing_date") or "")[:10]
    return label_for_days(days)


def long_label(hearing: Mapping[str, Any]) -> str:
    days = span_days(hearing)
    if not days:
        return str(hearing.get("hearing_date") or "")
    first, last = days[0], days[-1]
    if len(days) == 1:
        return f"{first.day} {first:%B %Y}"
    consecutive = (last - first).days + 1 == len(days)
    if (first.month, first.year) == (last.month, last.year):
        if consecutive:
            return f"{first.day} to {last.day} {first:%B %Y}"
        listed = ", ".join(str(d.day) for d in days[:-1])
        return f"{listed} and {last.day} {first:%B %Y}"
    if consecutive:
        return f"{first.day} {first:%B} to {last.day} {last:%B %Y}" if first.year == last.year else f"{first.day} {first:%B %Y} to {last.day} {last:%B %Y}"
    return " and ".join(f"{d.day} {d:%B %Y}" for d in (first, last)) if len(days) == 2 else ", ".join(f"{d.day} {d:%B}" for d in days[:-1]) + f" and {last.day} {last:%B %Y}"


def label_start(name: str) -> tuple[dt.date, str] | None:
    found = re.match(r"^\s*(?:\d{1,3}\.\s+)?(\S+)(?:\s+(.*))?$", str(name or ""), re.S)
    if not found:
        return None
    days = parse_label(found.group(1))
    if len(days) < 2:
        return None
    return days[0], (found.group(2) or "").strip()
