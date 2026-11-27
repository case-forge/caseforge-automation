#!/usr/bin/env python3

from __future__ import annotations

import re

COURT_TO_CONFIRM = "[COURT TO BE CONFIRMED]"

COURT_TYPE_SUFFIXES = (
    "magistrates' court and family court",
    "magistrates court and family court",
    "magistrates’ court and family court",
    "county court and family court",
    "county and family court",
    "civil and family justice centre",
    "civil justice centre",
    "civil and family courts centre",
    "civil and family court",
    "crown and county court",
    "combined court centre",
    "magistrates' court",
    "magistrates court",
    "magistrates’ court",
    "combined court",
    "justice centre",
    "law courts",
    "county court",
    "family court",
    "civil",
)

_MAGISTRATES_RE = re.compile(r"(?i)\bmagistrate(?:s['’]?|['’]s)?\b")


def is_magistrates(name: str) -> bool:
    return bool(_MAGISTRATES_RE.search(str(name or "")))


MFC_TAIL_RE = re.compile(r"(?i)\s+magistrates?['’]?s?['’]?\s+court\s+and(?:\s+(?:the\s+)?family\s+court)?\s*$")


def is_pure_magistrates(name: str) -> bool:
    text = str(name or "")
    return is_magistrates(text) and not re.search(r"(?i)\bfamily\s+court", text) and not MFC_TAIL_RE.search(text)


def family_court_place(name: str) -> str | None:
    return COURT_TO_CONFIRM if is_pure_magistrates(re.sub(r"\s+", " ", str(name or "")).strip()) else None


def printable_court(name: str) -> str:
    mapped = family_court_place(name)
    if mapped is None and re.fullmatch(r"(?i)\s*(?:the\s+)?central\s*", str(name or "")):
        return "Central Family Court"
    return str(name or "") if mapped is None else mapped
