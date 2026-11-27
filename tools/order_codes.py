#!/usr/bin/env python3

from __future__ import annotations

import re
from dataclasses import dataclass

CODE_ORDER: tuple[str, ...] = ("NMO", "OO", "PSO", "CAO", "SIO")

ORDER_LABELS = {
    "NMO": "Non-Molestation Order",
    "PSO": "Prohibited Steps Order",
    "CAO": "Child Arrangements Order",
    "OO": "Occupation Order",
    "SIO": "Specific Issue Order",
}

_ABBREVIATIONS = {
    "nmo": "NMO", "oo": "OO", "pso": "PSO", "cao": "CAO", "sio": "SIO",
    "fl401": "FL401", "c100": "C100", "c1a": "C100",
    "fl404": "NMO", "fl404a": "NMO", "fl404b": "NMO",
}

_VOCAB = {
    "non": "non", "mol": "mol", "step": "steps", "steps": "steps", "issue": "issue", "issues": "issue",
    "child": "child", "order": "order", "orders": "order", "fl": "fl", "401": "401",
    "molestation": "molestation", "nonmolestation": "nonmolestation", "occupation": "occupation",
    "prohibited": "prohibited", "specific": "specific", "children": "child",
    "arrangements": "arrangements", "arrangement": "arrangements", "contact": "contact",
}

_PHRASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("non", "molestation"), "NMO"),
    (("nonmolestation",), "NMO"),
    (("non", "mol"), "NMO"),
    (("prohibited", "steps"), "PSO"),
    (("specific", "issue"), "SIO"),
    (("child", "arrangements"), "CAO"),
    (("contact", "order"), "CAO"),
    (("occupation", "order"), "OO"),
    (("fl", "401"), "FL401"),
)

_FILLER = {"order", "the", "a", "an", "of"}
_SPLIT = re.compile(r"\s*(?:&|\+|/|,|;|\band\b)\s*", re.IGNORECASE)
MISSING_WORDS: frozenset[str] = frozenset({"unknown", "na", "none", "tbc", "not stated"})
_DOTTED = re.compile(r"(?:\b[a-z]\.){2,}")
_NON_MOLESTATION = re.compile(r"(?<![A-Za-z0-9])(non)[\s‐-–-]*(molestation)(?![A-Za-z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class OrderResult:
    codes: tuple[str, ...] = ()
    unrecognised: tuple[str, ...] = ()
    empty: bool = False
    fl401_form: bool = False
    children_form: bool = False

    @property
    def status(self) -> str:
        if self.empty:
            return "empty"
        if self.unrecognised:
            return "partial" if (self.codes or self.children_form) else "unrecognised"
        if not self.codes and not self.children_form:
            return "unrecognised"
        return "ok"

    @property
    def needs_human(self) -> bool:
        return self.status != "ok" or (self.children_form and not self.codes)


def _damerau(a: str, b: str) -> int:
    rows = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        rows[i][0] = i
    for j in range(len(b) + 1):
        rows[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            rows[i][j] = min(rows[i - 1][j] + 1, rows[i][j - 1] + 1, rows[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                rows[i][j] = min(rows[i][j], rows[i - 2][j - 2] + 1)
    return rows[len(a)][len(b)]


def _canon(token: str) -> str | None:
    if token in _ABBREVIATIONS:
        return None
    if token in _VOCAB:
        return _VOCAB[token]
    limit = 1 if 6 <= len(token) <= 8 else 2 if len(token) >= 9 else 0
    if not limit:
        return None
    best: dict[str, int] = {}
    for word, canon in _VOCAB.items():
        if len(word) < 6:
            continue
        distance = _damerau(token, word)
        if distance <= limit:
            best[canon] = min(best.get(canon, 9), distance)
    if not best:
        return None
    low = min(best.values())
    closest = [c for c, d in best.items() if d == low]
    return closest[0] if len(closest) == 1 else None


def _normalise(segment: str) -> list[str]:
    text = segment.lower()
    text = _DOTTED.sub(lambda m: m.group().replace(".", ""), text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.split()


def _read_segment(raw: str) -> tuple[list[str], list[str], bool, bool]:
    tokens = _normalise(raw)
    codes: list[str] = []
    unread: list[str] = []
    fl401 = children = False
    run: list[str] = []

    def flush() -> None:
        words = list(run)
        while words and words[0] in _FILLER:
            words.pop(0)
        while words and words[-1] in _FILLER:
            words.pop()
        if words:
            unread.append(" ".join(words))
        run.clear()

    canon = [(_ABBREVIATIONS.get(t), None if t in _ABBREVIATIONS else _canon(t)) for t in tokens]
    i = 0
    while i < len(tokens):
        abbreviation, word = canon[i]
        if abbreviation:
            flush()
            if abbreviation == "C100":
                children = True
            else:
                codes.append("NMO" if abbreviation == "FL401" else abbreviation)
                fl401 = fl401 or abbreviation == "FL401"
                if tokens[i] == "fl404b" and tokens[i + 1:i + 2] == ["occupation"]:
                    codes.append("OO")
                    i += 1
            i += 1
            continue
        matched = False
        for phrase, code in _PHRASES:
            n = len(phrase)
            window = [c[1] for c in canon[i:i + n]]
            if len(window) == n and tuple(window) == phrase:
                flush()
                codes.append("NMO" if code == "FL401" else code)
                fl401 = fl401 or code == "FL401"
                i += n
                matched = True
                break
        if matched:
            continue
        run.append(tokens[i])
        i += 1
    flush()
    if not codes and not unread and not children and tokens:
        unread.append(" ".join(tokens))
    return codes, unread, fl401, children


def resolve_order_text(text: object) -> OrderResult:
    raw = "" if text is None else str(text)
    if not raw.strip():
        return OrderResult(empty=True)
    raw = re.sub(r"\bn\s*/\s*a\b", "na", raw, flags=re.IGNORECASE)
    codes: set[str] = set()
    unread: list[str] = []
    fl401 = children = False
    for segment in _SPLIT.split(raw):
        if not segment.strip() or " ".join(_normalise(segment)) in MISSING_WORDS:
            continue
        seg_codes, seg_unread, seg_fl401, seg_children = _read_segment(segment)
        codes.update(seg_codes)
        unread.extend(u[:80] for u in seg_unread)
        fl401 = fl401 or seg_fl401
        children = children or seg_children
    if not codes and not unread and not children:
        return OrderResult(empty=True)
    seen: list[str] = []
    for phrase in unread:
        if phrase not in seen:
            seen.append(phrase)
    return OrderResult(
        codes=tuple(c for c in CODE_ORDER if c in codes),
        unrecognised=tuple(seen),
        fl401_form=fl401,
        children_form=children,
    )


def codes_in_text(text: object) -> tuple[str, ...]:
    return resolve_order_text(text).codes


def hyphenate_non_molestation(text: str) -> str:
    return _NON_MOLESTATION.sub(lambda m: m.group(1) + "-" + m.group(2), text)


FILENAME_TOKEN_GROUPS: dict[str, tuple[frozenset, ...]] = {
    "NMO": (frozenset({"nmo"}), frozenset({"non", "molestation"})),
    "PSO": (frozenset({"pso"}), frozenset({"prohibited", "steps"})),
    "CAO": (frozenset({"cao"}), frozenset({"child", "arrangements"})),
    "OO": (frozenset({"occupation", "order"}), frozenset({"draft", "oo"})),
    "SIO": (frozenset({"sio"}), frozenset({"specific", "issue"})),
}



_NAME_PATTERNS = (
    (r"non[- ]?mol(?:estation)?", "NMO"), (r"occupation", "OO"), (r"child(?:ren)?(?:'s)? arrang\w*", "CAO"),
    (r"prohibited steps", "PSO"), (r"specific issues?", "SIO"),
)
_COMBINED = re.compile(r"\bnon[- ]?mol(?:estation)?(?: orders?)?\s*(and|&)\s*occupation orders?\b", re.I)
_SINGLE = [(re.compile(rf"\b{pat}\s+order(s?)\b", re.I), abbr) for pat, abbr in _NAME_PATTERNS]
_ARTICLE = re.compile(r"\b([Aa])\s+(NMO|OO|SIO)\b")


def abbreviate_order_names(text: str) -> str:
    text = _COMBINED.sub(lambda m: f"NMO {m.group(1)} OO", text)
    for rx, abbr in _SINGLE:
        text = rx.sub(lambda m, a=abbr: f"{a}s" if m.group(1) else a, text)
    text = re.sub(r"\b(nmo|oo|cao|pso|sio)(s?)\b", lambda m: m.group(1).upper() + m.group(2).lower(), text, flags=re.I)
    return _ARTICLE.sub(lambda m: ("An" if m.group(1) == "A" else "an") + " " + m.group(2), text)
