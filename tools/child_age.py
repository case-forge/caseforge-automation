#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
from london_time import london_today
import re

_DOB_GROUP = re.compile(r"\((\d{4}-\d{2}-\d{2})(?:,\s*age\s+\d+)?\)")


def age_on(dob_iso: str, as_of: dt.date | None = None) -> int | None:
    try:
        born = dt.date.fromisoformat(str(dob_iso).strip()[:10])
    except ValueError:
        return None
    today = as_of or london_today()
    if born > today:
        return None
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def with_live_ages(summary: str, as_of: dt.date | None = None) -> str:

    def _replace(match: re.Match[str]) -> str:
        dob = match.group(1)
        age = age_on(dob, as_of)
        return f"({dob}, age {age})" if age is not None else f"({dob})"

    return _DOB_GROUP.sub(_replace, summary)


def strip_ages(summary: str) -> str:
    return _DOB_GROUP.sub(lambda m: f"({m.group(1)})", summary)
