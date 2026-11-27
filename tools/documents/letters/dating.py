from __future__ import annotations

import calendar
import datetime as dt
from typing import Iterable

OPENING, COURT_OUTCOME, CLOSING = "opening", "court-outcome", "closing"
WEEK_DAYS = 7
MAX_NOTE_GAP_MONTHS = 6


def add_months(value: dt.date, months: int) -> dt.date:
    index = value.month - 1 + months
    year, month = value.year + index // 12, index % 12 + 1
    return dt.date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def closing_anchor(last_order: dt.date | None, notes: Iterable[dt.date] = ()) -> dt.date | None:
    ordered = sorted(set(notes))
    if last_order is None:
        if not ordered:
            return None
        anchor, ordered = ordered[0], ordered[1:]
    else:
        anchor = last_order
    for note in ordered:
        if note <= anchor:
            continue
        if note > add_months(anchor, MAX_NOTE_GAP_MONTHS):
            break
        anchor = note
    return anchor


def latest_allowed(kind: str, *, arrival: dt.date | None = None, hearing: dt.date | None = None,
                   last_order: dt.date | None = None, notes: Iterable[dt.date] = ()) -> dt.date | None:
    if kind == OPENING:
        return arrival + dt.timedelta(days=WEEK_DAYS) if arrival else None
    if kind == COURT_OUTCOME:
        return hearing + dt.timedelta(days=WEEK_DAYS) if hearing else None
    if kind == CLOSING:
        anchor = closing_anchor(last_order or hearing, notes)
        return add_months(anchor, 1) if anchor else None
    raise ValueError(f"Unknown letter kind {kind!r}.")


def letter_date(kind: str, today: dt.date, **anchors) -> tuple[dt.date, dt.date | None]:
    cap = latest_allowed(kind, **anchors)
    return (min(today, cap) if cap else today), cap
