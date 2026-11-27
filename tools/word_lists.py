
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

DICT_DIR = Path("/usr/share/dict")
BRITISH_PATH = DICT_DIR / "british-english"
AMERICAN_PATH = DICT_DIR / "american-english"
GENERIC_PATH = DICT_DIR / "words"
OVERRIDE_ENV = "AMEND_EVAL_DICT"


def _read(path: Path) -> frozenset[str] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    return frozenset(w.strip().lower() for w in text.splitlines() if w.strip())


@lru_cache(maxsize=None)
def _british_cached(override: str, generic: bool) -> frozenset[str] | None:
    candidates = [Path(override)] if override else []
    candidates.append(BRITISH_PATH)
    if generic:
        candidates.append(GENERIC_PATH)
    for candidate in candidates:
        if candidate.is_file():
            words = _read(candidate)
            if words is not None:
                return words
    return None


@lru_cache(maxsize=None)
def _american_cached() -> frozenset[str] | None:
    return _read(AMERICAN_PATH)


def british(override: str = "", generic_fallback: bool = False) -> frozenset[str]:
    return _british_cached(override, generic_fallback) or frozenset()


def american() -> frozenset[str]:
    return _american_cached() or frozenset()


def combined() -> frozenset[str]:
    return british() | american()


def missing() -> list[str]:
    out = []
    if _british_cached("", False) is None:
        out.append("british")
    if _american_cached() is None:
        out.append("american")
    return out


@lru_cache(maxsize=None)
def _lowercase_only_cached() -> frozenset[str]:
    for path in (BRITISH_PATH, AMERICAN_PATH):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        return frozenset(w.strip() for w in text.splitlines() if w.strip().isalpha() and w.strip().islower())
    return frozenset()


def lowercase_only() -> frozenset[str]:
    return _lowercase_only_cached()


def reset_cache() -> None:
    _british_cached.cache_clear()
    _american_cached.cache_clear()
    _lowercase_only_cached.cache_clear()
