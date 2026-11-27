from __future__ import annotations

import re
from typing import Iterable, Pattern

from documents.letters.checks import LintResultLike


CLOSING_TITLE_RE = re.compile(r"^end of matter:", re.IGNORECASE)
CLOSING_BOILERPLATE_RE = re.compile(
    r"your matter has now concluded and our retainer", re.IGNORECASE
)
ORIGINAL_DOCS_RE = re.compile(
    r"it is our practice to return a client[’']?s original documents", re.IGNORECASE
)


COURT_OUTCOME_TITLE_RE = re.compile(r"^court outcome:", re.IGNORECASE)
MID_BOILERPLATE_RE = re.compile(
    r"this letter is to update you on the outcome of the hearing", re.IGNORECASE
)


OPENING_SECTION_RES: tuple[Pattern[str], ...] = (
    re.compile(r"^your instructions$", re.IGNORECASE),
    re.compile(r"^our advice$", re.IGNORECASE),
    re.compile(r"^your matter with us$", re.IGNORECASE),
    re.compile(r"^(?:fees & costs|fees and costs)$", re.IGNORECASE),
    re.compile(r"^complaints procedure$", re.IGNORECASE),
    re.compile(r"^your responsibilities$", re.IGNORECASE),
    re.compile(r"^supervision of your matter$", re.IGNORECASE),
)

SIGNALS: dict[str, tuple[Pattern[str], ...]] = {
    "opening": OPENING_SECTION_RES,
    "closing": (CLOSING_TITLE_RE, CLOSING_BOILERPLATE_RE, ORIGINAL_DOCS_RE),
    "court-outcome": (COURT_OUTCOME_TITLE_RE, MID_BOILERPLATE_RE),
}

MIN_SIGNALS: dict[str, int] = {"opening": 2, "closing": 1, "court-outcome": 1}

LABELS: dict[str, str] = {
    "opening": "opening (client care) letter",
    "closing": "closing (end of matter) letter",
    "court-outcome": "Court Outcome (mid-matter) letter",
}

FILENAME_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "opening": {
        "any": ("care letter", "ccl", "client care", "opening letter"),
        "also_any": (),
        "none": ("closing", "court outcome", "end of matter"),
    },
    "closing": {
        "any": ("closing",),
        "also_any": ("care letter", "ccl"),
        "none": ("court outcome",),
    },
    "court-outcome": {
        "any": ("court outcome",),
        "also_any": ("care letter", "ccl"),
        "none": (),
    },
}

ALIASES: dict[str, str] = {
    "mid": "court-outcome",
    "court_outcome": "court-outcome",
    "courtoutcome": "court-outcome",
    "outcome": "court-outcome",
    "ccl": "opening",
    "open": "opening",
    "close": "closing",
    "end-of-matter": "closing",
}

KINDS: tuple[str, ...] = ("opening", "closing", "court-outcome")


def resolve(raw: str) -> str:
    key = str(raw or "").strip().lower()
    key = ALIASES.get(key, key)
    if key not in KINDS:
        raise ValueError(f"Unknown letter kind {raw!r}. Known: {', '.join(KINDS)}")
    return key


_SEPARATORS_RE = re.compile(r"[-_.]+")


def normalise_filename(name: str) -> str:
    return _SEPARATORS_RE.sub(" ", name.lower())


def match_filename(kind: str, name: str) -> bool:
    rules = FILENAME_RULES[resolve(kind)]
    lowered = normalise_filename(name)
    if any(word in lowered for word in rules["none"]):
        return False
    if not any(word in lowered for word in rules["any"]):
        return False
    also = rules["also_any"]
    return not also or any(word in lowered for word in also)


def count_signals(kind: str, texts: Iterable[str]) -> int:
    collected = list(texts)
    return sum(
        1 for pattern in SIGNALS[resolve(kind)] if any(pattern.search(t) for t in collected)
    )


def detect(texts: Iterable[str]) -> set[str]:
    collected = list(texts)
    return {
        kind for kind in KINDS if count_signals(kind, collected) >= MIN_SIGNALS[kind]
    }


def check_declared_kind(
    texts: Iterable[str],
    kind: str,
    result: LintResultLike,
    *,
    location: str = "",
) -> bool:
    kind = resolve(kind)
    detected = detect(texts)
    if not detected:
        result.add(
            "L001",
            "warning",
            f"Could not confirm this is {LABELS[kind]} — none of the fixed template "
            "wording for any known letter type was found. Linting continued as "
            "asked, but check this is the letter you meant, and that flatten/fill "
            "has not stripped the template's fixed text.",
            location,
        )
        return True
    if kind in detected:
        return True
    others = ", ".join(LABELS[k] for k in sorted(detected))
    result.add(
        "L000",
        "error",
        f"Wrong letter type: {kind} checks were requested, but this document's "
        f"fixed template wording identifies it as {others}. No {kind} checks were "
        "run — they would report missing sections this template does not have, and "
        f"would skip the checks {others} actually needs. Re-run with the correct "
        "letter kind.",
        location,
    )
    return False
