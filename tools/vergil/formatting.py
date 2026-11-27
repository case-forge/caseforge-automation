from __future__ import annotations

import datetime as dt
from london_time import london_today
import re
from zoneinfo import ZoneInfo

from vergil.primitives import normalise_space

LONDON_TZ = ZoneInfo("Europe/London")

ATTENDANCE_SWITCHBOARD_CALLERS = {
    "client": "Client",
    "court": "Court",
    "respondent": "Respondent",
    "counsel": "Counsel",
    "other": "Other",
}

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def format_session_date(iso: str) -> str:
    try:
        d = dt.datetime.fromisoformat(iso.rstrip("Z")).replace(tzinfo=dt.timezone.utc)
        d_local = d.astimezone(ZoneInfo("Europe/London"))
        today = dt.datetime.now(ZoneInfo("Europe/London")).date()
        if d_local.date() == today:
            return d_local.strftime("%H:%M")
        return d_local.strftime("%d %b")
    except Exception:
        return ""


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def parse_iso_dt(value: str) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_countdown(target_utc: str) -> str:
    target = parse_iso_dt(target_utc)
    if target is None:
        return "Unknown"
    delta = target - dt.datetime.now(dt.timezone.utc)
    seconds = int(delta.total_seconds())
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    return f"{sign}{hours}h {minutes}m"


def format_outage_time(until_str: str) -> str:
    until = parse_iso_dt(until_str)
    if until is None:
        return until_str
    local = until.astimezone(LONDON_TZ)
    return local.strftime("%-d %b, %H:%M")


def parse_hearing_date(value: str) -> dt.date | None:
    text = normalise_space(value)
    if not text:
        return None
    match = re.search(
        r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+\d{4}\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", match.group(0), flags=re.IGNORECASE)
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_hearing_time(value: str) -> tuple[int, int] | None:
    text = normalise_space(value)
    if not text:
        return None
    patterns = (
        r"\b(?:at\s+)?(\d{1,2}):(\d{2})\s*(AM|PM)?\b",
        r"\b(?:at\s+)?(\d{1,2})\.(\d{2})\s*(AM|PM)\b",
        r"\bat\s+(\d{1,2})\.(\d{2})\b",
        r"\b(?:at\s+)?(\d{1,2})\s*(AM|PM)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.lastindex and match.lastindex >= 2 and match.group(2).isdigit() else 0
        meridiem = ""
        for group_index in range(2, (match.lastindex or 0) + 1):
            group = match.group(group_index)
            if group and group.upper() in {"AM", "PM"}:
                meridiem = group.upper()
                break
        if meridiem == "PM" and hour != 12:
            hour += 12
        elif meridiem == "AM" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    return None


def format_hearing_time(value: tuple[int, int] | None) -> str:
    if value is None:
        return ""
    hour, minute = value
    return f"{hour:02d}:{minute:02d}"


def format_run_time() -> str:
    now_uk = dt.datetime.now(LONDON_TZ)
    now_utc = dt.datetime.now(dt.timezone.utc)
    return (
        f"London time: {now_uk.strftime('%A %d %B %Y, %H:%M %Z')}\n"
        f"UTC: {now_utc.strftime('%A %d %B %Y, %H:%M UTC')}"
    )


def parse_attendance_switchboard_shorthand(text: str) -> dict[str, object]:
    for line in str(text or "").splitlines() or [str(text or "")]:
        m = re.search(
            r"(?P<client>[A-Za-z][A-Za-z'.\- ]{1,80}?)\s*/\s*"
            r"(?P<caller>Client|Court|Respondent|Counsel|Other)\s+"
            r"(?P<codes>\d(?:\s*,\s*\d)*)\b",
            line,
            flags=re.I,
        )
        if not m:
            continue
        raw_codes = [part.strip() for part in m.group("codes").split(",")]
        codes: list[str] = []
        for code in raw_codes:
            if re.fullmatch(r"\d", code) and code not in codes:
                codes.append(code)
        caller = ATTENDANCE_SWITCHBOARD_CALLERS.get(m.group("caller").lower(), "Client")
        return {
            "client": normalise_space(m.group("client")),
            "caller": caller,
            "codes": codes,
            "line": m.group(0).strip(),
        }
    return {}


def parse_backdate(prompt: str) -> dt.date | None:
    text = prompt.lower()
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(day_names):
        if f"last {day}" in text:
            today = london_today()
            delta = (today.weekday() - i) % 7 or 7
            return today - dt.timedelta(days=delta)
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    for mo_idx, mo in enumerate(month_names, 1):
        m = re.search(rf"(\d{{1,2}})\s+{mo}(?:\w*)?(?:\s+(\d{{2,4}}))?", text)
        if m:
            day = int(m.group(1))
            year = int(m.group(2)) if m.group(2) else london_today().year
            if year < 100:
                year += 2000
            try:
                return dt.date(year, mo_idx, day)
            except ValueError:
                pass
        m = re.search(rf"{mo}(?:\w*)?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+(\d{{2,4}}))?", text)
        if m:
            day = int(m.group(1))
            year = int(m.group(2)) if m.group(2) else london_today().year
            if year < 100:
                year += 2000
            try:
                return dt.date(year, mo_idx, day)
            except ValueError:
                pass
    m = re.search(r"(?:backdate|from)\s+(?:to\s+)?(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            return dt.date.fromisoformat(m.group(1))
        except ValueError:
            pass
    return None


def format_an_fast_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return f"{parsed.day} {MONTH_NAMES[parsed.month]}"
    except Exception:
        return text[:10]


def reformat_dates(text: str) -> str:
    def _sub(m: re.Match) -> str:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= mo <= 12:
            return f"{d} {MONTH_NAMES[mo]} {y}"
        return m.group(0)
    return re.sub(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", _sub, text)


def clean_markdown_cell(value: str) -> str:
    return normalise_space(re.sub(r"<[^>]+>", "", str(value or "")))


def markdown_cell(value: object, limit: int = 180) -> str:
    text = normalise_space(str(value or ""))
    if len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "..."
    return text.replace("|", "/")


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return ""
    header = "| " + " | ".join(markdown_cell(item, 80) for item in headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(markdown_cell(value) for value in row) + " |"
        for row in rows
    ]
    return "\n".join([header, divider, *body])
