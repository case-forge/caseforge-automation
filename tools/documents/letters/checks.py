from __future__ import annotations

import calendar
import datetime as dt
from london_time import london_today
import json
import re
from typing import Any, Protocol


HEADER_DATE_RE = re.compile(
    r"\bDate:\s*([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+[0-9]{4}|"
    r"[0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
    re.IGNORECASE,
)

_HEADER_DATE_FORMATS = (
    "%d %B %Y",
    "%d %b %Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%d.%m.%y",
    "%d-%m-%y",
)


class LintResultLike(Protocol):

    def add(self, code: str, severity: str, message: str, location: str = "") -> None: ...

    def passed(self) -> bool: ...

    def to_dict(self) -> dict[str, Any]: ...

    @property
    def path(self) -> str: ...

    @property
    def issues(self) -> list: ...

    @property
    def errors(self) -> int: ...

    @property
    def warnings(self) -> int: ...


def parse_header_date(value: str) -> dt.date | None:
    clean = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", str(value or ""), flags=re.IGNORECASE).strip()
    for fmt in _HEADER_DATE_FORMATS:
        try:
            return dt.datetime.strptime(clean, fmt).date()
        except ValueError:
            continue
    return None


def check_run_fonts_explicit(doc, result: LintResultLike, *, code: str) -> None:
    for para in doc.paragraphs:
        for run in para.runs:
            if not run.text.strip():
                continue
            if run.font.name is None or run.font.size is None:
                result.add(
                    code, "error",
                    "Run has no explicit font/size set — it will render in Word's default "
                    "theme font instead of matching the rest of the letter. Copy the "
                    "font/size (and bold, if applicable) from an adjacent run rather than "
                    "leaving it unset.",
                    run.text[:80],
                )


def add_one_month(value: dt.date) -> dt.date:
    if value.month == 12:
        year, month = value.year + 1, 1
    else:
        year, month = value.year, value.month + 1
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(value.day, last_day))


def check_header_date_current(
    texts: list[str],
    result: LintResultLike,
    *,
    code: str,
    label: str,
    final_hearing_date: dt.date | None = None,
    cap_days: int | None = None,
) -> None:
    today = london_today()
    saw_date_label = False
    for text in texts[:25]:
        if "date:" not in text.lower():
            continue
        saw_date_label = True
        match = HEADER_DATE_RE.search(text)
        if not match:
            continue
        parsed = parse_header_date(match.group(1))
        if parsed is None:
            result.add(code, "warning", f"Could not parse the {label.lower()} header date.", text[:100])
            return
        if final_hearing_date is not None:
            cap = final_hearing_date + dt.timedelta(days=cap_days) if cap_days else add_one_month(final_hearing_date)
            if parsed > today:
                result.add(
                    code, "error",
                    f"{label} header date is {parsed.isoformat()}, which is after today "
                    f"({today.isoformat()}). A closing letter may be dated earlier than the day "
                    "it is drafted, never later.",
                    text[:100],
                )
            elif not (final_hearing_date <= parsed <= cap):
                result.add(
                    code, "error",
                    f"{label} header date is {parsed.isoformat()}, outside the allowed "
                    f"{final_hearing_date.isoformat()}-{cap.isoformat()} range (final hearing "
                    "date, capped one month later).",
                    text[:100],
                )
        elif parsed != today:
            result.add(
                code, "error",
                f"{label} header date is {parsed.isoformat()}, not today's date "
                f"{today.isoformat()}.",
                text[:100],
            )
        return
    if saw_date_label:
        result.add(code, "error", f"{label} header has a Date label but no populated date.")
    else:
        result.add(code, "error", f"{label} header date was not found.")


def print_result(result: LintResultLike, *, use_json: bool) -> None:
    if use_json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return

    status = "PASS" if result.passed() else "FAIL"
    print(f"\n[{status}] {result.path}")
    if not result.issues:
        print("  No issues found.")
        return
    for issue in result.issues:
        prefix = {"error": "  ✖ ", "warning": "  ⚠ ", "info": "  ℹ "}.get(issue.severity, "  ? ")
        print(f"{prefix}[{issue.code}] {issue.message}")
        if issue.location:
            print(f"       └─ near: {issue.location!r}")
    print(f"\n  {result.errors} error(s), {result.warnings} warning(s)")
