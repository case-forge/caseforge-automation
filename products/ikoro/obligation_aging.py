#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence


OBLIGATION_TYPES: dict[str, str] = {
    "send_to_client": "Send order to client",
    "book_counsel": "Counsel booked",
    "arrange_service": "Service / process server / SOS",
    "prepare_bundle": "Bundle prepared",
    "amend_draft_order": "Amend & resubmit draft order to court",
}

OBLIGATION_THRESHOLDS: dict[str, dict[str, int]] = {
    "send_to_client": {"max_calendar_days": 2},
    "book_counsel": {"max_working_days": 2, "hearing_within_wd": 10},
    "arrange_service": {"max_working_days": 3},
    "prepare_bundle": {"hearing_within_wd": 10},
    "amend_draft_order": {"max_working_days": 2},
}

RED_AGE_MULTIPLIER = 2
RED_HEARING_WD = 3

BANK_HOLIDAYS: set[dt.date] = {
    dt.date(2026, 1, 1),
    dt.date(2026, 4, 3),
    dt.date(2026, 4, 6),
    dt.date(2026, 5, 4),
    dt.date(2026, 5, 25),
    dt.date(2026, 8, 31),
    dt.date(2026, 12, 25),
    dt.date(2026, 12, 28),
    dt.date(2027, 1, 1),
    dt.date(2027, 3, 26),
    dt.date(2027, 3, 29),
    dt.date(2027, 5, 3),
    dt.date(2027, 5, 31),
    dt.date(2027, 8, 30),
    dt.date(2027, 12, 27),
    dt.date(2027, 12, 28),
}

_NONE_TOKENS = {"", "none", "n/a", "na", "tbc", "-", "unknown", "no order", "none yet"}
_DATE_RE = re.compile(
    r"(?P<d>\d{1,2})[/.\-](?P<m>\d{1,2})[/.\-](?P<y>\d{2,4})"
    r"|(?P<iso>\d{4}-\d{2}-\d{2})"
)
_SPLIT_RE = re.compile(r"[,;|/]+")


def is_working_day(day: dt.date, holidays: Optional[set[dt.date]] = None) -> bool:
    holidays = BANK_HOLIDAYS if holidays is None else holidays
    return day.weekday() < 5 and day not in holidays


def working_days_between(
    start: dt.date, end: dt.date, holidays: Optional[set[dt.date]] = None
) -> int:
    if end == start:
        return 0
    sign = 1 if end > start else -1
    lo, hi = (start, end) if end > start else (end, start)
    cursor = lo
    count = 0
    while cursor < hi:
        cursor += dt.timedelta(days=1)
        if is_working_day(cursor, holidays):
            count += 1
    return sign * count


def working_days_since(start: dt.date, now: dt.date) -> int:
    return working_days_between(start, now)


def working_days_until(now: dt.date, target: dt.date) -> int:
    return working_days_between(now, target)


def parse_date(text: Any) -> Optional[dt.date]:
    if not text:
        return None
    if isinstance(text, dt.datetime):
        return text.date()
    if isinstance(text, dt.date):
        return text
    m = _DATE_RE.search(str(text))
    if not m:
        return None
    if m.group("iso"):
        try:
            return dt.date.fromisoformat(m.group("iso"))
        except ValueError:
            return None
    day, month, year = int(m.group("d")), int(m.group("m")), int(m.group("y"))
    if year < 100:
        year += 2000
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _is_none_text(text: Any) -> bool:
    return str(text or "").strip().lower() in _NONE_TOKENS


def parse_open_obligations(awaiting_next_step: Any) -> list[str]:
    raw = str(awaiting_next_step or "")
    found: list[str] = []
    for piece in _SPLIT_RE.split(raw):
        token = piece.strip().lower().replace(" ", "_").replace("-", "_")
        if token in OBLIGATION_TYPES and token not in found:
            found.append(token)
    return found


def parse_hearing(next_hearing_text: Any) -> tuple[Optional[dt.date], str]:
    raw = str(next_hearing_text or "").strip()
    if not raw:
        return None, ""
    court = ""
    if "|" in raw:
        left, _, right = raw.partition("|")
        court = right.strip()
        date = parse_date(left)
        if date is None:
            date = parse_date(raw)
        return date, court
    date = parse_date(raw)
    if date is not None:
        remainder = _DATE_RE.sub("", raw).strip(" -,|")
        court = remainder
    return date, court


def _clock_start(row: Mapping[str, Any]) -> Optional[dt.date]:
    order_date = None if _is_none_text(row.get("order_status")) else parse_date(row.get("order_status"))
    return (
        order_date
        or parse_date(row.get("status_changed_at"))
        or parse_date(row.get("last_material_email_received"))
    )


def _urgency_for(
    obligation: str,
    age_wd: Optional[int],
    hearing_wd: Optional[int],
    thresholds: Mapping[str, Mapping[str, int]],
    age_days: Optional[int] = None,
) -> tuple[str, str]:
    rule = thresholds.get(obligation, {})
    max_wd = rule.get("max_working_days")
    hearing_trigger = rule.get("hearing_within_wd")

    reasons: list[str] = []
    urgency = "green"

    if hearing_trigger is not None and hearing_wd is not None:
        if hearing_wd <= RED_HEARING_WD:
            urgency = "red"
            reasons.append(
                f"hearing {'passed' if hearing_wd < 0 else f'in {hearing_wd}wd'}"
            )
        elif hearing_wd <= hearing_trigger:
            urgency = _escalate(urgency, "amber")
            reasons.append(f"hearing in {hearing_wd}wd (≤{hearing_trigger})")

    max_cd = rule.get("max_calendar_days")
    if max_cd is not None and age_days is not None:
        if age_days >= max_cd * RED_AGE_MULTIPLIER:
            urgency = "red"
            reasons.append(f"open {age_days} days (≥{max_cd * RED_AGE_MULTIPLIER})")
        elif age_days > max_cd:
            urgency = _escalate(urgency, "amber")
            reasons.append(f"open {age_days} days (>{max_cd})")
    elif max_wd is not None and age_wd is not None:
        if age_wd >= max_wd * RED_AGE_MULTIPLIER:
            urgency = "red"
            reasons.append(f"open {age_wd}wd (≥{max_wd * RED_AGE_MULTIPLIER})")
        elif age_wd > max_wd:
            urgency = _escalate(urgency, "amber")
            reasons.append(f"open {age_wd}wd (>{max_wd})")

    if not reasons:
        reasons.append("within SLA")
    return urgency, "; ".join(reasons)


_SEV = {"green": 0, "amber": 1, "red": 2}


def _escalate(current: str, candidate: str) -> str:
    return candidate if _SEV[candidate] > _SEV[current] else current


def compute_obligations(
    rows: Iterable[Mapping[str, Any]],
    now: dt.datetime | dt.date,
    *,
    thresholds: Optional[Mapping[str, Mapping[str, int]]] = None,
) -> list[dict[str, Any]]:
    thresholds = OBLIGATION_THRESHOLDS if thresholds is None else thresholds
    today = now.date() if isinstance(now, dt.datetime) else now

    out: list[dict[str, Any]] = []
    for row in rows:
        open_tokens = parse_open_obligations(row.get("awaiting_next_step"))
        if not open_tokens:
            continue
        hearing_date, court = parse_hearing(row.get("next_hearing_text"))
        hearing_wd = working_days_until(today, hearing_date) if hearing_date else None
        start = _clock_start(row)
        age_wd = working_days_since(start, today) if start else None
        age_days = (today - start).days if start else None

        for token in open_tokens:
            if token == "arrange_service":
                svc = str(row.get("service_status") or "").lower()
                if "return" in svc or "complete" in svc or "served" in svc:
                    continue
            urgency, reason = _urgency_for(token, age_wd, hearing_wd, thresholds, age_days)
            out.append(
                {
                    "matter_id": row.get("matter_id"),
                    "matter_ref": str(row.get("matter_ref") or row.get("matter_id") or ""),
                    "client": str(row.get("client") or ""),
                    "order_type": str(row.get("order_type") or row.get("order_status") or ""),
                    "has_c8": bool(row.get("has_c8")),
                    "obligation": token,
                    "label": OBLIGATION_TYPES[token],
                    "done": False,
                    "age_working_days": age_wd,
                    "hearing_date": hearing_date.isoformat() if hearing_date else "",
                    "hearing_working_days": hearing_wd,
                    "court": court,
                    "urgency": urgency,
                    "reason": reason,
                }
            )

    out.sort(
        key=lambda ob: (
            -_SEV[ob["urgency"]],
            -(ob["age_working_days"] if ob["age_working_days"] is not None else -1),
        )
    )
    return out


def overdue_obligations(obligations: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(ob) for ob in obligations if ob.get("urgency") in {"amber", "red"}]


def pii_safe_alert_text(ob: Mapping[str, Any]) -> str:
    ref = str(ob.get("matter_ref") or "matter")
    label = str(ob.get("label") or ob.get("obligation") or "obligation")
    age = ob.get("age_working_days")
    age_txt = f"{age}wd open" if isinstance(age, int) else "age unknown"
    bits = [f"[{ob.get('urgency', '').upper()}] {ref}: {label} outstanding ({age_txt})"]
    if ob.get("hearing_date"):
        hw = ob.get("hearing_working_days")
        when = f" — hearing {ob['hearing_date']}"
        if isinstance(hw, int):
            when += f" ({hw}wd)"
        if ob.get("court"):
            when += f", {ob['court']}"
        bits.append(when)
    return "".join(bits)


def select_pushable(
    overdue: Sequence[Mapping[str, Any]],
    acks: Iterable[str],
    key: Callable[[Mapping[str, Any]], str],
) -> tuple[list[Mapping[str, Any]], set[str]]:
    acked = set(acks)
    to_push = [ob for ob in overdue if key(ob) not in acked]
    keep = {key(ob) for ob in overdue}
    return to_push, keep
