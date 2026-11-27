#!/usr/bin/env python3
from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import word_lists


MAX_DISTANCE = 2
_WORD_RE = re.compile(r"^[a-z]+(?:['’][a-z]+)?$")
_warned_missing = False


def _us_uk_words() -> tuple[frozenset[str], frozenset[str]]:
    global _warned_missing
    gaps = word_lists.missing()
    if gaps and not _warned_missing:
        _warned_missing = True
        logging.getLogger(__name__).error(
            "spelling_autofix: US-to-UK fixes DISABLED, system word list missing: %s (install wbritish and wamerican)",
            ", ".join(gaps),
        )
    return word_lists.american(), word_lists.british()


@dataclass(frozen=True)
class SpellingEdit:
    start: int
    end: int
    original: str
    replacement: str
    applied: bool
    reason: str = ""


def osa_distance(a: str, b: str) -> int:
    la, lb = len(a), len(b)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


def _is_adjacent_swap(a: str, b: str) -> bool:
    return len(a) == len(b) and osa_distance(a, b) == 1 and sorted(a) == sorted(b)


def choose_replacement(word: str, suggestions: Iterable[str]) -> tuple[str, str]:
    lowered = word.lower()
    scored = []
    for candidate in suggestions:
        if not _WORD_RE.match(candidate.lower()):
            continue
        distance = osa_distance(lowered, candidate.lower())
        if distance <= MAX_DISTANCE:
            scored.append((distance, candidate))
    if not scored:
        return "", "no close suggestion"
    best = min(distance for distance, _ in scored)
    closest = [candidate for distance, candidate in scored if distance == best]
    if len(closest) == 1:
        return closest[0], ""
    swaps = [candidate for candidate in closest if _is_adjacent_swap(lowered, candidate.lower())]
    if len(swaps) == 1:
        return swaps[0], ""
    us_words, uk_words = _us_uk_words()
    if lowered in us_words and lowered not in uk_words:
        uk_only = [c for c in closest if c.lower() in uk_words and c.lower() not in us_words]
        if len(uk_only) == 1:
            return uk_only[0], ""
    return "", "ambiguous: " + ", ".join(closest[:4])
