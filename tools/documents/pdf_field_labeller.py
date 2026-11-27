#!/usr/bin/env python3
"Identify the fields of a fillable court form from the printed text around them."
from __future__ import annotations

import argparse
import difflib
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import pdfplumber
from pypdf import PdfReader

QUESTION_RE = re.compile(r"^(?:\d{1,2}(?:\.\d{1,2})?[a-z]?\.?|\([a-z0-9]{1,3}\)|Part\s+\d+|Section\s+\w+)\s+\S")
LINE_TOLERANCE = 3.0
SAME_LINE_GAP = 25.0
MAX_LEFT_REACH = 260.0
ABOVE_REACH = 34.0
SIMILAR = 0.6


def _qualified_name(annot) -> str:
    parts: list[str] = []
    node = annot
    while node is not None:
        t = node.get("/T")
        if t is not None:
            parts.append(str(t))
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
    return ".".join(reversed(parts))


def _inherited(annot, key: str):
    node = annot
    while node is not None:
        if key in node:
            return node[key]
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
    return None


def widgets(path: Path | str) -> list[dict[str, Any]]:
    "Every widget: name, page (1-based), box in points from the top-left, kind, states, maxlen."
    reader = PdfReader(str(path))
    out: list[dict[str, Any]] = []
    for page_no, page in enumerate(reader.pages, 1):
        height = float(page.mediabox.height)
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            name = _qualified_name(annot)
            if not name:
                continue
            x0, y0, x1, y1 = (float(v) for v in annot["/Rect"])
            ft = str(_inherited(annot, "/FT") or "")
            flags = int(_inherited(annot, "/Ff") or 0)
            kind = {"/Tx": "text", "/Ch": "choice", "/Sig": "signature"}.get(ft, "")
            states: list[str] = []
            if ft == "/Btn":
                kind = "radio" if flags & (1 << 15) else "button" if flags & (1 << 16) else "checkbox"
                normal = (annot.get("/AP") or {}).get("/N")
                if normal is not None:
                    states = [str(s) for s in normal.get_object().keys() if str(s) != "/Off"]
            maxlen = _inherited(annot, "/MaxLen")
            out.append(
                {
                    "name": name,
                    "page": page_no,
                    "box": [round(min(x0, x1), 1), round(height - max(y0, y1), 1), round(max(x0, x1), 1), round(height - min(y0, y1), 1)],
                    "kind": kind,
                    "states": states,
                    "maxlen": int(maxlen) if maxlen else None,
                    "multiline": bool(flags & (1 << 12)) if kind == "text" else False,
                    "tooltip": str(_inherited(annot, "/TU") or ""),
                }
            )
    out.sort(key=lambda w: (w["page"], round(w["box"][1] / LINE_TOLERANCE), w["box"][0]))
    return out


def _lines(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for word in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        for line in lines:
            if abs(line["top"] - word["top"]) <= LINE_TOLERANCE:
                line["words"].append(word)
                break
        else:
            lines.append({"top": word["top"], "bottom": word["bottom"], "words": [word]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
        line["text"] = " ".join(w["text"] for w in line["words"])
    return sorted(lines, key=lambda l: l["top"])


def _run_ending_at(words: list[dict[str, Any]], x_edge: float) -> str:
    "The contiguous run of words that ends nearest ``x_edge`` (reading right to left)."
    chosen: list[str] = []
    edge = x_edge
    for word in sorted((w for w in words if w["x1"] <= x_edge + 2), key=lambda w: -w["x1"]):
        if edge - word["x1"] > SAME_LINE_GAP or x_edge - word["x0"] > MAX_LEFT_REACH:
            break
        chosen.append(word["text"])
        edge = word["x0"]
    return " ".join(reversed(chosen))


def _run_starting_at(words: list[dict[str, Any]], x_edge: float) -> str:
    chosen: list[str] = []
    edge = x_edge
    for word in sorted((w for w in words if w["x0"] >= x_edge - 2), key=lambda w: w["x0"]):
        if word["x0"] - edge > SAME_LINE_GAP or word["x1"] - x_edge > MAX_LEFT_REACH:
            break
        chosen.append(word["text"])
        edge = word["x1"]
    return " ".join(chosen)


def label_widgets(path: Path | str) -> list[dict[str, Any]]:
    "``widgets`` plus ``left``, ``right``, ``above`` and ``question`` text for each."
    found = widgets(path)
    labelled: list[dict[str, Any]] = []
    with pdfplumber.open(str(path)) as pdf:
        pages = {i: _lines(p.extract_words(keep_blank_chars=False, use_text_flow=False)) for i, p in enumerate(pdf.pages, 1)}
    for w in found:
        x0, top, x1, bottom = w["box"]
        mid = (top + bottom) / 2
        lines = pages.get(w["page"], [])
        band = [word for line in lines for word in line["words"] if word["top"] - LINE_TOLERANCE <= mid <= word["bottom"] + LINE_TOLERANCE]
        left = _run_ending_at(band, x0)
        right = _run_starting_at(band, x1)
        above = ""
        for line in reversed([l for l in lines if l["bottom"] <= top + 2]):
            if top - line["bottom"] > ABOVE_REACH:
                break
            hits = [word for word in line["words"] if word["x1"] >= x0 - 5 and word["x0"] <= x1 + 5]
            if hits:
                above = line["text"] if len(line["text"]) < 140 else " ".join(word["text"] for word in hits)
                break
        question = ""
        for line in reversed([l for l in lines if l["top"] < top - 1]):
            if QUESTION_RE.match(line["text"]):
                question = line["text"][:160]
                break
        labelled.append({**w, "left": left, "right": right, "above": above[:160], "question": question})
    return labelled


def _similar(a: str, b: str) -> bool:
    a, b = re.sub(r"\W+", " ", a).strip().lower(), re.sub(r"\W+", " ", b).strip().lower()
    return a == b or bool(a and b and difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR)


def _signature(w: dict[str, Any]) -> str:
    return " | ".join(x for x in (w["question"], w["above"], w["left"], w["right"]) if x)


def verify(old_pdf: Path | str, new_pdf: Path | str, field_map: dict[str, str]) -> dict[str, Any]:
    "Does each mapped field still sit under the same printed words in the new edition?"
    old = {w["name"]: w for w in label_widgets(old_pdf)}
    new = {w["name"]: w for w in label_widgets(new_pdf)}
    ok: list[str] = []
    changed: list[dict[str, Any]] = []
    missing: list[str] = []
    for key, name in field_map.items():
        if name not in new:
            missing.append(key)
        elif name not in old or _similar(_signature(old[name]), _signature(new[name])):
            ok.append(key)
        else:
            changed.append({"key": key, "field": name, "old": _signature(old[name]), "new": _signature(new[name]), "old_page": old[name]["page"], "new_page": new[name]["page"]})
    return {"same_text": len(ok), "changed": changed, "missing": missing, "unmapped_new_fields": sorted(set(new) - set(old))}


def carry(old_pdf: Path | str, new_pdf: Path | str, output: Path | str, also: dict[str, str] | None = None) -> dict[str, Any]:
    "Copy the values already filled into an older edition of a form (the firm's own details)"
    from documents.pdf_acroform_fill import fill_acroform

    old_values = {k: v.get("/V") for k, v in (PdfReader(str(old_pdf)).get_fields() or {}).items() if v.get("/V") not in (None, "", "/Off")}
    old = {w["name"]: w for w in label_widgets(old_pdf)}
    new = {w["name"]: w for w in label_widgets(new_pdf)}
    facts: dict[str, Any] = {}
    moved: list[dict[str, str]] = []
    unmatched: list[dict[str, str]] = []
    for name, value in old_values.items():
        source = old.get(name)
        target = None
        if name in new and source and _similar(_signature(source), _signature(new[name])):
            target = name
        elif source:
            near = [n for n, w in new.items() if w["kind"] == source["kind"] and _similar(_signature(source), _signature(w))]
            target = near[0] if len(near) == 1 else None
        if target is None:
            unmatched.append({"field": name, "value": str(value)[:60], "context": _signature(source)[:100] if source else ""})
            continue
        facts[target] = True if str(value).startswith("/") else str(value)
        moved.append({"from": name, "to": target})
    facts.update(also or {})
    fill_acroform(template=Path(new_pdf), output=Path(output), facts=facts, flatten=False)
    return {"carried": len(moved), "renamed": [m for m in moved if m["from"] != m["to"]], "unmatched": unmatched}


def stamp(path: Path | str, output: Path | str) -> int:
    "Fill every field with its index (``F12``), tick every box, so a render shows which is which."
    from documents.pdf_acroform_fill import fill_acroform

    facts: dict[str, Any] = {}
    for i, w in enumerate(widgets(path)):
        facts[w["name"]] = True if w["kind"] in {"checkbox", "radio"} else f"F{i}"
    fill_acroform(template=Path(path), output=Path(output), facts=facts, flatten=False)
    return len(facts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("labels")
    p.add_argument("pdf", type=Path)
    p.add_argument("--out", type=Path)
    p = sub.add_parser("stamp")
    p.add_argument("pdf", type=Path)
    p.add_argument("out", type=Path)
    p = sub.add_parser("carry")
    p.add_argument("old", type=Path)
    p.add_argument("new", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--also", action="append", default=[], metavar="FIELD=VALUE", help="Set a field the carry could not match.")
    p = sub.add_parser("verify")
    p.add_argument("old", type=Path)
    p.add_argument("new", type=Path)
    p.add_argument("--map", required=True, help="module:NAME of a dict of friendly key -> field name")
    args = parser.parse_args(argv)
    if args.cmd == "labels":
        text = json.dumps(label_widgets(args.pdf), indent=1, ensure_ascii=False)
        (args.out.write_text(text, encoding="utf-8") if args.out else print(text))
    elif args.cmd == "stamp":
        print(f"stamped {stamp(args.pdf, args.out)} fields")
    elif args.cmd == "carry":
        print(json.dumps(carry(args.old, args.new, args.out, dict(a.split("=", 1) for a in args.also)), indent=1, ensure_ascii=False))
    else:
        module, _, attr = args.map.partition(":")
        print(json.dumps(verify(args.old, args.new, getattr(importlib.import_module(module), attr)), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
