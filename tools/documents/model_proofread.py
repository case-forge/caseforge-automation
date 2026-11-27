#!/usr/bin/env python3
from __future__ import annotations

import difflib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import model_backend
from documents import spelling_autofix as sa
from documents import statement_proofread as sp

ROLE = model_backend.ROLE_SPELLING_TIEBREAK
SECOND_ROLE = model_backend.ROLE_SPELLING_SECOND
MIN_WORDS = 4
MAX_FIXES_PER_PARAGRAPH = 8
MAX_WORD_DRIFT = 3
MAX_CHAR_RATIO = 0.08

FUNCTION_WORDS = frozenset(
    "a an the of to in on at for by with from and but or that which who he she it they i we you me him her them us "
    "my our his their your is are was were am be been being had has have do does did".split()
)
PRONOUNS = frozenset("he she it they i we you me him her them us".split())
_QUOTED_RE = re.compile(r"“[^”]*”|\"[^\"]*\"")
_TERMINATOR_RE = re.compile(r"[.?!]")
_OTHER_PUNCT_RE = re.compile(r"[^\w\s,.'’]")

SYSTEM = (
    "You are a meticulous proofreader for a UK family-law firm, British English. You are given ONE paragraph "
    "from a client's own witness statement. Correct ONLY spelling, punctuation and grammar slips: typos, a "
    "missing apostrophe, a doubled word, a missing small word that the sentence makes obvious (he, she, it, "
    "the, to, of), wrong capitalisation, a missing full stop. NEVER add, remove or change a fact, a date, a "
    "number, a name, a place, a quoted word, or the order of events. NEVER rewrite for style: do not add a comma for rhythm or readability, and leave informal wording, run-on sentences and comma splices exactly as the client wrote them; correct a comma only when it is plainly a slip (doubled, misplaced, or with a space before it). Words like "
    "PERSON_A, PLACE_B, DATE_C, NUMBER_D are placeholders: keep them exactly. If a slip cannot be fixed "
    "without guessing (a missing noun, a garbled sentence), leave that text exactly as written. If nothing "
    "needs fixing, return the paragraph unchanged. Reply with ONLY a JSON object: "
    '{"corrected": "<the whole paragraph>"}. No prose, no fences.'
)


@dataclass(frozen=True)
class Edit:

    para: int
    label: str
    start: int
    end: int
    original: str
    replacement: str
    applied: bool
    reason: str = ""
    before: str = ""
    after: str = ""


@dataclass
class Result:
    edits: list[Edit] = field(default_factory=list)
    checked: bool = True
    failures: int = 0
    paragraphs: int = 0


RUNNER_TRIES = 3
RUNNER_PAUSE_S = 2.0


def default_runner(system: str, prompt: str) -> str | None:
    for attempt in range(RUNNER_TRIES):
        try:
            result = model_backend.run_model(
                ROLE,
                prompt,
                model=model_backend.model_for_role(ROLE, backend="openrouter"),
                backend="openrouter",
                system_prompt=system,
                timeout=90,
                reasoning="low",
                max_tokens=6000,
                route_reason="statement-model-proofread",
            )
        except Exception:
            result = None
        if result is not None and result.ok:
            return result.text
        if attempt + 1 < RUNNER_TRIES:
            time.sleep(RUNNER_PAUSE_S * (attempt + 1))
    return None


SECOND_SYSTEM = SYSTEM + (
    " A first proofreader has already read this paragraph. The notes below its text list the places it suggested a "
    "change for that a machine guard refused, with the guard's reason, or say it gave no usable answer. Look at those "
    "places yourself. Correct only what is plainly a spelling, punctuation or grammar slip, as small a change as "
    "possible, one place at a time; if a place is not plainly a slip, leave it exactly as written."
)


def second_runner(system: str, prompt: str) -> str | None:
    for attempt in range(RUNNER_TRIES):
        try:
            result = model_backend.run_model(
                SECOND_ROLE,
                prompt,
                model=model_backend.model_for_role(SECOND_ROLE, backend="openrouter"),
                backend="openrouter",
                system_prompt=system,
                timeout=120,
                reasoning="low",
                max_tokens=6000,
                route_reason="statement-model-proofread-second",
            )
        except Exception:
            result = None
        if result is not None and result.ok:
            return result.text
        if attempt + 1 < RUNNER_TRIES:
            time.sleep(RUNNER_PAUSE_S * (attempt + 1))
    return None


def para_label(text: str, index: int) -> str:
    match = re.match(r"\s*(\d+)[.)]", text)
    return match.group(1) if match else f"#{index + 1}"


def _parse(reply: str | None) -> str | None:
    if reply is None:
        return None
    raw = re.sub(r"^```(?:json)?", "", reply.strip()).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    value = data.get("corrected") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def _protected_items(protected: Iterable[str]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for string in protected:
        string = " ".join(str(string or "").split())
        if len(string) < 2:
            continue
        kind = "PLACE" if re.search(r"\d", string) else "PERSON"
        items.append((kind, string))
        items += [(kind, part) for part in re.split(r"[\s,]+", string) if len(part) >= 3 and part.isalpha()]
    return items


def _norm(text: str) -> str:
    return re.sub(r"[   ]", " ", text)


def _quoted(text: str) -> list[str]:
    return _QUOTED_RE.findall(text)


def _paragraph_ok(original: str, corrected: str) -> str | None:
    if re.findall(r"\d+", original) != re.findall(r"\d+", corrected):
        return "changes a number"
    if _quoted(original) != _quoted(corrected):
        return "touches words in quotation marks"
    ow, cw = sp._words(original), sp._words(corrected)
    if abs(len(ow) - len(cw)) > MAX_WORD_DRIFT:
        return "changes too many words"
    low, lcw = [w.lower() for w in ow], [w.lower() for w in cw]
    if low != lcw and sorted(low) == sorted(lcw):
        return "moves words to another place"
    if abs(len(_TERMINATOR_RE.findall(original)) - len(_TERMINATOR_RE.findall(corrected))) > 1:
        return "changes where sentences end"
    return None


_APOSTROPHE_TOKEN_RE = re.compile(r"[A-Za-z]+['’][A-Za-z]*")
_CONTRACTION_BASES = frozenset("it he she that who what there here let".split())
_CONTRACTIONS = frozenset(
    "didn't couldn't wouldn't shouldn't wasn't weren't isn't aren't doesn't don't hasn't haven't hadn't won't can't mustn't needn't "
    "i'm i've i'd i'll you're you've we're we've they're they've".split()
)
_ITS_IS_IT_IS = re.compile(r"\bits\s+(?:been|going|not|just|always|never|only|very|really|too|so|nice|hard|easy|time|true|clear)\b")
_HAVE_SLIP_BEFORE = frozenset("should could would must might may".split())


def _apostrophe_tokens(text: str) -> list[str]:
    return [t.lower().replace("’", "'") for t in _APOSTROPHE_TOKEN_RE.findall(text)]


def _apostrophe_problem(orig: str, new: str, paragraph: str) -> str | None:
    before, after = _apostrophe_tokens(orig), _apostrophe_tokens(new)
    if before == after:
        return None
    gone = [t for t in before if t not in after or before.count(t) > after.count(t)]
    moved = [t for t in gone if any(a.replace("'", "") == t.replace("'", "") and a in _CONTRACTIONS for a in after)]
    gone = [t for t in gone if t not in moved]
    if gone:
        return "removes an apostrophe"
    in_paragraph = set(_apostrophe_tokens(paragraph))
    orig_words = {w.lower().replace("’", "'") for w in sp._words(orig)}
    for token in after:
        if token in before and after.count(token) <= before.count(token):
            continue
        if token in _CONTRACTIONS and any(m.replace("'", "") == token.replace("'", "") for m in moved):
            continue
        if token.endswith("s'"):
            if token in in_paragraph:
                continue
            return "plural possessive (s') is not applied"
        match = re.fullmatch(r"([a-z]+)'s", token)
        if match:
            base = match.group(1)
            if token == "it's" and _ITS_IS_IT_IS.search(orig.lower().replace("’", "'")):
                continue
            if base in _CONTRACTION_BASES:
                return "possessive or contraction cannot be told apart"
            if base + "s" not in orig_words:
                return "possessive repair must be word+s to word's"
            continue
        if token.replace("'", "") not in orig_words:
            return "adds an apostrophe that is not a contraction or possessive repair"
    return None


def _known_capital(word: str, paragraph_caps: set[str]) -> bool:
    base = re.sub(r"['’]s$", "", word).lower()
    return any(sa.osa_distance(base, known.lower()) <= 2 for known in paragraph_caps if known[:1].isupper() and len(known) >= 4)


def _sentence_initial(words_text: str, position: int) -> bool:
    before = words_text[:position].rstrip()
    return not before or before[-1] in ".?!:"


_SUFFIXES = ("ing", "ed", "es", "ly", "s")


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _inflection_problem(old: str, new: str, paragraph_lower: str) -> str | None:
    if "'" in new.replace("’", "'") and new.replace("'", "").replace("’", "") == old:
        return None
    if _stem(old) != _stem(new) and old.rstrip("s") != new.rstrip("s"):
        return None
    if new.endswith("ed") and (
        re.search(rf"\b{re.escape(old)}\s+and\s+\w+ed\b", paragraph_lower) or re.search(rf"\b\w+ed\s+and\s+{re.escape(old)}\b", paragraph_lower)
    ):
        return None
    return "changes a word's number or tense, not a typo"


_PERSON_WORDS = frozenset("he she him her hers his they them their we us our i me my you your it its".split())
_NEGATION_WORDS = frozenset("no not never none nothing nobody nowhere".split())
_AN_BEFORE_SILENT_H = frozenset("hour hours honest honour honours honourable heir".split())


def _article_agrees(article: str, following: str) -> bool:
    word = re.sub(r"[^a-z]", "", following.lower())
    if not word:
        return False
    if word in _AN_BEFORE_SILENT_H:
        return article == "an"
    first = word[0]
    if first in "aeio" and not word.startswith(("one", "once", "oh", "ok")):
        return article == "an"
    if first in "bcdfgjklmnpqrstvwxyz":
        return article == "a"
    return False


def _meaning_swap(old: str, new: str) -> str | None:
    if old in _PERSON_WORDS and new in _PERSON_WORDS:
        return "swaps one person word for another"
    if old in _NEGATION_WORDS and new in _NEGATION_WORDS:
        return "swaps one negative word for another"
    return None


def _allowed(orig: str, new: str, paragraph: str, protected: Sequence[str], corpus: str, at_paragraph_end: bool) -> str | None:
    orig, new = _norm(orig), _norm(new)
    if orig == new:
        return "no change"
    if re.findall(r"[\t\r\n]", orig) != re.findall(r"[\t\r\n]", new):
        return "touches a tab or line break"
    if re.sub(r"\s+", "", orig) == re.sub(r"\s+", "", new) and not (abs(orig.count(" ") - new.count(" ")) == 1 and "  " not in orig + new) and not (
        new == re.sub(r" {2,}", " ", orig) or (at_paragraph_end and new == orig.rstrip(" ")) or new == re.sub(r" +,(?=[A-Za-z])", ", ", orig)
    ):
        return "changes spacing other than collapsing doubled spaces"
    if re.findall(r"\d+", orig) != re.findall(r"\d+", new):
        return "changes a number"
    problem = _apostrophe_problem(orig, new, paragraph)
    if problem:
        return problem
    for string in protected:
        if string and orig.lower().count(string.lower()) != new.lower().count(string.lower()):
            return "touches a name or place"
    if _OTHER_PUNCT_RE.findall(orig) != _OTHER_PUNCT_RE.findall(new):
        return "changes punctuation other than commas and full stops"
    if abs(orig.count(",") - new.count(",")) > 1:
        return "changes several commas"
    delta = len(_TERMINATOR_RE.findall(new)) - len(_TERMINATOR_RE.findall(orig))
    if delta not in (0, 1) or (delta == 1 and not at_paragraph_end):
        return "changes where a sentence ends"

    ow, nw = sp._words(orig), sp._words(new)
    olow, nlow = [w.lower() for w in ow], [w.lower() for w in nw]
    paragraph_words = {w.lower() for w in sp._words(paragraph)}
    paragraph_caps = set(sp._words(paragraph))
    changed = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, olow, nlow, autojunk=False).get_opcodes():
        if tag == "equal":
            for a, b in zip(ow[i1:i2], nw[j1:j2]):
                if a == b:
                    continue
                changed += 1
                if b == "I":
                    continue
                if a[:1].islower() and b[:1].isupper() and _sentence_initial(new, new.find(b)):
                    continue
                if sp._mid_sentence(b, corpus):
                    continue
                return "changes a capital letter"
            continue
        changed += 1
        a, b = olow[i1:i2], nlow[j1:j2]
        if tag == "replace":
            if a == ["of"] and b == ["have"] and i1 > 0 and olow[i1 - 1] in _HAVE_SLIP_BEFORE:
                continue
            if len(a) == 1 and len(b) == 1:
                swap = _meaning_swap(a[0], b[0])
                if swap:
                    return swap
                if {a[0], b[0]} == {"a", "an"}:
                    if j2 >= len(nlow) or not _article_agrees(b[0], nlow[j2]):
                        return "a or an that does not agree with the next word"
                    continue
                if not re.fullmatch(r"[a-z]+(?:['’][a-z]+)?", b[0]) or sa.osa_distance(a[0], b[0]) > 2:
                    return "swaps a word"
                problem = _inflection_problem(a[0], b[0], paragraph.lower())
                if problem:
                    return problem
            elif len(a) == 1 and len(b) == 2 and "".join(b) == a[0]:
                pass
            elif len(a) == 2 and len(b) == 1 and "".join(a) == b[0]:
                pass
            else:
                return "swaps or reorders words"
        elif tag == "insert":
            if len(b) > 2 or any(w not in FUNCTION_WORDS for w in b):
                return "adds a word that is not a small function word"
            if any(w in PRONOUNS and w not in paragraph_words for w in b):
                return "adds a pronoun that does not occur in the paragraph"
        else:
            if len(a) != 1 or not ((i1 > 0 and olow[i1 - 1] == a[0]) or (i2 < len(olow) and olow[i2] == a[0])):
                return "removes a word"
        for word in nw[j1:j2]:
            if word[:1].isupper() and not _sentence_initial(new, new.find(word)) and not _known_capital(word, paragraph_caps):
                return "adds a new proper noun"
    if changed > MAX_WORD_DRIFT:
        return "changes too many words at once"
    return None


_PREFIX_RE = re.compile(r"^\s*(?:(?:\(?(?:\d{1,3}|[A-Za-z]|[ivxIVX]{1,5})[.)]|\([A-Za-z0-9]{1,3}\))[ \t]+)?")
_TITLE_RE = re.compile(r"^\s*(?:(?:first|second|third|fourth|\d+(?:st|nd|rd|th))\s+)?witness statement of\b", re.IGNORECASE)
NEAR_CHARS = 3


def _prefix_length(text: str) -> int:
    match = _PREFIX_RE.match(text)
    return match.end() if match else 0


def _protected_layout(text: str) -> bool:
    return text[:1] == "\t" or text.strip().isupper()


def _too_close(text: str, first: Edit, second: Edit) -> bool:
    if second.start <= first.end + NEAR_CHARS:
        return True
    gap_end = second.start
    while gap_end > 0 and not text[gap_end - 1].isspace():
        gap_end -= 1
    gap_start = first.end
    while gap_start < len(text) and not text[gap_start].isspace():
        gap_start += 1
    return len(text[gap_start:gap_end].split()) <= 1


def _apply(text: str, edits: Sequence[Edit]) -> str:
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        text = text[: edit.start] + edit.replacement + text[edit.end :]
    return text


def _changes_stay_inside_edits(text: str, result: str, edits: Sequence[Edit]) -> bool:
    rebuilt: list[str] = []
    pos = 0
    for edit in sorted(edits, key=lambda e: (e.start, e.end)):
        if edit.start < pos or text[edit.start : edit.end] != edit.original:
            return False
        rebuilt += [text[pos : edit.start], edit.replacement]
        pos = edit.end
    rebuilt.append(text[pos:])
    return "".join(rebuilt) == result


def _kept(edit: Edit, reason: str) -> Edit:
    return Edit(edit.para, edit.label, edit.start, edit.end, edit.original, edit.replacement, False, f"kept as written: {reason}", edit.before, edit.after)


def _touches_protected(body: str, start: int, end: int, protected: Sequence[str]) -> bool:
    for string in protected:
        words = str(string or "").split()
        if not words:
            continue
        pattern = r"\s+".join(re.escape(w) for w in words)
        for match in re.finditer(pattern, body, re.IGNORECASE):
            if start <= match.end() and end >= match.start():
                return True
    return False


def _candidates(index: int, label: str, body: str, protected: Sequence[str], protected_items: list[tuple[str, str]], corpus: str, runner: Callable[[str, str], str | None], note: str = "") -> tuple[list[Edit], list[Edit], bool]:
    ph = sp.Placeholders(protected_items)
    hidden = ph.hide(body)
    prompt = f"Paragraph:\n{hidden}" + (f"\n\nNotes from the first proofreader:\n{ph.hide(note)}" if note else "")
    corrected_hidden = _parse(runner(SECOND_SYSTEM if note else SYSTEM, prompt))
    if corrected_hidden is None:
        return [], [], False
    if ph.tokens_in(hidden) != ph.tokens_in(corrected_hidden):
        return [], [Edit(index, label, 0, 0, body[:40], "", False, "the model changed a name, place, date or number", body[:40])], True
    corrected = ph.restore(corrected_hidden)
    if corrected == body:
        return [], [], True
    why = _paragraph_ok(body, corrected)
    if why:
        return [], [Edit(index, label, 0, 0, body[:40], "", False, f"whole paragraph: {why}", body[:40])], True

    approved: list[Edit] = []
    left: list[Edit] = []
    for orig_span, new_span in sp.narrow(body, corrected):
        placed = sp._locate(body, orig_span)
        if placed is None:
            left.append(Edit(index, label, 0, 0, orig_span, new_span, False, "could not place the suggestion", orig_span, new_span))
            continue
        offset, old, new = sp.minimal_edit(orig_span, new_span)
        start = placed[0] + offset
        end = start + len(old)
        problem = _allowed(orig_span, new_span, body, protected, corpus, at_paragraph_end=placed[1] >= len(body.rstrip()))
        if problem is None and not (old or new):
            problem = "no change"
        if problem is None and _touches_protected(body, start, end, protected):
            problem = "touches or sits next to a name, address or other protected text"
        if problem is None and (len(old) + len(new)) > MAX_CHAR_RATIO * max(len(body), 1) * 4 + 20:
            problem = "a larger edit than a slip"
        candidate = Edit(index, label, start, end, old, new, problem is None, "" if problem is None else problem, orig_span, new_span)
        (approved if problem is None else left).append(candidate)
    return approved, left, True


_LOWERCASE_BRANDS = frozenset("iphone ipad ipod ebay eg ie etc".split())


def _opening_capital(index: int, label: str, body: str, approved: Sequence[Edit]) -> Edit | None:
    match = re.match(r"([a-z])([a-z']*)(?=[\s,.;:!?]|$)", body)
    if not match or (match.group(1) + match.group(2)).lower() in _LOWERCASE_BRANDS:
        return None
    if any(e.start <= 0 < e.end or (e.start == 0 and e.end == 0) for e in approved):
        return None
    word = body[: match.end()]
    return Edit(index, label, 0, 1, body[0], body[0].upper(), True, "", word, word[0].upper() + word[1:])


def _layout_only(edit: Edit) -> bool:
    return not re.search(r"[A-Za-z0-9]", edit.original + edit.replacement)


def _merge_layout_pairs(body: str, approved: list[Edit], protected: Sequence[str], corpus: str) -> list[Edit]:
    out: list[Edit] = []
    i = 0
    while i < len(approved):
        a = approved[i]
        b = approved[i + 1] if i + 1 < len(approved) else None
        if b is not None and _layout_only(a) and _layout_only(b) and b.start <= a.end + NEAR_CHARS:
            s, e = a.start, b.end
            while s > 0 and not body[s - 1].isspace():
                s -= 1
            while e < len(body) and not body[e].isspace():
                e += 1
            orig = body[s:e]
            new = body[s : a.start] + a.replacement + body[a.end : b.start] + b.replacement + body[b.end : e]
            if _allowed(orig, new, body, protected, corpus, e >= len(body.rstrip())) is None:
                out.append(Edit(a.para, a.label, s, e, orig, new, True, "", orig, new))
                i += 2
                continue
        out.append(a)
        i += 1
    return out


def _first_pass_note(left: Sequence[Edit]) -> str:
    lines = []
    for e in left:
        if e.original and e.replacement != e.original:
            lines.append(f"- {e.before or e.original!r}: first proofreader suggested {e.after or e.replacement!r}; the guard refused it ({e.reason}).")
        else:
            lines.append(f"- the whole paragraph: the guard refused the first proofreader's answer ({e.reason}).")
    return "\n".join(lines)


def _same_place(a: Edit, b: Edit) -> bool:
    if (a.start, a.end, a.replacement) == (b.start, b.end, b.replacement):
        return True
    return a.end > a.start and b.end > b.start and a.start < b.end and b.start < a.end


def _paragraph(index: int, text: str, protected: Sequence[str], protected_items: list[tuple[str, str]], corpus: str, runner: Callable[[str, str], str | None], second: Callable[[str, str], str | None] | None = None) -> tuple[list[Edit], bool]:
    label = para_label(text, index)
    base = _prefix_length(text)
    body = text[base:]
    a1, l1, ok1 = _candidates(index, label, body, protected, protected_items, corpus, runner)
    a2: list[Edit] = []
    l2: list[Edit] = []
    ok2 = False
    second_ran = second is not None and (not ok1 or bool(l1))
    if second_ran:
        note = "The first proofreader gave no usable answer for this paragraph." if not ok1 else _first_pass_note(l1)
        assert second is not None
        a2, l2, ok2 = _candidates(index, label, body, protected, protected_items, corpus, second, note)
    if not ok1 and not ok2:
        return [], False
    approved = list(a1)
    for edit in a2:
        if not any((e.start, e.end, e.replacement) == (edit.start, edit.end, edit.replacement) for e in approved):
            approved.append(edit)
    left: list[Edit] = []
    for edit in [*l1, *l2]:
        if any(_same_place(edit, e) for e in approved):
            continue
        if any((e.start, e.end, e.original, e.replacement, e.reason) == (edit.start, edit.end, edit.original, edit.replacement, edit.reason) for e in left):
            continue
        left.append(edit)

    capital = _opening_capital(index, label, body, approved)
    if capital is not None:
        approved.append(capital)
    approved.sort(key=lambda e: (e.start, e.end))
    approved = _merge_layout_pairs(body, approved, protected, corpus)
    conflicted: set[int] = set()
    for i in range(len(approved) - 1):
        if _too_close(body, approved[i], approved[i + 1]):
            conflicted.update((i, i + 1))
    if len(approved) - len(conflicted) > MAX_FIXES_PER_PARAGRAPH:
        conflicted.update(range(len(approved)))
        reason = "too many changes in one paragraph"
    else:
        reason = "sits next to another change"
    kept = [e for i, e in enumerate(approved) if i not in conflicted]
    left += [_kept(e, reason) for i, e in enumerate(approved) if i in conflicted]

    if kept:
        result = _apply(body, kept)
        if _paragraph_ok(body, result) or not _changes_stay_inside_edits(body, result, kept):
            left += [_kept(e, "the combined result failed the whole-paragraph check") for e in kept]
            kept = []

    left = [e if e.reason.startswith("kept as written") else _kept(e, f"{e.reason}; read by {'two models' if second_ran else 'one model'}") for e in left]

    def shifted(edit: Edit) -> Edit:
        return Edit(edit.para, edit.label, edit.start + base, edit.end + base, edit.original, edit.replacement, edit.applied, edit.reason, edit.before, edit.after)

    return [shifted(e) for e in [*kept, *left]], True


def proofread(paragraphs: Sequence[str], *, protected: Iterable[str] = (), runner: Callable[[str, str], str | None] | None = None, second: Callable[[str, str], str | None] | None = None) -> Result:
    run = runner or default_runner
    second_run = second if second is not None else (second_runner if runner is None else None)
    protected = [p for p in (str(x) for x in protected) if p.strip()]
    items = _protected_items(protected)
    corpus = "\n".join(paragraphs)
    title = next((i for i, text in enumerate(paragraphs) if _TITLE_RE.match(text)), -1)
    result = Result()
    for index, text in enumerate(paragraphs):
        if index <= title or _protected_layout(text) or len(sp._words(text[_prefix_length(text):])) < MIN_WORDS:
            continue
        result.paragraphs += 1
        edits, ok = _paragraph(index, text, protected, items, corpus, run, second_run)
        result.edits += edits
        if not ok:
            result.failures += 1
    result.checked = result.failures == 0
    return result


def format_change_list(result: Result) -> str:
    applied = [e for e in result.edits if e.applied]
    left = [e for e in result.edits if not e.applied]
    lines = [f"Paragraphs proofread: {result.paragraphs}."]
    if not result.checked:
        lines.append(f"SPELLING NOT CHECKED: the model could not check {result.failures} paragraph(s); they are left as written.")
    lines.append(f"Corrections made ({len(applied)}):")
    lines += [f"  Paragraph {e.label}: {(e.before or e.original)!r} -> {(e.after or e.replacement)!r}" for e in applied]
    lines.append(f"Kept as the client wrote it ({len(left)}):")
    lines += [f"  Paragraph {e.label}: {(e.before or e.original)!r}" + (f" (model suggested {e.after!r})" if e.after else "") + f": {e.reason}" for e in left]
    return "\n".join(lines) + "\n"


def fake_runner(substitutions: dict[str, str]) -> Callable[[str, str], str | None]:

    def run(system: str, prompt: str) -> str:
        text = prompt.split("Paragraph:\n", 1)[1]
        for old, new in substitutions.items():
            text = text.replace(old, new)
        return json.dumps({"corrected": text})

    return run


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Show the change list the guarded proofread would make to a statement (.docx). Read-only: nothing is written. "
        "Without --live a fake model makes only the --fake substitutions, so no text leaves this machine."
    )
    parser.add_argument("docx", type=Path)
    parser.add_argument("--protect", action="append", default=[], help="A name or address to protect (repeatable).")
    parser.add_argument("--fake", action="append", default=[], metavar="OLD=>NEW", help="A substitution the fake model makes (repeatable).")
    parser.add_argument("--live", action="store_true", help="Use the real model (the paragraphs go to it with names hidden).")
    args = parser.parse_args(argv)

    from docx import Document

    paragraphs = [p.text for p in Document(str(args.docx)).paragraphs]
    substitutions = dict(item.split("=>", 1) for item in args.fake if "=>" in item)
    result = proofread(paragraphs, protected=args.protect, runner=None if args.live else fake_runner(substitutions))
    sys.stdout.write(format_change_list(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
