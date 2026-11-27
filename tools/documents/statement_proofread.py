#!/usr/bin/env python3
"Two-layer proofread of a witness statement, returned as tracked changes."
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from docx import Document
from docx.oxml.ns import qn
from docx.text.run import Run

from documents import spelling_autofix

AUTO = "auto-safe"
PERSON = "needs-a-person"
LAYERS = ("tidy", "llm")
LLM_RUNS = 2
LLM_ROLE = "large"
LLM_TIMEOUT = 90.0
MAX_SPAN_WORDS = 25
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


@dataclass
class Change:
    layer: str
    klass: str
    para: int
    start: int
    end: int
    original: str
    suggestion: str
    reason: str
    applied: bool = False
    note: str = ""
    runs: int = 1




def _child_len(child) -> int:
    if child.tag == qn("w:t"):
        return len(child.text or "")
    if child.tag in (qn("w:tab"), qn("w:br"), qn("w:cr")):
        return 1
    return 0


def _run_text(r) -> str:
    out = []
    for c in r:
        if c.tag == qn("w:t"):
            out.append(c.text or "")
        elif c.tag == qn("w:tab"):
            out.append("\t")
        elif c.tag in (qn("w:br"), qn("w:cr")):
            out.append("\n")
    return "".join(out)


def direct_runs(p_el) -> list:
    "The paragraph's plain runs, in order, including those inside a link (an address Word has turned"
    out = []
    for child in p_el:
        if child.tag == qn("w:r"):
            out.append(child)
        elif child.tag == qn("w:hyperlink"):
            out += [r for r in child if r.tag == qn("w:r")]
    return out


def paragraph_text(p_el) -> str:
    return "".join(_run_text(r) for r in direct_runs(p_el))


_BOILERPLATE = re.compile(r"^\s*(?:statement\s+of\s+truth\b|I\s+believe\s+(?:that\s+)?the\s+facts\b)", re.I)


def statement_paragraphs(doc) -> list[tuple[int, str]]:
    "(index into doc.paragraphs, text) for each body paragraph with words in it."
    out = []
    for i, p in enumerate(doc.paragraphs):
        text = paragraph_text(p._p)
        if text.strip() and text == p.text and not _BOILERPLATE.match(text):
            out.append((i, text))
    return out



_TIDY = re.compile(
    r"(?P<comma_stuck>,(?:[ \t]*,)*(?=[A-Za-z]))"
    r"|(?P<comma_doubled>,(?:[ \t]*,)+)"
    r"|(?P<comma_no_space>,(?=[A-Za-z]))"
    r"|(?P<spaces>(?<=\S) {2,}(?=\S))"
    r"|(?P<stop_no_space>(?<=[a-z]{3})\.(?=[A-Z][a-z]))"
    r"|(?P<space_before>(?<=\S) +(?=[,;](?:\s|$)|\.(?:\s|$)))"
)
_REPEAT = re.compile(r"\b(the|a|an|and|of|to|in|is|was|that|it|my|he|she|on|for|with|I)\s+\1\b", re.I)
_TIDY_REASON = {
    "comma_stuck": "a doubled comma or a comma run into the next word",
    "comma_doubled": "a doubled comma",
    "comma_no_space": "a comma with no space after it",
    "spaces": "extra spaces between words",
    "stop_no_space": "a full stop with no space after it",
    "space_before": "a space before a comma, semicolon or full stop",
}


def tidy(text: str) -> list[Change]:
    "Typing slips found by pattern. Changes that only touch spacing and stray punctuation are auto-safe."
    changes: list[Change] = []
    for m in _TIDY.finditer(text):
        kind = m.lastgroup or ""
        original = m.group(0)
        if kind in ("comma_stuck", "comma_no_space"):
            new = ", "
        elif kind == "comma_doubled":
            new = ","
        elif kind == "spaces":
            new = " "
        elif kind == "stop_no_space":
            new = ". "
        else:
            new = ""
        changes.append(Change("tidy", AUTO, -1, m.start(), m.end(), original, new, _TIDY_REASON[kind]))
    for m in _REPEAT.finditer(text):
        word = m.group(1)
        changes.append(Change("tidy", PERSON, -1, m.start(), m.end(), m.group(0), word, f"the word '{word}' is repeated"))
    return changes



_DATE_RE = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+\d{4})?\b"
    r"|\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b",
    re.I,
)
_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
_NUMBER_RE = re.compile(r"(?:\d[\d,./:\-]*\d|\d)(?:st|nd|rd|th|am|pm)?\b", re.I)


def _protected_strings(client: str, respondent: str, children: Iterable[str], addresses: Iterable[str]) -> list[tuple[str, str]]:
    "(kind, string) for each thing that must never reach a model or be changed: whole names first."
    items: list[tuple[str, str]] = []
    for name in [client, respondent, *children]:
        name = " ".join(str(name or "").split())
        if not name:
            continue
        items.append(("PERSON", name))
        items += [("PERSON", part) for part in name.split() if len(part) >= 2]
    for address in addresses:
        address = " ".join(str(address or "").split())
        if not address:
            continue
        items.append(("PLACE", address))
        items += [("PLACE", part.strip()) for part in address.split(",") if len(part.strip()) >= 3]
    return items


class Placeholders:
    "Swap protected strings for tokens like PERSON_1, and back, so a model never sees who it is about."

    def __init__(self, protected: Sequence[tuple[str, str]]):
        self._kinds: dict[str, str] = {}
        for kind, string in protected:
            self._kinds.setdefault(string, kind)
        self._token_of: dict[str, str] = {}
        self._string_of: dict[str, str] = {}
        self._count: dict[str, int] = {}

    @staticmethod
    def _letters(n: int) -> str:
        "1 -> A, 26 -> Z, 27 -> AA: no digits, so the number pass cannot touch a token."
        out = ""
        while n:
            n, rem = divmod(n - 1, 26)
            out = chr(65 + rem) + out
        return out

    def _token(self, kind: str, string: str) -> str:
        if string not in self._token_of:
            self._count[kind] = self._count.get(kind, 0) + 1
            token = f"{kind}_{self._letters(self._count[kind])}"
            self._token_of[string] = token
            self._string_of[token] = string
        return self._token_of[string]

    def hide(self, text: str) -> str:
        for string in sorted(self._kinds, key=len, reverse=True):
            pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(string) + r"(?![A-Za-z0-9])", re.I)
            text = pattern.sub(lambda m, s=string: self._token(self._kinds[s], m.group(0)), text)
        for kind, rx in (("PLACE", _POSTCODE_RE), ("DATE", _DATE_RE), ("NUMBER", _NUMBER_RE)):
            text = rx.sub(lambda m, k=kind: self._token(k, m.group(0)), text)
        return text

    def restore(self, text: str) -> str:
        return re.sub(r"\b(?:PERSON|PLACE|DATE|NUMBER)_[A-Z]{1,3}\b", lambda m: self._string_of.get(m.group(0), m.group(0)), text)

    @staticmethod
    def tokens_in(text: str) -> list[str]:
        return sorted(re.findall(r"\b(?:PERSON|PLACE|DATE|NUMBER)_[A-Z]{1,3}\b", text))



_WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")


def _words(text: str) -> list[str]:
    return _WORD.findall(text)


def _terminators(text: str) -> int:
    return len(re.findall(r"[.?!]", text))


def _mid_sentence(word: str, corpus: str) -> bool:
    "True when ``word`` (exactly as written, capitals included) occurs mid-sentence somewhere in ``corpus``."
    return re.search(r"(?<=[a-z,;] )" + re.escape(word) + r"\b", corpus) is not None


def classify(original: str, suggestion: str, protected: Sequence[str], corpus: str = "") -> tuple[str, str] | None:
    "(class, reason) for a suggested change, or None when it must be rejected outright."
    original, suggestion = (re.sub(r"[\u00a0\u2009\u202f]", " ", x) for x in (original, suggestion))
    if original == suggestion:
        return None
    if re.findall(r"\d+", original) != re.findall(r"\d+", suggestion):
        return None
    for string in protected:
        if string and original.lower().count(string.lower()) != suggestion.lower().count(string.lower()):
            return None
    ow, sw = _words(original), _words(suggestion)
    if len(ow) != len(sw):
        return PERSON, "adds or removes a word"
    if _terminators(original) != _terminators(suggestion):
        return PERSON, "changes where a sentence ends"
    if original.count(",") != suggestion.count(","):
        return PERSON, "adds or removes a comma"
    if [w.lower() for w in ow] == [w.lower() for w in sw]:
        if ow != sw:
            changed = [b for a, b in zip(ow, sw) if a != b]
            if all(_mid_sentence(b, corpus) for b in changed):
                return AUTO, "capitalisation"
            return PERSON, "capitalisation"
        return (AUTO, "spacing") if re.sub(r"\s+", "", original) == re.sub(r"\s+", "", suggestion) else (PERSON, "punctuation")
    for a, b in zip(ow, sw):
        if a.lower() != b.lower() and (spelling_autofix.osa_distance(a.lower(), b.lower()) > 2 or not b.isalpha()):
            return PERSON, "swaps a word"
    return AUTO, "spelling"


_TOKEN = re.compile(r"\s+|\w+(?:['’]\w+)?|[^\w\s]")
CONTEXT_WORDS = 2


def narrow(original: str, corrected: str) -> list[tuple[str, str]]:
    "The small pieces that really differ, each with a couple of words either side for context."
    import difflib

    a, b = _TOKEN.findall(original), _TOKEN.findall(corrected)
    pieces: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        lo, hi = i1, i2
        while lo > 0 and not a[lo - 1].isspace():
            lo -= 1
        while hi < len(a) and not a[hi].isspace():
            hi += 1
        for _ in range(CONTEXT_WORDS):
            while lo > 0 and a[lo - 1].isspace():
                lo -= 1
            while lo > 0 and not a[lo - 1].isspace():
                lo -= 1
            while hi < len(a) and a[hi].isspace():
                hi += 1
            while hi < len(a) and not a[hi].isspace():
                hi += 1
        left, right = "".join(a[lo:i1]), "".join(a[i2:hi])
        pieces.append((left + "".join(a[i1:i2]) + right, left + "".join(b[j1:j2]) + right))
    return pieces


def _locate(text: str, span: str) -> tuple[int, int] | None:
    "The one place ``span`` occurs in ``text`` ignoring whitespace differences, else None."
    tokens = span.split()
    if not tokens:
        return None
    rx = re.compile(r"\s+".join(re.escape(t) for t in tokens))
    found = list(rx.finditer(text))
    return (found[0].start(), found[0].end()) if len(found) == 1 else None



_PROMPT = """You are proofreading a UK witness statement written by a client, in her own words.
Correct ONLY spelling, grammar and punctuation, in British English. Do not rewrite, reorder, add or
remove ideas, and do not improve style or choose better words. Never change a fact, number, date or
meaning. Words like PERSON_A, PLACE_A, DATE_A and NUMBER_A are placeholders: copy them exactly and never
edit, add or remove one. Do not add commas to lists.

Look for: misspellings; extra or missing spaces; a missing word that makes a sentence incomplete or ungrammatical
(a sentence with no verb, a date with no "on" before it); a comma splice (two full sentences joined by a comma);
inconsistent capital letters for the same term (for example "court" and "Court", or a legal term written two ways);
a missing comma after a name or a person's title; a full stop or space missing between sentences.

Each paragraph below starts with its number in square brackets. Reply with JSON only: a list of objects
{{"paragraph": <number>, "original": "<the exact words from the paragraph, as few as will do, at most {max_words} words>",
"corrected": "<the same words corrected>", "reason": "<a few words>"}}. One object per change. If there is
nothing to correct, reply [].

{body}
"""


def _parse_json_list(text: str) -> list[dict[str, Any]]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    a, b = text.find("["), text.rfind("]")
    if a < 0 or b < a:
        return []
    try:
        data = json.loads(text[a : b + 1])
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict)]


def _default_runner(prompt: str) -> tuple[str, dict[str, Any]]:
    import model_backend

    result = model_backend.run_model(LLM_ROLE, prompt, timeout=LLM_TIMEOUT, telemetry=True, route_reason="statement_proofread")
    if not result.ok:
        raise RuntimeError("the language model did not answer")
    return result.text, {"model": result.model, "seconds": round(result.elapsed_seconds, 1), **(result.usage or {})}


def llm_layer(
    paras: Sequence[tuple[int, str]],
    protected: Sequence[tuple[str, str]],
    *,
    runner: Callable[[str], tuple[str, dict[str, Any]]] | None = None,
    runs: int = LLM_RUNS,
) -> tuple[list[Change], dict[str, Any]]:
    "Ask the model ``runs`` times, guard every suggestion against the real text, merge the runs."
    runner = runner or _default_runner
    hider = Placeholders(protected)
    body = "\n\n".join(f"[{n}] {hider.hide(text)}" for n, text in paras)
    prompt = _PROMPT.format(max_words=MAX_SPAN_WORDS, body=body)
    text_of = dict(paras)
    protected_strings = [s for _k, s in protected]
    corpus = "\n".join(text_of.values())
    merged: dict[tuple[int, int, int, str], Change] = {}
    stats: dict[str, Any] = {"runs": 0, "rejected": 0, "rejected_by": {}, "usage": []}

    def reject(why: str) -> None:
        stats["rejected"] += 1
        stats["rejected_by"][why] = stats["rejected_by"].get(why, 0) + 1

    for _ in range(runs):
        try:
            raw, usage = runner(prompt)
        except Exception as exc:
            stats.setdefault("errors", []).append(type(exc).__name__)
            continue
        stats["runs"] += 1
        stats["usage"].append(usage)
        for item in _parse_json_list(raw):
            try:
                para = int(item.get("paragraph"))
            except (TypeError, ValueError):
                reject("no paragraph number")
                continue
            hidden_o, hidden_c = str(item.get("original") or ""), str(item.get("corrected") or "")
            if para not in text_of:
                reject("unknown paragraph")
                continue
            if Placeholders.tokens_in(hidden_o) != Placeholders.tokens_in(hidden_c):
                reject("placeholder changed")
                continue
            original, corrected = hider.restore(hidden_o), hider.restore(hidden_c)
            if _locate(text_of[para], original) is None:
                reject("original not found exactly once")
                continue
            if verdict_whole := classify(original, corrected, protected_strings, corpus):
                pieces = narrow(original, corrected)
            else:
                reject("digit or protected text changed, or no change")
                continue
            for piece_o, piece_c in pieces:
                where = _locate(text_of[para], piece_o)
                if where is None:
                    reject("piece not found exactly once")
                    continue
                actual = text_of[para][where[0] : where[1]]
                verdict = classify(actual, piece_c, protected_strings, corpus)
                if verdict is None:
                    reject("digit or protected text changed, or no change")
                    continue
                klass, reason = verdict
                key = (para, where[0], where[1], piece_c)
                if key in merged:
                    merged[key].runs += 1
                else:
                    merged[key] = Change("llm", klass, para, where[0], where[1], actual, piece_c, str(item.get("reason") or reason)[:120] or reason)
    return list(merged.values()), stats




def minimal_edit(original: str, suggestion: str) -> tuple[int, str, str]:
    "(offset into original, text removed, text inserted): trim what the two share at each end."
    p = 0
    while p < min(len(original), len(suggestion)) and original[p] == suggestion[p]:
        p += 1
    s = 0
    while s < min(len(original), len(suggestion)) - p and original[len(original) - 1 - s] == suggestion[len(suggestion) - 1 - s]:
        s += 1
    return p, original[p : len(original) - s], suggestion[p : len(suggestion) - s]


def merge(layers: Sequence[list[Change]]) -> list[Change]:
    "One list, layers in order. Auto-safe changes are applied unless they overlap an earlier applied one"
    out: list[Change] = []
    applied_spans: dict[int, list[tuple[int, int, Change]]] = {}
    for layer in layers:
        for c in sorted(layer, key=lambda c: (c.para, c.start)):
            spans = applied_spans.setdefault(c.para, [])
            clash = next((x for x in spans if c.start < x[1] and x[0] < c.end), None)
            if c.klass == AUTO:
                if clash:
                    if clash[2].suggestion == c.suggestion and clash[2].layer != c.layer:
                        clash[2].note = (clash[2].note + f" also found by {c.layer}").strip()
                    continue
                c.applied = True
                spans.append((c.start, c.end, c))
            elif clash:
                continue
            out.append(c)
    return out




def _split_run(r, offset: int):
    "Split run ``r`` after ``offset`` characters; returns the new right-hand run."
    right = copy.deepcopy(r)
    pos = 0
    for child, twin in zip([c for c in r if c.tag != qn("w:rPr")], [c for c in right if c.tag != qn("w:rPr")]):
        n = _child_len(child)
        if pos + n <= offset:
            right.remove(twin)
        elif pos >= offset:
            r.remove(child)
        else:
            text = child.text or ""
            cut = offset - pos
            child.text, twin.text = text[:cut], text[cut:]
            child.set(_XML_SPACE, "preserve")
            twin.set(_XML_SPACE, "preserve")
        pos += n
    r.addnext(right)
    return right


def isolate(p_el, start: int, end: int) -> tuple[list, Any]:
    "Split the paragraph's direct runs at ``start`` and ``end``; return (runs inside, the run just before ``start``)."
    for boundary in (end, start):
        pos = 0
        for r in direct_runs(p_el):
            n = sum(_child_len(c) for c in r)
            if pos < boundary < pos + n:
                _split_run(r, boundary - pos)
                break
            pos += n
    inside, before, pos = [], None, 0
    for r in direct_runs(p_el):
        n = sum(_child_len(c) for c in r)
        if n and pos >= start and pos + n <= end:
            inside.append(r)
        elif pos + n <= start and (n or before is None):
            before = r
        pos += n
    return inside, before


def _mark(tag: str, ident: int, author: str, when: str):
    el = p_el_factory(tag)
    el.set(qn("w:id"), str(ident))
    el.set(qn("w:author"), author)
    el.set(qn("w:date"), when)
    return el


def p_el_factory(tag: str):
    from docx.oxml import OxmlElement

    return OxmlElement(tag)


def tracked_replace(p_el, start: int, end: int, new: str, author: str, when: str, ident: int) -> None:
    "Replace [start, end) with ``new`` as a Word tracked deletion and insertion."
    inside, before = isolate(p_el, start, end)
    model = inside[0] if inside else before
    rpr = None if model is None else model.find(qn("w:rPr"))
    if inside:
        deletion = _mark("w:del", ident, author, when)
        inside[0].addprevious(deletion)
        for r in inside:
            for t in r.findall(qn("w:t")):
                t.tag = qn("w:delText")
                t.set(_XML_SPACE, "preserve")
            deletion.append(r)
        anchor = deletion
    else:
        anchor = before
    if new:
        insertion = _mark("w:ins", ident + 1, author, when)
        run = p_el_factory("w:r")
        if rpr is not None:
            run.append(copy.deepcopy(rpr))
        t = p_el_factory("w:t")
        t.text = new
        t.set(_XML_SPACE, "preserve")
        run.append(t)
        insertion.append(run)
        if anchor is not None:
            anchor.addnext(insertion)
        else:
            p_el.insert(1 if p_el.find(qn("w:pPr")) is not None else 0, insertion)


def write_copy(source: Path, output: Path, paras_index: Sequence[tuple[int, str]], changes: Sequence[Change], author_prefix: str = "CaseForge proofreader") -> dict[str, int]:
    "Copy ``source`` to ``output`` with the applied changes as tracked changes and the rest as comments."
    if Path(source).resolve() == Path(output).resolve():
        raise ValueError("the output must be a different file: the original is never modified")
    doc = Document(str(source))
    when = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    counts = {"tracked": 0, "comments": 0, "comments_unsupported": 0}
    ident = 9000
    by_para: dict[int, list[Change]] = {}
    for c in changes:
        by_para.setdefault(c.para, []).append(c)
    for para, items in by_para.items():
        paragraph = doc.paragraphs[para]
        for c in sorted(items, key=lambda c: c.start, reverse=True):
            if c.applied:
                offset, removed, inserted = minimal_edit(c.original, c.suggestion)
                tracked_replace(paragraph._p, c.start + offset, c.start + offset + len(removed), inserted, f"{author_prefix}: {c.layer}", when, ident)
                ident += 2
                counts["tracked"] += 1
            elif hasattr(doc, "add_comment"):
                inside, _before = isolate(paragraph._p, c.start, c.end)
                if inside:
                    text = f"{c.layer}: {c.reason}" + (f". Suggested: {c.suggestion}" if c.suggestion else "")
                    doc.add_comment(runs=[Run(r, paragraph) for r in inside], text=text, author=f"{author_prefix}: {c.layer}", initials="VP")
                    counts["comments"] += 1
            else:
                counts["comments_unsupported"] += 1
    doc.save(str(output))
    return counts




def proofread(
    source: Path | str,
    output: Path | str,
    *,
    client: str = "",
    respondent: str = "",
    children: Sequence[str] = (),
    addresses: Sequence[str] = (),
    use_llm: bool = True,
    runner: Callable[[str], tuple[str, dict[str, Any]]] | None = None,
    llm_runs: int = LLM_RUNS,
) -> dict[str, Any]:
    "Run the layers over ``source``, write the tracked-change copy to ``output``, return the report data."
    started = time.monotonic()
    doc = Document(str(source))
    paras = statement_paragraphs(doc)
    protected = _protected_strings(client, respondent, children, addresses)

    layer1: list[Change] = []
    for n, text in paras:
        for c in tidy(text):
            c.para = n
            layer1.append(c)
    notes: list[str] = []
    layer2: list[Change] = []
    llm_stats: dict[str, Any] = {}
    if use_llm:
        layer2, llm_stats = llm_layer(paras, protected, runner=runner, runs=llm_runs)
    else:
        notes.append("The language model layer was switched off.")
    spelling_checked = bool(use_llm) and llm_stats.get("runs", 0) > 0 and not llm_stats.get("errors")
    if not spelling_checked:
        notes.append("Spelling was NOT checked: the language model layer did not run cleanly.")

    changes = merge([layer1, layer2])
    counts = write_copy(Path(source), Path(output), paras, changes)
    return {
        "changes": [asdict(c) for c in changes],
        "counts": counts,
        "spelling_checked": spelling_checked,
        "llm": llm_stats,
        "notes": notes,
        "seconds": round(time.monotonic() - started, 1),
    }


def report_markdown(data: dict[str, Any]) -> str:
    changes = data["changes"]
    lines = ["# Statement proofread", ""]
    applied = [c for c in changes if c["applied"]]
    person = [c for c in changes if not c["applied"]]
    by_layer = ", ".join(f"{layer} {sum(1 for c in changes if c['layer'] == layer)}" for layer in LAYERS)
    lines.append(f"{len(applied)} tracked change(s) applied, {len(person)} suggestion(s) left as comments ({by_layer}).")
    lines.append(f"Took {data['seconds']} s. Language model runs: {data['llm'].get('runs', 0)}, suggestions rejected by the guard: {data['llm'].get('rejected', 0)}.")
    for note in data["notes"]:
        lines.append(f"- {note}")
    for heading, rows in (("Applied as tracked changes", applied), ("Left for a person (comments)", person)):
        lines += ["", f"## {heading}", "", "| Layer | Original | Suggestion | Why |", "| --- | --- | --- | --- |"]
        for c in rows:
            seen = f" (both runs)" if c["runs"] > 1 else ""
            orig, sug = c["original"].replace("|", "/"), c["suggestion"].replace("|", "/")
            lines.append(f"| {c['layer']}{seen} | {orig!r} | {sug!r} | {c['reason']} |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--client", default="")
    parser.add_argument("--respondent", default="")
    parser.add_argument("--child", action="append", default=[], help="A child's name (repeatable).")
    parser.add_argument("--address", action="append", default=[], help="An address to protect (repeatable).")
    parser.add_argument("--no-llm", action="store_true", help="Skip the language model layer (nothing leaves this machine).")
    args = parser.parse_args(argv)
    data = proofread(args.source, args.output, client=args.client, respondent=args.respondent, children=args.child, addresses=args.address, use_llm=not args.no_llm)
    args.output.with_suffix(".changes.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    args.output.with_suffix(".report.md").write_text(report_markdown(data), encoding="utf-8")
    print(f"{data['counts']['tracked']} tracked change(s), {data['counts']['comments']} comment(s); see {args.output.with_suffix('.report.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
