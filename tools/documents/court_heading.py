#!/usr/bin/env python3

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from documents.family_court_names import COURT_TYPE_SUFFIXES as _COURT_TYPE_SUFFIXES
from documents.family_court_names import MFC_TAIL_RE, family_court_place

FONT = "Arial"
SIZE_PT = 12
MATTER_OVERHANG_PT = 21.26
TITLE_RULE_STYLE = "single"
TITLE_RULE_EIGHTHS = 24
TITLE_RULE_SPACE_PT = 8
PARTY_GAP_PT = 27.6
CASE_NO_WRITE_SPACE_CM = 4.0
TITLE_GAP_PT = 30
_BOLD_WIDTHS = {' ': 278, '!': 333, '"': 474, '#': 556, '$': 556, '%': 889, '&': 722, "'": 238, '(': 333, ')': 333, '*': 389, '+': 584, ',': 278, '-': 333, '.': 278, '/': 278, '0': 556, '1': 556, '2': 556, '3': 556, '4': 556, '5': 556, '6': 556, '7': 556, '8': 556, '9': 556, ':': 333, ';': 333, '<': 584, '=': 584, '>': 584, '?': 611, '@': 975, 'A': 722, 'B': 722, 'C': 722, 'D': 722, 'E': 667, 'F': 611, 'G': 778, 'H': 722, 'I': 278, 'J': 556, 'K': 722, 'L': 611, 'M': 833, 'N': 722, 'O': 778, 'P': 667, 'Q': 778, 'R': 722, 'S': 667, 'T': 611, 'U': 722, 'V': 667, 'W': 944, 'X': 667, 'Y': 667, 'Z': 611, '[': 333, '\\': 278, ']': 333, '^': 584, '_': 556, '`': 333, 'a': 556, 'b': 611, 'c': 556, 'd': 611, 'e': 556, 'f': 333, 'g': 611, 'h': 611, 'i': 278, 'j': 278, 'k': 556, 'l': 278, 'm': 889, 'n': 611, 'o': 611, 'p': 611, 'q': 611, 'r': 389, 's': 556, 't': 333, 'u': 611, 'v': 556, 'w': 778, 'x': 556, 'y': 556, 'z': 500, '{': 389, '|': 280, '}': 389, '~': 584, '’': 278, '–': 556}
_DEFAULT_WIDTH = 611


def text_width_pt(text: str, size_pt: int = SIZE_PT) -> float:
    return sum(_BOLD_WIDTHS.get(ch, _DEFAULT_WIDTH) for ch in text) * size_pt / 1000


def court_place(court: str) -> str:
    name = re.sub(r"\s+", " ", str(court or "")).strip()
    name = re.sub(r"(?i)^(?:(?:in\s+)?the\s+)?family\s+court\s+(?:at|sitting\s+at)\s+", "", name)
    name = MFC_TAIL_RE.sub("", name)
    mapped = family_court_place(name)
    if mapped is not None:
        return mapped
    if re.fullmatch(r"(?i)(?:the\s+)?central(?:\s+family\s+court)?", name):
        return "Central Family Court"
    while True:
        bare = re.sub(r"\s*\([^()]*\)$", "", name).strip()
        if bare and bare != name:
            name = bare
            continue
        for suffix in _COURT_TYPE_SUFFIXES:
            stripped = re.sub(rf"(?i)\s+{re.escape(suffix)}$", "", name)
            if stripped != name and stripped:
                name = stripped
                break
        else:
            break
    return name


def court_line(court: str) -> str:
    return f"In the Family Court sitting at {court_place(court)}"


FAMILY_ORDER_CODES = frozenset({"NMO", "OO"})
CHILDREN_ORDER_CODES = frozenset({"CAO", "PSO", "SIO"})
FAMILY_LAW_ACT_LINE = "IN THE MATTER OF AN APPLICATION UNDER PART IV OF THE FAMILY LAW ACT 1996"
CHILDREN_ACT_LINE = "IN THE MATTER OF AN APPLICATION UNDER SECTION 8 OF THE CHILDREN ACT 1989"
_MATTER_PREFIX = "IN THE MATTER OF "


def minors_text(names: Iterable[str]) -> str:
    clean = [re.sub(r"\s+", " ", str(n or "")).strip().upper() for n in names]
    clean = [n for n in dict.fromkeys(clean) if n]
    if not clean:
        return ""
    joined = clean[0] if len(clean) == 1 else ", ".join(clean[:-1]) + " AND " + clean[-1]
    return f"{joined} ({'MINOR' if len(clean) == 1 else 'MINORS'})"


def matter_lines(order_codes: Any, minors: Sequence[str] | str = "") -> list[str]:
    codes = {str(c).strip().upper() for c in (order_codes or ()) if str(c).strip()}
    lines: list[str] = []
    if codes & FAMILY_ORDER_CODES:
        lines.append(FAMILY_LAW_ACT_LINE)
    if codes & CHILDREN_ORDER_CODES:
        lines.append(CHILDREN_ACT_LINE)
        text = minors.strip() if isinstance(minors, str) else minors_text(minors)
        text = re.sub(r"(?i)^(?:and\s+)?in\s+the\s+matter\s+of\s+", "", text).strip().upper()
        if text:
            lines.append(_MATTER_PREFIX + text)
    return [line if i == 0 else "AND " + line for i, line in enumerate(lines)]


def _usable_width_pt(section) -> float:
    return (section.page_width - section.left_margin - section.right_margin) / 12700


def _run(paragraph, text: str, *, bold: bool = True, underline: bool = False, size_pt: int = SIZE_PT, font: str = FONT):
    run = paragraph.add_run(text)
    run.bold = bold
    run.underline = underline
    run.font.name = font
    run.font.size = Pt(size_pt)
    run._r.get_or_add_rPr().get_or_add_rFonts().set(qn("w:hAnsi"), font)
    return run


def _spacing(paragraph, after_pt: float = 6) -> None:
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(after_pt)
    fmt.left_indent = Pt(0)
    fmt.right_indent = Pt(0)
    fmt.first_line_indent = Pt(0)
    fmt.line_spacing = 1.0


def _title_borders(paragraph) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    for edge in ("top", "bottom"):
        line = OxmlElement(f"w:{edge}")
        line.set(qn("w:val"), TITLE_RULE_STYLE)
        line.set(qn("w:sz"), str(TITLE_RULE_EIGHTHS))
        line.set(qn("w:space"), str(TITLE_RULE_SPACE_PT))
        line.set(qn("w:color"), "000000")
        borders.append(line)
    for later in ("w:shd", "w:tabs", "w:suppressAutoHyphens", "w:spacing", "w:ind", "w:contextualSpacing", "w:jc"):
        node = ppr.find(qn(later))
        if node is not None:
            node.addprevious(borders)
            return
    ppr.append(borders)


def build_court_heading(
    doc: Any,
    *,
    court: str,
    case_no: str = "",
    order_codes: Any = (),
    minors: Sequence[str] | str = (),
    parties: Sequence[tuple[str, str]],
    title: str,
    before: Any = None,
    margins_cm: float | tuple[float, float] | None = None,
) -> list[Any]:
    if margins_cm is not None:
        left, right = (margins_cm, margins_cm) if isinstance(margins_cm, (int, float)) else margins_cm
        for section in doc.sections:
            section.left_margin, section.right_margin = Cm(left), Cm(right)
    width = _usable_width_pt(doc.sections[0])
    paragraphs: list[Any] = []
    anchor = before if before is not None else (doc.paragraphs[0] if doc.paragraphs else None)

    def new_paragraph():
        paragraph = anchor.insert_paragraph_before() if anchor is not None else doc.add_paragraph()
        paragraphs.append(paragraph)
        return paragraph

    court_p = new_paragraph()
    _spacing(court_p, after_pt=0)
    _run(court_p, court_line(court).upper(), underline=True)
    case_p = new_paragraph()
    _spacing(case_p)
    case_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(case_p, "CASE NO:", underline=True)
    if str(case_no or "").strip():
        _run(case_p, " " + str(case_no).strip().upper())
    else:
        case_p.paragraph_format.right_indent = Cm(CASE_NO_WRITE_SPACE_CM)

    for text in matter_lines(order_codes, minors):
        p = new_paragraph()
        _spacing(p)
        needed = text_width_pt(text)
        if width < needed <= width + MATTER_OVERHANG_PT:
            p.paragraph_format.right_indent = Pt(-MATTER_OVERHANG_PT)
        _run(p, text, underline=True)

    between = new_paragraph()
    _spacing(between, after_pt=10)
    _run(between, "BETWEEN:", underline=True)

    for i, (name, role) in enumerate(parties):
        if i:
            p = new_paragraph()
            _spacing(p, after_pt=PARTY_GAP_PT)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _run(p, "-and-")
        name_p = new_paragraph()
        _spacing(name_p, after_pt=0)
        name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(name_p, str(name or "").upper())
        role_p = new_paragraph()
        _spacing(role_p, after_pt=PARTY_GAP_PT)
        role_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _run(role_p, str(role or ""))

    title_p = new_paragraph()
    _spacing(title_p, after_pt=TITLE_GAP_PT)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_before = Pt(12)
    _run(title_p, title.upper())
    _title_borders(title_p)
    return paragraphs


def heading_texts(paragraphs: Sequence[Any]) -> list[str]:
    return [p.text for p in paragraphs]
