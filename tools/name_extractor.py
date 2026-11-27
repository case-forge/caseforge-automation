#!/usr/bin/env python3
"Shared candidate-name extractor (spaCy PERSON-entity recognition)."
from __future__ import annotations

import re

_nlp = None

_SPAN_SEPARATOR_RE = re.compile(r"\s+[-–—]\s+")


def _split_merged_span(name: str) -> list[str]:
    parts = [p.strip() for p in _SPAN_SEPARATOR_RE.split(name)]
    return [p for p in parts if p]


def _get_nlp():
    global _nlp
    if _nlp is not None:
        return _nlp

    import spacy

    _nlp = spacy.load("en_core_web_sm")
    return _nlp


def extract_candidate_names(text: str) -> list[str]:
    "Extract plausible person-name spans from free text."
    nlp = _get_nlp()
    doc = nlp((text or "").title())
    names: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str) -> None:
        key = candidate.lower()
        if candidate and key not in seen:
            seen.add(key)
            names.append(candidate)

    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue
        name = ent.text.strip()
        if not name:
            continue
        _add(name)
        for part in _split_merged_span(name):
            _add(part)
    return names


_WEAK_ENTITY_LABELS = frozenset({"PERSON", "ORG", "GPE"})


def extract_weak_candidate_names(text: str) -> list[str]:
    "Same PERSON extraction as extract_candidate_names(), plus ORG and"
    nlp = _get_nlp()
    doc = nlp((text or "").title())
    names: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str) -> None:
        key = candidate.lower()
        if candidate and key not in seen:
            seen.add(key)
            names.append(candidate)

    for ent in doc.ents:
        if ent.label_ not in _WEAK_ENTITY_LABELS:
            continue
        name = ent.text.strip()
        if not name:
            continue
        _add(name)
        for part in _split_merged_span(name):
            _add(part)
    return names


def extract_candidate_names_via_model(text: str) -> list[str]:
    "Extract plausible person-name spans from free text via a small model"
    stripped = (text or "").strip()
    if not stripped:
        return []

    import json

    import model_backend

    prompt = (
        "Extract every real person's full name mentioned in the text below. "
        "Reply with ONLY a JSON array of strings, e.g. [\"Jane Doe\"]. "
        "If no person is named, reply with []. Do not include case "
        "references, matter numbers, organisations, or places.\n\n"
        f"Text: {stripped}"
    )
    try:
        raw = model_backend.run_text(model_backend.ROLE_NAME_EXTRACTOR, prompt, timeout=8.0)
    except Exception:
        return []
    if not raw:
        return []
    try:
        parsed = json.loads(raw.strip())
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []

    names: list[str] = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, str):
            continue
        name = item.strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", metavar="TEXT", help="Extract candidate names from one string and print them as JSON.")
    parser.add_argument("--eval", action="store_true", help="Run the held-out accuracy check documented in this module's tests.")
    args = parser.parse_args()

    if args.extract is not None:
        print(json.dumps(extract_candidate_names(args.extract), ensure_ascii=False))
    elif args.eval:
        cases = [
            ("jane doe", ["Jane Doe"]),
            ("mia.miketest", ["Mia Miketest"]),
            ("liam.limatest", ["Liam Limatest"]),
            ("rose.quebectest", []),
            ("what documents are outstanding for mia.miketest", ["Mia Miketest"]),
            ("what is the status of my case", []),
            ("has the ccl been sent yet", []),
        ]
        correct = 0
        for text, expected in cases:
            got = extract_candidate_names(text)
            ok = got == expected
            correct += ok
            print(f"{'OK  ' if ok else 'MISS'} expected={expected!r:30} got={got!r:30} text={text!r}")
        print(f"\n{correct}/{len(cases)} correct ({100 * correct / len(cases):.0f}%)")
    else:
        parser.print_help()
