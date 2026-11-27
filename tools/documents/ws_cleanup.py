#!/usr/bin/env python3
"Clean a client's witness statement into the firm's own statement template."
from __future__ import annotations

import argparse
import copy
import datetime as dt
import io
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

TOOLS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from docx import Document
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Emu, Pt
from docx.text.paragraph import Paragraph
from lxml import etree

from documents import court_of_record, model_proofread
from documents.court_heading import CHILDREN_ORDER_CODES, build_court_heading, matter_lines
from documents.family_court_names import COURT_TO_CONFIRM, family_court_place
from documents.docx_template_fill import populate_docx_template, remove_block_if_empty

TEMPLATE_PATH = REPO_ROOT / "templates" / "Client Care Letter Template" / "Witness Statement.docx"
PAGE_MARGIN_CM = 2.0
SLOT_TEXT = "[Insert statement of facts]"
EXHIBIT_LIST_TEXT = "[List of exhibits referred to in this statement]"
EXHIBITS_START_MARKER = "{{ExhibitsSectionStart}}"
EXHIBITS_END_MARKER = "{{ExhibitsSectionEnd}}"

RULE_LINE_RE = re.compile(r"^[_\-\u2013\u2014=~\s]{8,}$")
OPENING_RE = re.compile(r"^I,\s+\S")
BODY_START_RE = re.compile(r"^(?:\d+[.)]\s*)?I,\s+\S")
STATE_AS_FOLLOWS_RE = re.compile(r"\bSTATE\s+AS\s+FOLLOWS\b", re.I)
BODY_LINE_SPACING = 2.0
HEADING_BLOCK_PARAS = 18
ANCHOR_RE = re.compile(r"\b(?:\d+(?:st|nd|rd|th)|first|second|third|fourth|fifth|sixth)\s+(?:witness\s+)?statement\s+of\b", re.I)
_ADDRESS_WITHHELD_RE = re.compile(
    r"\baddress(?:es)?\s+(?:is\s+|are\s+|has\s+been\s+|have\s+been\s+)?(?:withheld|not\s+disclosed|confidential|protected)\b|\bwithheld\s+address\b",
    re.I,
)
PREAMBLE_RE = re.compile(r"^\s*I\s*,.*\b(?:state|say|make this statement|declare)\b", re.I)
END_RE = re.compile(r"^\s*(?:statement\s+of\s+truth\b|I\s+believe\s+(?:that\s+)?the\s+facts\b|signed\s*[:.\-_…]|dated\s*[:.\-_…])", re.I)
LITERAL_NUMBER_RE = re.compile(r"^\s*(\d{1,3})[.)]\s+(.*)$", re.S)
LITERAL_SUB_RE = re.compile(r"^\s*\(([a-z]|[ivx]{1,5})\)\s+(.*)$", re.S)
POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)
_OWN_HOME_RE = re.compile(r"(?i)\b(?:I|we)\s+(?:currently\s+|now\s+)?(?:live|lived|reside|resided|am living)\b|\bmy\s+(?:home|address|flat|house|postcode)\b")
_THIRD_PARTY_RE = re.compile(r"(?i)\b(?:he|she|they|his|her|their|respondent|ex|partner|husband|wife|neighbour|friend|mother|father)\b")
EXHIBIT_LABEL_RE = re.compile(r"(?i:exhibit)s?\s+([A-Z]{1,4}[\s/-]?\d{1,3}|[A-Z]\b|\d{1,3}\b)")
EXHIBIT_CAPTION_RE = re.compile(r"(?i:exhibit)\s+([A-Z]{1,4}[\s/-]?\d{1,3}|[A-Z]\b|\d{1,3}\b)\s*[-–—:.]?\s*(.*)")
STRONG_EXHIBIT_RE = re.compile(r"\bexhibit(?:s|ed)?\b", re.I)
WEAK_EXHIBIT_RE = re.compile(r"\b(?:photograph|photo|screenshot|screen shot|picture|image|recording|video|attached|annexed|enclosed)s?\b", re.I)

SIGNING_LINE_RE = re.compile(r"^\s*(?:SIGNED|DATE|NAME)\s*:", re.I)
PARTY_ROLE_WORDS = {"applicant", "respondent", "and", "v", "-v-", "claimant", "defendant"}
PARTY_NAME_MAX_WORDS = 5
PARTY_TABLE_MAX_LINES = 8
_NAME_WORD_RE = re.compile(r"^(?:[A-Z][A-Za-z'’.-]*|[a-z][a-z'’-]*)$")
CHECKER_MODEL = "model proofread"
CHECKER_NONE = "none (the model proofread could not run: spelling not checked)"

MIN_EXHIBIT_LONG_SIDE_PX = 200
MIN_EXHIBIT_SHORT_SIDE_PX = 100
EXHIBIT_MAX_WIDTH_CM = 15.0
EXHIBIT_MAX_HEIGHT_CM = 21.0


def applicant_address_withheld(opening: str) -> bool:
    "True when the applicant's own opening line (\"I, X, of [address withheld], state as follows\")"
    text = " ".join(str(opening or "").split())
    if not text or re.search(r"\brespondent", text, re.I):
        return False
    return bool(_ADDRESS_WITHHELD_RE.search(text))


class CleanupError(RuntimeError):
    "The original could not be safely cleaned; a human should handle it."




@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False


@dataclass
class SourcePara:
    runs: list[Run]
    number: str = ""
    level: int = 0
    heading: bool = False

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class ImageRef:
    blob: bytes
    content_type: str
    width_px: int
    height_px: int
    filename: str
    alt_text: str
    kind: str
    camera: str = ""
    taken: str = ""
    had_gps: bool = False
    label: str = ""
    caption: str = ""
    region: str = "body"
    qualifies: bool = True


@dataclass
class ExhibitScan:
    images: list[ImageRef] = field(default_factory=list)
    ignored_small_images: int = 0
    strong_mentions: int = 0
    weak_mentions: int = 0
    labels_mentioned: list[str] = field(default_factory=list)
    has_exhibits: bool = False
    flags: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "images_found": len(self.images),
            "small_images_ignored": self.ignored_small_images,
            "exhibit_mentions": self.strong_mentions,
            "weak_mentions": self.weak_mentions,
            "labels_mentioned": self.labels_mentioned,
            "has_exhibits": self.has_exhibits,
            "images": [
                {"label": i.label, "kind": i.kind, "size": f"{i.width_px}x{i.height_px}", "camera": i.camera, "taken": i.taken, "gps_stripped": i.had_gps, "region": i.region}
                for i in self.images
            ],
            "flags": self.flags,
        }


@dataclass
class Statement:
    paragraphs: list[SourcePara]
    exhibits: ExhibitScan
    anchor_text: str = ""
    numbering_mode: str = ""
    notes: list[str] = field(default_factory=list)
    edits: list[model_proofread.Edit] = field(default_factory=list)
    applicant_address_withheld: bool = False
    postcodes: list[str] = field(default_factory=list)
    tables: list[tuple[int, Any]] = field(default_factory=list)
    other_postcodes: list[str] = field(default_factory=list)
    court_in_original: str = ""
    matter_lines_in_original: list[str] = field(default_factory=list)
    checker: str = CHECKER_NONE
    spelling_checked: bool = False
    model_check_failures: int = 0
    renumbered: int = 0
    heading_needs_person: bool = False




def _on(el, tag: str) -> bool:
    node = el.find(qn(tag)) if el is not None else None
    if node is None:
        return False
    return node.get(qn("w:val"), "true").lower() not in {"0", "false", "off", "none"}


class _Numbering:
    "Word list numbering, resolved to the literal text it displays."

    def __init__(self, doc) -> None:
        self.abstract: dict[str, dict[int, tuple[str, str, int]]] = {}
        self.num_to_abstract: dict[str, str] = {}
        self.counters: dict[str, list[int]] = {}
        try:
            root = doc.part.numbering_part.element
        except Exception:
            return
        for abs_el in root.findall(qn("w:abstractNum")):
            levels: dict[int, tuple[str, str, int]] = {}
            for lvl in abs_el.findall(qn("w:lvl")):
                fmt = lvl.find(qn("w:numFmt"))
                text = lvl.find(qn("w:lvlText"))
                start = lvl.find(qn("w:start"))
                levels[int(lvl.get(qn("w:ilvl")))] = (
                    fmt.get(qn("w:val")) if fmt is not None else "decimal",
                    text.get(qn("w:val")) if text is not None else "%1.",
                    int(start.get(qn("w:val"))) if start is not None else 1,
                )
            self.abstract[abs_el.get(qn("w:abstractNumId"))] = levels
        for num in root.findall(qn("w:num")):
            ref = num.find(qn("w:abstractNumId"))
            if ref is not None:
                self.num_to_abstract[num.get(qn("w:numId"))] = ref.get(qn("w:val"))

    @staticmethod
    def _numpr(paragraph: Paragraph):
        ppr = paragraph._p.pPr
        numpr = ppr.find(qn("w:numPr")) if ppr is not None else None
        if numpr is None:
            style = paragraph.style
            while style is not None and numpr is None:
                sppr = style.element.pPr
                numpr = sppr.find(qn("w:numPr")) if sppr is not None else None
                style = style.base_style
        if numpr is None:
            return None, 0
        num_id = numpr.find(qn("w:numId"))
        ilvl = numpr.find(qn("w:ilvl"))
        return (
            num_id.get(qn("w:val")) if num_id is not None else None,
            int(ilvl.get(qn("w:val"))) if ilvl is not None else 0,
        )

    @staticmethod
    def _format(value: int, fmt: str) -> str:
        if fmt == "lowerLetter":
            return chr(ord("a") + (value - 1) % 26)
        if fmt == "upperLetter":
            return chr(ord("A") + (value - 1) % 26)
        if fmt in {"lowerRoman", "upperRoman"}:
            pairs = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
            out, n = "", value
            for size, sym in pairs:
                while n >= size:
                    out, n = out + sym, n - size
            return out if fmt == "lowerRoman" else out.upper()
        return str(value)

    def prefix(self, paragraph: Paragraph) -> tuple[str, int]:
        "(literal prefix, level) for a list paragraph, or (\"\", 0)."
        num_id, ilvl = self._numpr(paragraph)
        if not num_id or num_id == "0" or num_id not in self.num_to_abstract:
            return "", 0
        levels = self.abstract.get(self.num_to_abstract[num_id], {})
        if ilvl not in levels:
            return "", 0
        counters = self.counters.setdefault(num_id, [0] * 9)
        if counters[ilvl] == 0:
            counters[ilvl] = levels[ilvl][2]
        else:
            counters[ilvl] += 1
        for deeper in range(ilvl + 1, 9):
            counters[deeper] = 0
        fmt, text, _ = levels[ilvl]
        if fmt == "bullet":
            return "•", ilvl

        def sub(match: re.Match[str]) -> str:
            n = int(match.group(1)) - 1
            level_fmt = levels.get(n, ("decimal", "", 1))[0]
            return self._format(counters[n] or 1, level_fmt)

        return re.sub(r"%(\d)", sub, text), ilvl


def _para_runs(p_el) -> tuple[list[Run], list[Any]]:
    "Runs (text + b/i/u) and the drawing elements of a paragraph, in order."
    runs: list[Run] = []
    drawings: list[Any] = []
    for r in p_el.iter(qn("w:r")):
        if any(a.tag == qn("w:del") for a in r.iterancestors()):
            continue
        rpr = r.find(qn("w:rPr"))
        parts: list[str] = []
        for child in r:
            if child.tag == qn("w:t"):
                parts.append(child.text or "")
            elif child.tag == qn("w:tab"):
                parts.append("\t")
            elif child.tag in (qn("w:br"), qn("w:cr")):
                parts.append("\n")
            elif child.tag == qn("w:noBreakHyphen"):
                parts.append("-")
            elif child.tag in (qn("w:drawing"), qn("w:pict")):
                drawings.append(child)
        text = "".join(parts)
        if text:
            u = rpr.find(qn("w:u")) if rpr is not None else None
            runs.append(
                Run(
                    text,
                    bold=_on(rpr, "w:b"),
                    italic=_on(rpr, "w:i"),
                    underline=u is not None and u.get(qn("w:val"), "single") != "none",
                )
            )
    return _merge_runs(runs), drawings


def _merge_runs(runs: list[Run]) -> list[Run]:
    merged: list[Run] = []
    for run in runs:
        if merged and (merged[-1].bold, merged[-1].italic, merged[-1].underline) == (run.bold, run.italic, run.underline):
            merged[-1] = Run(merged[-1].text + run.text, run.bold, run.italic, run.underline)
        else:
            merged.append(run)
    return merged


def _image_from_drawing(doc, drawing) -> ImageRef | None:
    rid = None
    for blip in drawing.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"):
        rid = blip.get(qn("r:embed"))
    if rid is None:
        for img in drawing.iter("{urn:schemas-microsoft-com:vml}imagedata"):
            rid = img.get(qn("r:id"))
    if rid is None or rid not in doc.part.related_parts:
        return None
    part = doc.part.related_parts[rid]
    blob = part.blob
    alt = ""
    for docpr in drawing.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr"):
        alt = (docpr.get("descr") or docpr.get("name") or "").strip()
    return _describe_image(blob, part.content_type, str(part.partname).rsplit("/", 1)[-1], alt)


def _describe_image(blob: bytes, content_type: str, filename: str, alt: str) -> ImageRef:
    from PIL import Image

    width = height = 0
    camera = taken = ""
    had_gps = False
    kind = "image"
    try:
        with Image.open(io.BytesIO(blob)) as img:
            width, height = img.size
            exif = img.getexif()
            if exif:
                camera = " ".join(str(exif.get(t, "")).strip() for t in (0x010F, 0x0110) if exif.get(t)).strip()
                sub = exif.get_ifd(0x8769) if hasattr(exif, "get_ifd") else {}
                taken = str(sub.get(0x9003) or exif.get(0x0132) or "")
                had_gps = bool(exif.get(0x8825))
            if camera:
                kind = "photograph"
            elif (img.format or "").upper() == "PNG" or "screenshot" in (filename + alt).lower():
                kind = "screenshot-or-graphic"
    except Exception:
        pass
    if "whatsapp" in (filename + alt).lower() and kind == "image":
        kind = "photograph"
    qualifies = max(width, height) >= MIN_EXHIBIT_LONG_SIDE_PX and min(width, height) >= MIN_EXHIBIT_SHORT_SIDE_PX
    return ImageRef(blob, content_type, width, height, filename, alt, kind, camera, taken, had_gps, qualifies=qualifies)


def _strip_gps(image: ImageRef) -> bytes:
    "The image bytes with GPS location removed; unchanged when there is none."
    if not image.had_gps:
        return image.blob
    from PIL import Image

    with Image.open(io.BytesIO(image.blob)) as img:
        exif = img.getexif()
        if 0x8825 in exif:
            del exif[0x8825]
        out = io.BytesIO()
        fmt = (img.format or "JPEG").upper()
        if fmt == "JPEG":
            img.save(out, "JPEG", exif=exif, quality=95, subsampling=0)
        else:
            img.save(out, fmt)
        return out.getvalue()


def _looks_like_heading(para: SourcePara) -> bool:
    text = para.text.strip()
    if not text or len(text.split()) > 12 or text.endswith((".", ",", ";")) and not text.isupper():
        return False
    return all(r.bold for r in para.runs if r.text.strip()) or (text.isupper() and any(c.isalpha() for c in text))


def _is_parties_table(tbl_el, protected: Iterable[str] = ()) -> bool:
    "True for the heading's \"Name / Applicant / and / Name / Respondent\" block set in a table."
    lines = [
        "".join(t.text or "" for t in p.iter(qn("w:t"))).strip()
        for p in tbl_el.iter(qn("w:p"))
    ]
    lines = [l for l in lines if l]
    if not lines or len(lines) > PARTY_TABLE_MAX_LINES:
        return False
    known = {n.strip().lower() for n in protected if n and n.strip()}
    roles = 0
    for line in lines:
        bare = re.sub(r"[\s()\[\]:,]+$|^[\s()\[\]:,]+", "", line).lower()
        if bare in PARTY_ROLE_WORDS:
            roles += 1
            continue
        if bare in known:
            continue
        words = line.split()
        if len(words) > PARTY_NAME_MAX_WORDS or not all(_NAME_WORD_RE.match(w) for w in words):
            return False
    return roles > 0


_MATTER_LINE_RE = re.compile(r"^\s*(?:AND\s+)?IN\s+THE\s+MATTER\b", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"x{3,}|_{3,}|\.{4,}", re.IGNORECASE)


_MINORS_RE = re.compile(r"\(\s*(?:A\s+)?MINORS?\s*\)\s*$", re.IGNORECASE)


def _child_firsts(line: str) -> set[str]:
    "The first names on an \"... IN THE MATTER OF A B, C D AND E F (MINORS)\" line, upper case."
    body = re.sub(r"^\s*(?:AND\s+)?IN\s+THE\s+MATTER\s+OF\s+", "", _MINORS_RE.sub("", line), flags=re.IGNORECASE)
    names = [n.strip() for n in re.split(r",|\bAND\b|&", body, flags=re.IGNORECASE) if n.strip()]
    return {n.split()[0].upper() for n in names}


_CHILDREN_ACT_RE = re.compile(r"CHILDREN\s+ACT", re.IGNORECASE)


def reconcile_matter_lines(original: Sequence[str], record: Sequence[str], order_codes: Iterable[str] = ()) -> tuple[list[str], list[str]]:
    "The heading's matter lines: the original's own, as written (owner ruling, 2026-10-20), except that the line naming"
    lines, notes = [], []
    codes = {str(c).strip().upper() for c in (order_codes or ()) if str(c).strip()}
    record_children = next((r for r in record if _MINORS_RE.search(r)), "")
    no_children_order = bool(codes) and not (codes & CHILDREN_ORDER_CODES) and not record_children
    dropped = kept_unknown = False
    for line in original:
        if no_children_order and (_CHILDREN_ACT_RE.search(line) or _MINORS_RE.search(line)):
            dropped = True
            continue
        if not codes and _CHILDREN_ACT_RE.search(line):
            kept_unknown = True
        if _MINORS_RE.search(line) and record_children:
            if _child_firsts(line) <= _child_firsts(record_children):
                lines.append(record_children)
                continue
            missing = sorted(_child_firsts(line) - _child_firsts(record_children))
            notes.append("The matter record is missing a child named in the original's heading (" + ", ".join(m.title() for m in missing) + "): the original's line is kept; add the child to the record.")
        lines.append(line)
    if dropped:
        notes.append("Children Act line removed: no children order sought.")
    if kept_unknown:
        notes.append("Children Act line kept as written: the orders sought are not recorded.")
    return lines, notes


_CONTINUATION_STOP_RE = re.compile(
    r"^\s*(?:BETWEEN\b|CASE\s*(?:NO|NUMBER)\b|(?:AND\s+)?IN\s+THE\b|AND\s*:?\s*$|\(?\s*(?:\d+(?:st|nd|rd|th)\s+|FIRST\s+|SECOND\s+)?WITNESS\s+STATEMENT|.*\b(?:APPLICANT|RESPONDENT|CLAIMANT|DEFENDANT)\b)",
    re.IGNORECASE,
)
_CONTINUATION_MAX_WORDS = 12


def _is_continuation(line: str, above: str = "") -> bool:
    "A heading line that merely carries on the matter line above it: short, not a sentence, not a heading or party line."
    text = " ".join(line.split())
    if not text or len(text.split()) > _CONTINUATION_MAX_WORDS or text.endswith("."):
        return False
    if _CONTINUATION_STOP_RE.match(text) or ANCHOR_RE.search(text):
        return False
    if text == text.upper() or _MINORS_RE.search(text):
        return True
    return bool(re.search(r"(?:,|\bAND|&)\s*$", above, re.IGNORECASE))


def matter_lines_and_joins(head_text: str) -> tuple[list[str], int]:
    "matter_lines_of, plus how many continuation paragraphs were joined onto their matter line."
    lines: list[str] = []
    joined = 0
    raw = head_text.splitlines()
    i = 0
    while i < len(raw):
        if not _MATTER_LINE_RE.match(raw[i]):
            i += 1
            continue
        line = " ".join(raw[i].split())
        i += 1
        while i < len(raw) and not _MINORS_RE.search(line) and _is_continuation(raw[i], line):
            line += " " + " ".join(raw[i].split())
            joined += 1
            i += 1
        lines.append(line)
    return lines, joined


def matter_lines_of(head_text: str) -> list[str]:
    "The original's \"IN THE MATTER OF ...\" / \"AND IN THE MATTER OF ...\" lines, as written (the heading is the"
    lines, _ = matter_lines_and_joins(head_text)
    return [] if any(_PLACEHOLDER_RE.search(line) for line in lines) else lines


def read_original(path: Path | str, *, protected: Iterable[str] = (), keep_opening: bool = False) -> Statement:
    "Everything below the statement heading and above the statement of truth."
    doc = Document(str(path))
    numbering = _Numbering(doc)
    body = doc.element.body

    entries: list[tuple[str, Any]] = []
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            entries.append(("p", Paragraph(child, doc._body)))
        elif child.tag == qn("w:tbl"):
            entries.append(("tbl", child))

    anchor_index = next(
        (i for i, (kind, item) in enumerate(entries[:60]) if kind == "p" and ANCHOR_RE.search(item.text or "")),
        None,
    )
    if anchor_index is None:
        raise CleanupError("Could not find a '1st witness statement of ...' heading in the first 60 paragraphs; nothing was copied.")
    statement = Statement([], ExhibitScan(), anchor_text=entries[anchor_index][1].text.strip())

    head_text = "\n".join(item.text for kind, item in entries[:anchor_index] if kind == "p")
    statement.court_in_original = court_of_record.extract_court_from_text(head_text)
    statement.matter_lines_in_original = matter_lines_of(head_text)
    if statement.matter_lines_in_original:
        joined = matter_lines_and_joins(head_text)[1]
        if joined:
            statement.notes.append("A matter line in the original was wrapped over several paragraphs; it has been joined into one line. Check the heading reads correctly.")
        if not any("FAMILY LAW ACT" in line.upper() for line in statement.matter_lines_in_original):
            statement.notes.append("The original's matter lines do not mention the Family Law Act 1996; check they fit the application.")

    region = "body"
    raw: list[SourcePara] = []
    after_paras: list[SourcePara] = []
    pending_images: list[tuple[ImageRef, str, int, str]] = []
    tables_skipped = 0
    protected = list(protected)
    started = False
    preamble_postcodes: list[str] = []
    for kind, item in entries[anchor_index + 1 :]:
        if kind == "tbl":
            if _is_parties_table(item, protected):
                continue
            if region == "body" and not any(el.tag in (qn("w:drawing"), qn("w:pict")) for el in item.iter()):
                statement.tables.append((len(raw), copy.deepcopy(item)))
                statement.notes.append("The original has a table in the statement; it is copied across as it stands and is not spell-checked. Check it reads correctly.")
                continue
            tables_skipped += 1
            continue
        runs, drawings = _para_runs(item._p)
        prefix, level = numbering.prefix(item)
        para = SourcePara(runs, number=prefix, level=level)
        text = para.text.strip()
        for drawing in drawings:
            image = _image_from_drawing(doc, drawing)
            if image is not None:
                image.region = region
                pending_images.append((image, region, len(raw) if region == "body" else len(after_paras), text))
        if not text:
            continue
        if not started and RULE_LINE_RE.match(text):
            continue
        if not started and keep_opening and OPENING_RE.match(text):
            statement.notes.append("Kept the statement's own opening 'I, ... live at ...' line; the template's 'state as follows' line is left out.")
            preamble_postcodes = _distinct_postcodes(text)
            statement.applicant_address_withheld = applicant_address_withheld(text)
            started = True
            (raw if region == "body" else after_paras).append(para)
            continue
        if not started and PREAMBLE_RE.match(text):
            statement.notes.append("Dropped the original's opening 'I, ... state as follows' line; the template supplies it (it can carry an address).")
            preamble_postcodes = _distinct_postcodes(text)
            statement.applicant_address_withheld = applicant_address_withheld(text)
            started = True
            continue
        if region == "body" and END_RE.match(text):
            region = "after-statement"
        started = True
        (raw if region == "body" else after_paras).append(para)

    if region == "body":
        statement.notes.append("No statement of truth or signature line was found; copied to the end of the document.")
    if tables_skipped:
        raise CleanupError(f"The original has {tables_skipped} table(s) below the heading; not copied automatically (after the statement of truth, or holding a picture). Handle by hand.")
    if any(el.tag == qn("w:ins") or el.tag == qn("w:del") for el in body.iter(qn("w:ins"), qn("w:del"))):
        statement.notes.append("Tracked changes are present in the original: inserted text was kept, deleted text dropped.")

    body_paras = [p for p in raw]
    for para in body_paras:
        para.heading = not para.number and _looks_like_heading(para)
    if any(p.number for p in body_paras):
        statement.numbering_mode = "original"
    else:
        counter = 0
        literal = 0
        for para in body_paras:
            text = para.text
            m, s = LITERAL_NUMBER_RE.match(text), LITERAL_SUB_RE.match(text)
            if m or s:
                literal += 1
                if m:
                    para.number, para.level, rest = f"{m.group(1)}.", 0, m.group(2)
                else:
                    para.number, para.level, rest = f"({s.group(1)})", 1, s.group(2)
                para.runs = _strip_leading(para.runs, len(text) - len(rest))
        if literal:
            statement.numbering_mode = "literal"
        else:
            for para in body_paras:
                if not para.heading:
                    counter += 1
                    para.number = f"{counter}."
            statement.numbering_mode = "added"
            statement.notes.append("The original had no paragraph numbers; numbered consecutively.")
    if statement.numbering_mode in {"original", "literal"}:
        statement.renumbered = _continue_numbering(body_paras)
        if statement.renumbered:
            statement.notes.append(f"Renumbered {statement.renumbered} paragraph(s) so the numbering continues across headings and list breaks; check any 'paragraph N' cross-references in the text.")
    statement.paragraphs = body_paras

    normalise_order_wording(statement)
    drop_empty_crime_refs(statement)

    for edit_group in _autofix(statement, protected):
        statement.edits.append(edit_group)

    statement.exhibits = scan_exhibits(pending_images, [p.text for p in body_paras], [p.text for p in after_paras])
    statement.postcodes, statement.other_postcodes = _applicant_postcodes(preamble_postcodes, [p.text for p in body_paras])
    if after_paras:
        stray = [p for p in after_paras if not (EXHIBIT_CAPTION_RE.search(p.text) or _looks_like_heading(p) or END_RE.match(p.text.strip()) or _is_signature_residue(p.text))]
        if stray:
            statement.notes.append(f"{len(stray)} paragraph(s) of text after the statement of truth were not copied; check nothing of substance was there.")
    return statement


_PLAIN_NUMBER_RE = re.compile(r"^\d{1,3}\.$")


def _continue_numbering(paras: Sequence[SourcePara]) -> int:
    "Number top-level decimal paragraphs 1, 2, 3 ... straight through, headings included."
    counter = changed = 0
    for para in paras:
        if para.level == 0 and _PLAIN_NUMBER_RE.match(para.number):
            counter += 1
            wanted = f"{counter}."
            if para.number != wanted:
                para.number = wanted
                changed += 1
    return changed


def _is_signature_residue(text: str) -> bool:
    t = text.strip()
    return bool(re.fullmatch(r"[.\-_…\s]*", t)) or bool(re.match(r"(?i)(signed|dated|name)\b", t)) or len(t.split()) <= 4


def _strip_leading(runs: list[Run], count: int) -> list[Run]:
    out: list[Run] = []
    skip = count
    for run in runs:
        if skip >= len(run.text):
            skip -= len(run.text)
            continue
        out.append(Run(run.text[skip:], run.bold, run.italic, run.underline))
        skip = 0
    return out


def _autofix(statement: Statement, protected: Iterable[str]) -> list[model_proofread.Edit]:
    "Proofread the copied text with the guarded model and apply the edits the guard accepts."
    paras = statement.paragraphs
    result = model_proofread.proofread([p.text for p in paras], protected=protected)
    statement.checker = CHECKER_MODEL if result.checked else CHECKER_NONE
    statement.spelling_checked = result.checked
    statement.model_check_failures = result.failures
    if not result.checked:
        statement.notes.append(
            f"Spelling not fully checked: the model could not check {result.failures} paragraph(s), which are left as written. Nobody has checked their spelling."
        )
    for edit in sorted((e for e in result.edits if e.applied), key=lambda e: (e.para, e.start), reverse=True):
        _replace_in_runs(paras[edit.para].runs, edit.start, edit.end, edit.replacement)
    return result.edits


_EMPTY_CRIME_REF_RE = re.compile(
    r"\s*[(\[]\s*crime\s*(?:ref(?:erence)?\.?)(?:\s*(?:no\.?|number))?\s*[:\-\u2013]?\s*"
    r"(?:tbc|tba|to be confirmed|not known|unknown|none|n/?a|\?+|\.{2,}|_+|-+)?\s*[)\]]",
    re.IGNORECASE,
)


def drop_empty_crime_refs(statement: Statement) -> int:
    "Remove each empty crime reference bracket from the statement's paragraphs. Returns how many."
    removed = 0
    for para in statement.paragraphs:
        while True:
            match = _EMPTY_CRIME_REF_RE.search(para.text)
            if not match:
                break
            _replace_in_runs(para.runs, match.start(), match.end(), "")
            removed += 1
    if removed:
        statement.notes.append(f"{removed} empty crime reference bracket(s) in the source were left out: no crime reference is mentioned where there is none.")
    return removed


_SUPPORT_SENTENCE_RE = re.compile(r"in support of my application for\b", re.IGNORECASE)
_NMO_NAME_RE = re.compile(r"non[\s\u2010-\u2013-]*molestation(?=\s+order)", re.IGNORECASE)
_ORDER_NAME_RE = re.compile(
    r"(?:non-molestation|occupation|child arrangements|prohibited steps|specific issue)\s+order(?:s)?\b", re.IGNORECASE
)


def _split_run_at(runs: list[Run], pos: int) -> None:
    "Make ``pos`` a run boundary by splitting the run that spans it."
    offset = 0
    for i, run in enumerate(runs):
        end = offset + len(run.text)
        if offset < pos < end:
            cut = pos - offset
            runs[i : i + 1] = [
                Run(run.text[:cut], run.bold, run.italic, run.underline),
                Run(run.text[cut:], run.bold, run.italic, run.underline),
            ]
            return
        offset = end


def _bold_span(runs: list[Run], start: int, end: int) -> None:
    _split_run_at(runs, start)
    _split_run_at(runs, end)
    offset = 0
    for run in runs:
        if offset >= start and offset + len(run.text) <= end:
            run.bold = True
        offset += len(run.text)


def normalise_order_wording(statement: Statement) -> int:
    "In the sentence \"... in support of my application for <orders>\", write ``Non-Molestation`` hyphenated and"
    changed = 0
    for para in statement.paragraphs:
        match = _SUPPORT_SENTENCE_RE.search(para.text)
        if not match:
            continue
        for _ in range(4):
            tail_start = match.end()
            nmo = next((m for m in _NMO_NAME_RE.finditer(para.text, tail_start) if m.group(0) != "Non-Molestation"), None)
            if nmo:
                _replace_in_runs(para.runs, nmo.start(), nmo.end(), "Non-Molestation")
                continue
            comma = re.compile(r"(?<=[Oo]rder),(?=\s+(?:and|&)\s+(?:an?\s+)?(?:Occupation|Non-Molestation)\s+Order)", re.IGNORECASE).search(para.text, tail_start)
            if comma:
                _replace_in_runs(para.runs, comma.start(), comma.end(), "")
                continue
            break
        tail_start = _SUPPORT_SENTENCE_RE.search(para.text).end()
        sentence_end = para.text.find(".", tail_start)
        sentence_end = len(para.text) if sentence_end < 0 else sentence_end
        for name in list(_ORDER_NAME_RE.finditer(para.text, tail_start, sentence_end)):
            _bold_span(para.runs, name.start(), name.end())
        para.runs = _merge_runs(para.runs)
        changed += 1
    if changed:
        statement.notes.append(f"{changed} 'in support of my application for' sentence(s): order names hyphenated where needed and made bold.")
    return changed


def _replace_in_runs(runs: list[Run], start: int, end: int, replacement: str) -> None:
    pos = 0
    placed = False
    for run in runs:
        run_start, run_end = pos, pos + len(run.text)
        pos = run_end
        if run_end <= start or run_start >= end:
            continue
        local_start, local_end = max(start, run_start) - run_start, min(end, run_end) - run_start
        run.text = run.text[:local_start] + (replacement if not placed else "") + run.text[local_end:]
        placed = True


def _distinct_postcodes(text: str) -> list[str]:
    seen: list[str] = []
    for m in POSTCODE_RE.finditer(text):
        code = f"{m.group(1).upper()} {m.group(2).upper()}"
        if code not in seen:
            seen.append(code)
    return seen


def _applicant_postcodes(preamble: list[str], body_texts: Sequence[str]) -> tuple[list[str], list[str]]:
    "(applicant's postcodes, all others)."
    own: list[str] = list(preamble)
    everything: list[str] = list(preamble)
    for text in body_texts:
        for m in POSTCODE_RE.finditer(text):
            code = f"{m.group(1).upper()} {m.group(2).upper()}"
            if code not in everything:
                everything.append(code)
            window = text[max(0, m.start() - 80) : m.start()]
            if _OWN_HOME_RE.search(window) and not _THIRD_PARTY_RE.search(window) and code not in own:
                own.append(code)
    return own, [c for c in everything if c not in own]




def scan_exhibits(
    pending: Sequence[tuple[ImageRef, str, int, str]],
    body_texts: Sequence[str],
    after_texts: Sequence[str],
) -> ExhibitScan:
    "Are there exhibits, and do the pictures and the text agree?"
    scan = ExhibitScan()
    texts = list(body_texts) + list(after_texts)
    for image, region, idx, para_text in pending:
        if not image.qualifies:
            scan.ignored_small_images += 1
            continue
        caption = ""
        pool = after_texts if region == "after-statement" else body_texts
        for candidate in [para_text] + [pool[j] for j in (idx - 1, idx) if 0 <= j < len(pool)]:
            m = EXHIBIT_CAPTION_RE.search(candidate or "")
            if m:
                image.label, caption = m.group(1).strip(), m.group(2).strip()[:80]
                break
        image.caption = caption
        scan.images.append(image)

    full = "\n".join(texts)
    scan.strong_mentions = len(STRONG_EXHIBIT_RE.findall(full))
    scan.weak_mentions = len(WEAK_EXHIBIT_RE.findall(full))
    for m in EXHIBIT_LABEL_RE.finditer(full):
        label = m.group(1).strip()
        if label not in scan.labels_mentioned:
            scan.labels_mentioned.append(label)

    used = {i.label for i in scan.images if i.label}
    labels = iter([l for l in scan.labels_mentioned if l not in used])
    counter = 0
    for image in scan.images:
        if not image.label:
            nxt = next(labels, None)
            if nxt is None:
                counter += 1
                while str(counter) in used:
                    counter += 1
                nxt = str(counter)
            image.label = nxt

    scan.has_exhibits = bool(scan.images) or scan.strong_mentions > 0
    if scan.strong_mentions and not scan.images:
        scan.flags.append("Exhibits are referred to in the text but no pictures are embedded: they may be separate files or missing. No Exhibits section was added to the returned copy; chase the client.")
    elif scan.images and not scan.strong_mentions:
        scan.flags.append("Pictures are embedded but the text never mentions an exhibit: confirm they are exhibits and not decoration.")
    elif scan.images and scan.labels_mentioned and len(scan.labels_mentioned) != len(scan.images):
        scan.flags.append(f"The text refers to {len(scan.labels_mentioned)} exhibit label(s) but {len(scan.images)} picture(s) are embedded; labels were matched in order of appearance, check them.")
    if any(i.had_gps for i in scan.images):
        scan.flags.append("GPS location data was found in one or more pictures and has been removed from the returned copy.")
    return scan


def exhibit_list_lines(scan: ExhibitScan) -> list[str]:
    if scan.images:
        return [
            f"Exhibit {i.label}: {i.caption or {'photograph': 'photograph', 'screenshot-or-graphic': 'screenshot or image', 'image': 'image'}[i.kind]}"
            + (f" (taken {i.taken.split(' ')[0].replace(':', '-')})" if i.taken else "")
            for i in scan.images
        ]
    return [f"Exhibit {label} (file not embedded in the statement received)" for label in scan.labels_mentioned]




def resolve_court(
    statement: Statement,
    *,
    recorded_court: str = "",
    postcode_sources: Sequence[tuple[str, str]] = (),
    service_area: str = "domestic-abuse",
) -> dict[str, Any]:
    "Court for the heading, most authoritative source first, never invented."
    recorded_court = family_court_place(recorded_court) or recorded_court
    in_original = family_court_place(statement.court_in_original) or statement.court_in_original
    if recorded_court:
        return {"status": "recorded", "court": recorded_court}
    if in_original:
        return {"status": "named_in_statement", "court": in_original}
    sources: list[tuple[str, str]] = []
    if len(statement.postcodes) == 1:
        sources.append(("witness statement", statement.postcodes[0]))
    sources.extend(postcode_sources)
    if not sources and len(statement.postcodes) > 1:
        return {"status": "tbc", "reason": f"{len(statement.postcodes)} candidate applicant postcodes in the statement and none supplied from another source; cannot tell which is the applicant's."}
    result = court_of_record.suggest_court(list(sources), service_area)
    if result.get("status") == "suggested" and result.get("finder_name", "").lower() == "central family court":
        result["note"] = "Central Family Court: confirm the heading wording (it is usually 'IN THE CENTRAL FAMILY COURT')."
    return result




_EDGE_SPACE = " \t\n\r\u00a0"


def tidy_runs(runs: list[Run]) -> list[Run]:
    "The paragraph's runs without the client's stray spacing: no space or line break at either end of the"
    out = [Run(re.sub(r" {2,}", " ", re.sub(r"[ \u00a0]+\n", "\n", r.text)), r.bold, r.italic, r.underline) for r in runs]
    while out and not out[-1].text.strip(_EDGE_SPACE):
        out.pop()
    if out:
        out[-1].text = out[-1].text.rstrip(_EDGE_SPACE)
    while out and not out[0].text.strip(_EDGE_SPACE):
        out.pop(0)
    if out:
        out[0].text = out[0].text.lstrip(_EDGE_SPACE)
    return out


def _make_paragraph(template_ppr, para: SourcePara):
    p = etree.SubElement(etree.Element("dummy"), qn("w:p"))
    ppr = etree.fromstring(etree.tostring(template_ppr)) if template_ppr is not None else etree.Element(qn("w:pPr"))
    if para.number:
        for old in ppr.findall(qn("w:ind")):
            ppr.remove(old)
        ind = etree.SubElement(ppr, qn("w:ind"))
        ind.set(qn("w:left"), str(720 * (para.level + 1)))
        ind.set(qn("w:hanging"), "720")
    p.append(ppr)

    def add_run(text: str, run: Run | None = None) -> None:
        r = etree.SubElement(p, qn("w:r"))
        rpr = etree.SubElement(r, qn("w:rPr"))
        if run is not None:
            for flag, on in (("w:b", run.bold), ("w:i", run.italic)):
                if on:
                    etree.SubElement(rpr, qn(flag))
            if run.underline:
                etree.SubElement(rpr, qn("w:u")).set(qn("w:val"), "single")
        if len(rpr) == 0:
            r.remove(rpr)
        for i, piece in enumerate(text.split("\n")):
            if i:
                etree.SubElement(r, qn("w:br"))
            for j, chunk in enumerate(piece.split("\t")):
                if j:
                    etree.SubElement(r, qn("w:tab"))
                if chunk:
                    t = etree.SubElement(r, qn("w:t"))
                    t.text = chunk
                    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    if para.number:
        add_run(f"{para.number}\t")
    for run in tidy_runs(para.runs):
        add_run(run.text, Run(run.text, bold=run.bold or para.heading, italic=run.italic, underline=run.underline))
    return p


_SUPPORT_RE = re.compile(r"(?i)\bin support of my application\b(.*)")
_BORN_NAME_RE = re.compile(r"\b([A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){0,3})\s*,?\s*(?:who\s+)?(?:was\s+)?born\b")


def orders_in_body(paragraphs: Sequence[SourcePara]) -> set[str]:
    "The orders the client asks for, read from the body's \"in support of my application for ...\" paragraph"
    for para in paragraphs[:6]:
        m = _SUPPORT_RE.search(para.text)
        if not m:
            continue
        text = m.group(1).lower()
        found = set()
        if "non-molestation" in text or "non molestation" in text:
            found.add("NMO")
        if "occupation order" in text:
            found.add("OO")
        if "child arrangements" in text:
            found.add("CAO")
        if "prohibited steps" in text:
            found.add("PSO")
        if "specific issue" in text:
            found.add("SIO")
        return found
    return set()


_LETTER_MARK_RE = re.compile(r"^\s*(?:\(?[a-z]\)|[a-z][.)])\s+")
_ITEM_NAME_RE = re.compile(r"^\s*(?:(?:\(?[a-z]\)|[a-z][.)])\s+)?([A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){0,3})\b")
_CHILDREN_INTRO_RE = re.compile(r"(?i)\b(?:one|two|three|four|five|six|\d)\s+child(?:ren)?\b|\bchild(?:ren)?\b[^.]*\bnamely\b")
_INLINE_ITEM_RE = re.compile(r"(?:^|(?<=[\s:;,]))\(?[a-z][.)]\s+(?=[A-Z])")
_NOT_A_CHILD = {"i", "my", "the", "he", "she", "they", "we", "our", "respondent", "applicant"}
_PLACEHOLDER_NAME_RE = re.compile(
    r"^(?:(?:A|AN|THE)\s+)?(?:CHILD(?:REN)?|MINORS?|KIDS?|NAME|BABY|UNBORN(?:\s+CHILD)?)(?:\s*\d+)?$|^X{2,}$|^(?:TBC|TBA|TBD|UNKNOWN|N/?A|NONE)$|[_.]{3,}",
    re.IGNORECASE,
)


def is_placeholder_name(name: str) -> bool:
    "True for a child's \"name\" that is a placeholder (CHILD, THE CHILDREN, XXX, TBC ...), not a name."
    text = re.sub(r"\s+", " ", _MINORS_RE.sub("", str(name or ""))).strip()
    return not text or bool(_PLACEHOLDER_NAME_RE.search(text)) or bool(re.search(r"(?i)\bx{3,}\b|\bTBC\b", text))


def _is_list_item(para: SourcePara) -> bool:
    return bool(re.fullmatch(r"\(?[a-z]\)|[a-z][.)]", para.number.strip())) or bool(_LETTER_MARK_RE.match(para.text))


def _child_list(paragraphs: Sequence[SourcePara]) -> tuple[int, list[str]]:
    "The body's children paragraph (\"I have N children with the Respondent, namely: a. NAME was born ...\") and its"
    for i, para in enumerate(paragraphs):
        if not _CHILDREN_INTRO_RE.search(para.text):
            continue
        tail = re.split(r"(?i)\bnamely\b", para.text, maxsplit=1)
        items = [seg.strip() for seg in _INLINE_ITEM_RE.split(tail[1])[1:]] if len(tail) == 2 else []
        items = [seg for seg in items if seg]
        for later in paragraphs[i + 1 : i + 13]:
            if not _is_list_item(later):
                break
            items.append(later.text.strip())
        if items or _BORN_NAME_RE.search(para.text):
            return i, items
    return -1, []


def children_in_body(paragraphs: Sequence[SourcePara]) -> str:
    "Children's names from the body's \"I have N children ... namely: a. X was born ..., b. Y ...\" paragraph, as"
    i, items = _child_list(paragraphs)
    if i < 0:
        return ""
    names = [m.group(1).strip() for m in _BORN_NAME_RE.finditer(paragraphs[i].text)]
    for item in items:
        m = _ITEM_NAME_RE.match(item)
        if m:
            names.append(m.group(1).strip())
    keep = [n for n in names if not is_placeholder_name(n) and n.split()[0].lower() not in _NOT_A_CHILD]
    return "; ".join(dict.fromkeys(keep))


_HEADING_PLACEHOLDER_RES = (
    re.compile(r"(?i)\bIN\s+THE\s+MATTER\s+OF\s+(?:(?:A|AN|THE)\s+)?(?:CHILD(?:REN)?|MINORS?)\s*(?:\d+\s*)?\(\s*MINORS?\s*\)"),
    re.compile(r"(?i)\bx{3,}\b"),
    re.compile(r"(?i)\bTBC\b|\bTBA\b"),
    re.compile(r"_{3,}|\.{4,}"),
)


def heading_placeholders(lines: Iterable[str]) -> list[str]:
    "The heading lines that carry a placeholder instead of a fact (``AND IN THE MATTER OF CHILD (MINOR)``, ``THE"
    return [str(line) for line in lines if any(rx.search(str(line or "")) for rx in _HEADING_PLACEHOLDER_RES)]


_MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)"
_WAS_IN_DATE_RE = re.compile(
    rf"\b(?:the\s+respondent|the\s+applicant|he|she|they|[A-Z][a-z]+)\s+was\s+in\s+(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?{_MONTHS}\b(?:\s+\d{{4}})?",
    re.IGNORECASE,
)
_ON_THE_DATE_RE = re.compile(r"\bon\s+(?:the\s+)?\d{1,2}(?:st|nd|rd|th)?\b|\bon\s+(?:the\s+)?\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", re.IGNORECASE)
_NAMELY_STOP_RE = re.compile(r"(?i)\bnamely\.(?=\s*$|\s*\(?[a-z][.)]\s)")


def gaps_for_a_person(paragraphs: Sequence[SourcePara]) -> list[str]:
    "Report lines for words that are plainly missing and only a person can supply: \"The respondent was in April"
    out: list[str] = []

    def label(i: int) -> str:
        return paragraphs[i].number.strip().rstrip(".") or str(i + 1)

    def quote(text: str) -> str:
        text = " ".join(text.split())
        return text if len(text) <= 70 else text[:67] + "..."

    for i, para in enumerate(paragraphs):
        for m in _WAS_IN_DATE_RE.finditer(para.text):
            out.append(f"Paragraph {label(i)}: '{quote(m.group(0))}' reads as if a word is missing after 'was' (left as written; a person decides).")
        if _NAMELY_STOP_RE.search(para.text):
            following = paragraphs[i + 1] if i + 1 < len(paragraphs) else None
            if re.search(r"(?i)namely\.\s*\(?[a-z][.)]\s", para.text) or (following is not None and _is_list_item(following)):
                out.append(f"Paragraph {label(i)}: 'namely.' comes before a list; a colon may be meant (left as written; a person decides).")
    start, items = _child_list(paragraphs)
    for item in items:
        if _ITEM_NAME_RE.match(item) and _ON_THE_DATE_RE.search(item) and not re.search(r"(?i)\bborn\b", item):
            out.append(f"Paragraph {label(start)}: the child list item '{quote(item)}' has a date but no 'was born' (left as written; a person decides).")
    return list(dict.fromkeys(out))


def heading_inputs(statement: Statement, data: Mapping[str, Any]) -> tuple[set[str], list[str], list[str]]:
    "What the heading is built from, as ``(order codes, children's names, notes)``: the orders the body asks for (else"
    notes: list[str] = []
    record_codes = {c.strip().upper() for c in str(data.get("OrderCodes") or "").split(",") if c.strip()}
    body_codes = orders_in_body(statement.paragraphs)
    codes = body_codes or record_codes
    if body_codes and record_codes and body_codes != record_codes:
        notes.append("The heading follows the orders the statement asks for (" + ", ".join(sorted(body_codes)) + "); the matter record says " + ", ".join(sorted(record_codes)) + ". Update the record if the statement is right.")
    record_children = next((r for r in str(data.get("FamilyMatters") or "").splitlines() if _MINORS_RE.search(r)), "")
    record_children = _MINORS_RE.sub("", re.sub(r"^\s*(?:AND\s+)?IN\s+THE\s+MATTER\s+OF\s+", "", record_children, flags=re.I)).strip()
    names = [n.strip() for n in children_in_body(statement.paragraphs).split(";") if n.strip()]
    names = names or [n.strip() for n in re.split(r"\s*,\s*|\s+AND\s+", record_children, flags=re.I) if n.strip()]
    names = [n for n in names if not is_placeholder_name(n)]
    statement.heading_needs_person = bool(codes & CHILDREN_ORDER_CODES) and not names
    if statement.heading_needs_person:
        notes.append("HEADING NEEDS A PERSON: a children order is sought but no child's name was found in the statement or on the record, so the heading has no children line: add the children by hand.")
    if not matter_lines(codes, names):
        notes.append("No order is recorded or asked for in the statement, so the heading has no matter line: add it by hand.")
    return codes, names, notes


def render(statement: Statement, output: Path | str, data: Mapping[str, Any]) -> Path:
    "Fill the template's placeholders, then put the cleaned body and exhibits in."
    output = Path(output)
    doc = Document(str(TEMPLATE_PATH))
    remove_block_if_empty(doc, EXHIBITS_START_MARKER, EXHIBITS_END_MARKER, _emit_exhibits(statement))
    staged = output.with_suffix(".staged.docx")
    doc.save(str(staged))
    try:
        populate_docx_template(staged, output, data)
    finally:
        staged.unlink(missing_ok=True)

    doc = Document(str(output))
    heading_codes, heading_names, heading_notes = heading_inputs(statement, data)
    statement.notes.extend(n for n in heading_notes if n not in statement.notes)
    heading = _court_heading(doc, data, heading_codes, heading_names)
    bad = heading_placeholders(p.text for p in heading)
    if bad:
        output.unlink(missing_ok=True)
        raise CleanupError("The heading would carry a placeholder (" + "; ".join(bad) + "): fix the matter record or the statement.")
    slot =next((p for p in doc.paragraphs if SLOT_TEXT in p.text), None)
    if slot is None:
        raise CleanupError("The template's statement slot was not found.")
    ppr = slot._p.pPr
    held = list(statement.tables)
    for index, para in enumerate(statement.paragraphs):
        while held and held[0][0] <= index:
            slot._p.addprevious(copy.deepcopy(held.pop(0)[1]))
        slot._p.addprevious(_make_paragraph(ppr, para))
    for _, table in held:
        slot._p.addprevious(copy.deepcopy(table))
    slot._p.getparent().remove(slot._p)

    _remove_signing_block(doc)
    if _emit_exhibits(statement):
        list_p = next((p for p in doc.paragraphs if EXHIBIT_LIST_TEXT in p.text), None)
        if list_p is None:
            raise CleanupError("The template's exhibit list slot was not found.")
        last_text = [p for p in doc.paragraphs if p.text.strip()][-1]
        if last_text._p is not list_p._p:
            raise CleanupError("The template's Exhibits section is no longer the last part of the document.")
        lines = exhibit_list_lines(statement.exhibits)
        anchor = list_p._p
        for line in lines:
            new_p = etree.fromstring(etree.tostring(list_p._p))
            for t in new_p.iter(qn("w:t")):
                t.text = line
            anchor.addprevious(new_p)
        anchor.getparent().remove(anchor)
        for image in statement.exhibits.images:
            _exhibit_cover(doc, image)
            picture = doc.add_paragraph()
            picture.paragraph_format.page_break_before = True
            scale = min(EXHIBIT_MAX_WIDTH_CM / max(image.width_px, 1), EXHIBIT_MAX_HEIGHT_CM / max(image.height_px, 1))
            picture.add_run().add_picture(io.BytesIO(_strip_gps(image)), width=Cm(image.width_px * scale), height=Cm(image.height_px * scale))
    _finish_layout(doc, statement)
    _put_client_address(doc, data, statement)
    house_bold(doc)
    _drop_stray_empty_paragraphs(doc)
    _drop_trailing_empty_paragraphs(doc)
    apply_body_spacing(doc)
    apply_page_margins(doc)
    doc.save(str(output))
    return output


def _exhibit_cover(doc, image) -> None:
    "The exhibit's own cover page: \"EXHIBIT <label>\" centred on a page of its own (and the caption beneath"
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.page_break_before = True
    title.paragraph_format.space_before = Pt(240)
    run = title.add_run(f"EXHIBIT {image.label}")
    run.bold = True
    run.font.size = Pt(28)
    if image.caption:
        caption = doc.add_paragraph()
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption.paragraph_format.space_before = Pt(12)
        caption.add_run(image.caption).font.size = Pt(14)


def _court_heading(doc, data: Mapping[str, Any], order_codes: Iterable[str] = (), minors: Sequence[str] = ()) -> list[Any]:
    "Replace the template's heading block (everything down to the title and its rule) with the firm's"
    body = doc.element.body
    blocks = [el for el in body.iterchildren() if el.tag != qn("w:sectPr")]
    title_i = next((i for i, el in enumerate(blocks) if "WITNESS STATEMENT OF" in "".join(el.itertext()).upper()), None)
    if title_i is None:
        raise CleanupError("The template's title was not found.")
    end = title_i + 1
    if end < len(blocks) and set("".join(blocks[end].itertext()).strip()) == {"_"}:
        end += 1
    for el in blocks[:end]:
        body.remove(el)
    client = str(data.get("ClientName") or "").strip()
    respondent = str(data.get("RespondentName") or "").strip()
    client_role = str(data.get("ClientRole") or "Applicant").strip() or "Applicant"
    parties = [(client, client_role)]
    if respondent:
        parties.append((respondent, "Applicant" if client_role.lower() == "respondent" else "Respondent"))
    ordinal = str(data.get("WitnessStatementOrdinal") or "First").strip()
    court = str(data.get("CourtName") or "")
    if heading_placeholders([court]):
        court = COURT_TO_CONFIRM
    return build_court_heading(
        doc,
        court=court,
        order_codes=order_codes,
        minors=minors,
        parties=parties,
        title=f"{ordinal} witness statement of {client}",
        before=doc.paragraphs[0] if doc.paragraphs else None,
        margins_cm=PAGE_MARGIN_CM,
    )


WITHHELD_ADDRESS_PHRASE = "of a withheld address"
_OWN_ADDRESS_RE = re.compile(
    r"^(?P<lead>(?:\d+[.)]\s*)?I,\s+(?P<who>[^,]+?),)\s*(?:(?:live[sd]?|living|resid(?:e|es|ed|ing)|of|from)\b[^\n]*?)?(?P<tail>[,\s]*(?:[A-Za-z ]+ in this matter,\s*)?(?:will\s+say|state|say)\b.*)$",
    re.I | re.S,
)


def _opening_paragraph(doc):
    "The statement's opening \"I, NAME, ...\" line: the first such paragraph below the title."
    paras = doc.paragraphs
    start = next((i for i, p in enumerate(paras[: HEADING_BLOCK_PARAS + 6]) if "WITNESS STATEMENT OF" in p.text.upper()), -1) + 1
    return next((p for p in paras[start : start + 6] if BODY_START_RE.match(p.text.strip())), None)


def _put_client_address(doc, data: Mapping[str, Any], statement: Statement) -> None:
    "The opening line carries the client's own address from the matter record (\"I, NAME, of ADDRESS,"
    opening = _opening_paragraph(doc)
    if opening is None or not opening.runs:
        return
    withheld = bool(data.get("AddressWithheld"))
    address = " ".join(str(data.get("ClientAddress") or "").split())
    if not withheld and not address:
        return
    phrase = WITHHELD_ADDRESS_PHRASE if withheld else f"of {address}"
    text = " ".join(opening.text.split()) if "\n" in opening.text else opening.text
    m = _OWN_ADDRESS_RE.match(text)
    if m:
        new = f"{m['lead']} {phrase}, {m['tail'].lstrip(', ')}"
    else:
        client = str(data.get("ClientName") or "").strip()
        new = text.replace(f"I, {client}, ", f"I, {client}, {phrase}, ", 1)
    new = re.sub(r",\s*,+", ",", new)
    if new == text:
        return
    opening.runs[0].text = new
    for extra in opening.runs[1:]:
        extra.text = ""
    if withheld:
        statement.notes.append("The applicant's address is withheld (C8): the opening line says so and the address is not given.")


def _is_empty(el) -> bool:
    return el.tag == qn("w:p") and not "".join(el.itertext()).strip() and next(el.iter(qn("w:drawing"), qn("w:pict"), qn("w:br")), None) is None


def _drop_stray_empty_paragraphs(doc) -> None:
    "The statement body is double spaced, so it needs no blank paragraphs: none between the title and the opening"
    paras = doc.paragraphs
    title = next((p for p in paras[: HEADING_BLOCK_PARAS + 6] if "WITNESS STATEMENT OF" in p.text.upper()), None)
    if title is None:
        return
    opening = _opening_paragraph(doc)
    for anchor in (title._p, opening._p if opening is not None else None):
        node = anchor.getnext() if anchor is not None else None
        while node is not None and _is_empty(node):
            nxt = node.getnext()
            node.getparent().remove(node)
            node = nxt
    truth = next((p for p in doc.paragraphs if TRUTH_HEADING_RE.match(p.text)), None)
    node = truth._p.getprevious() if truth is not None else None
    while node is not None and _is_empty(node):
        prev = node.getprevious()
        node.getparent().remove(node)
        node = prev


def _emit_exhibits(statement: Statement) -> bool:
    "An exhibits section is written only when pictures are embedded to put in it;"
    return bool(statement.exhibits.images)


def _set_line_spacing(p_el, spacing: float) -> None:
    "Line spacing of one paragraph as a multiple of a line (Word's ``auto`` rule), kept other spacing as it was."
    ppr = p_el.find(qn("w:pPr"))
    if ppr is None:
        ppr = etree.SubElement(p_el, qn("w:pPr"))
        p_el.remove(ppr)
        p_el.insert(0, ppr)
    node = ppr.find(qn("w:spacing"))
    if node is None:
        node = etree.SubElement(ppr, qn("w:spacing"))
        for later in ("w:ind", "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange"):
            nxt = ppr.find(qn(later))
            if nxt is not None:
                ppr.remove(node)
                nxt.addprevious(node)
                break
    node.set(qn("w:line"), str(round(spacing * 240)))
    node.set(qn("w:lineRule"), "auto")


def apply_body_spacing(doc, spacing: float = BODY_LINE_SPACING) -> int:
    "Set the line spacing of the statement's body, from its opening line to the end. The court heading"
    paras = doc.paragraphs
    window = paras[: HEADING_BLOCK_PARAS + 6]
    start = next((i for i, p in enumerate(window) if BODY_START_RE.match(p.text.strip()) or STATE_AS_FOLLOWS_RE.search(p.text)), HEADING_BLOCK_PARAS)
    count = 0
    for para in paras[start:]:
        if next(para._p.iter(qn("w:drawing")), None) is not None:
            continue
        _set_line_spacing(para._p, spacing)
        count += 1
    return count


def _remove_signing_block(doc) -> None:
    "The draft that goes to the client for approval has no SIGNED/NAME/DATE lines."
    lines = [p for p in doc.paragraphs if SIGNING_LINE_RE.match(p.text)]
    if not lines:
        return
    before = lines[0]._p.getprevious()
    if before is not None and before.tag == qn("w:p") and not "".join(before.itertext()).strip():
        before.getparent().remove(before)
    for p in lines:
        p._p.getparent().remove(p._p)


def _drop_trailing_empty_paragraphs(doc) -> None:
    "No blank paragraph after the last line: it can spill onto an empty last page."
    body = doc.element.body
    while True:
        last = [c for c in body.iterchildren() if c.tag != qn("w:sectPr")]
        if not last or last[-1].tag != qn("w:p"):
            return
        p = last[-1]
        ppr = p.find(qn("w:pPr"))
        has_section = ppr is not None and ppr.find(qn("w:sectPr")) is not None
        has_content = "".join(p.itertext()).strip() or next(p.iter(qn("w:drawing"), qn("w:pict"), qn("w:br")), None) is not None
        if has_section or has_content:
            return
        body.remove(p)


TRUTH_RE = re.compile(r"^\s*I\s+believe\s+(?:that\s+)?the\s+facts\b", re.I)
TRUTH_HEADING_RE = re.compile(r"^\s*statement\s+of\s+truth\s*:?\s*$", re.I)


def _signing_line(truth: Paragraph, text: str):
    "One line of the signing block: the statement of truth's own paragraph settings (no list"
    from copy import deepcopy

    from docx.oxml import OxmlElement

    new_p = OxmlElement("w:p")
    if truth._p.pPr is not None:
        ppr = deepcopy(truth._p.pPr)
        for tag in ("w:numPr", "w:pageBreakBefore", "w:sectPr"):
            for el in ppr.findall(qn(tag)):
                ppr.remove(el)
        new_p.append(ppr)
    run = OxmlElement("w:r")
    first = next((r for r in truth.runs if r.text.strip()), None)
    rpr = deepcopy(first._r.rPr) if first is not None and first._r.rPr is not None else OxmlElement("w:rPr")
    for tag in ("w:b", "w:bCs", "w:i", "w:iCs", "w:u", "w:highlight", "w:caps", "w:smallCaps"):
        for el in rpr.findall(qn(tag)):
            rpr.remove(el)
    rpr.insert(0, OxmlElement("w:b"))
    run.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    new_p.append(run)
    return new_p


def add_signing_block(source: Path | str, output: Path | str) -> dict[str, Any]:
    "The signing version of an approved statement: ``source`` (the draft ``clean`` made) with the"
    from documents.docx_template_fill import SIGNATURE_BLOCK_LINES

    doc = Document(str(source))
    _remove_signing_block(doc)
    truths = [p for p in doc.paragraphs if TRUTH_RE.match(p.text)]
    if not truths:
        raise CleanupError("No statement of truth was found, so there is nowhere to put the signing block.")
    truth = truths[-1]
    parent = truth._parent
    anchor = truth._p
    block: list[Paragraph] = []
    for text in SIGNATURE_BLOCK_LINES:
        new_p = _signing_line(truth, text)
        anchor.addnext(new_p)
        anchor = new_p
        block.append(Paragraph(new_p, parent))

    chain = [truth._p]
    el = truth._p.getprevious()
    while el is not None and el.tag == qn("w:p"):
        words = Paragraph(el, parent).text.strip()
        if words and not TRUTH_HEADING_RE.match(words):
            break
        chain.append(el)
        el = el.getprevious()
    for p_el in chain:
        Paragraph(p_el, parent).paragraph_format.keep_with_next = True
    for para in [truth, *block]:
        para.paragraph_format.keep_together = True
    for para in block[:-1]:
        para.paragraph_format.keep_with_next = True
    block[-1].paragraph_format.keep_with_next = False
    _drop_trailing_empty_paragraphs(doc)
    apply_body_spacing(doc)
    after = [c for c in block[-1]._p.itersiblings() if c.tag != qn("w:sectPr")]
    doc.save(str(output))
    return {"output": str(output), "lines": [p.text for p in block], "exhibits_follow": bool(after)}


def apply_page_margins(doc, margin_cm: float = PAGE_MARGIN_CM) -> int:
    "Set every section's four page margins (the human-authored template's own are 3.17/2.54 cm)."
    for section in doc.sections:
        section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = Cm(margin_cm)
    return len(doc.sections)


def _finish_layout(doc, statement: Statement) -> None:
    "Firm layout: one opening line, not two (the heading is already in capitals from the builder)."
    paras = doc.paragraphs
    template_line = next((p for p in paras[: HEADING_BLOCK_PARAS + 6] if STATE_AS_FOLLOWS_RE.search(p.text)), None)
    first_copied = statement.paragraphs[0] if statement.paragraphs else None
    if template_line is not None and first_copied is not None and OPENING_RE.match(first_copied.text.strip()):
        nxt = template_line._p.getnext()
        template_line._p.getparent().remove(template_line._p)
        if nxt is not None and nxt.tag == qn("w:p") and not "".join(nxt.itertext()).strip():
            nxt.getparent().remove(nxt)
        statement.notes.append("The statement already opens with its own 'I, ...' line, so the template's 'state as follows' line was left out.")


def names_in_body(statement: Statement) -> dict[str, str]:
    "The names the statement's body gives, for the heading (the statement wins over the record, owner 2026-11-09):"
    from documents import ws_firm_wording as fw

    respondent = next((n for n in (fw.respondent_named(p.text) for p in statement.paragraphs) if n), "")
    return {"RespondentName": respondent} if respondent else {}


def _keep_format(runs: list[Run], text: str) -> list[Run]:
    "``text`` as one run in the formatting the paragraph already had (a bold heading stays bold); plain when mixed."
    shown = [r for r in runs if r.text.strip()]
    marks = {(r.bold, r.italic, r.underline) for r in shown}
    if len(marks) == 1:
        bold, italic, underline = next(iter(marks))
        return [Run(text, bold=bold, italic=italic, underline=underline)]
    return [Run(text)]


def _bold_support_orders(para) -> None:
    "The order names in an \"in support of my application for ...\" paragraph stay bold (the names only) after the wording is replaced."
    match = _SUPPORT_SENTENCE_RE.search(para.text)
    if not match:
        return
    end = para.text.find(".", match.end())
    end = len(para.text) if end < 0 else end
    for name in list(_ORDER_NAME_RE.finditer(para.text, match.end(), end)):
        _bold_span(para.runs, name.start(), name.end())
    para.runs = _merge_runs(para.runs)




def parties_in_heading(doc) -> dict[str, str]:
    "``{\"Applicant\": NAME, \"Respondent\": NAME}`` from the court heading's BETWEEN: block (each party's name, then"
    out: dict[str, str] = {}
    seen_between = False
    previous = ""
    for p in doc.paragraphs[: HEADING_BLOCK_PARAS + 12]:
        text = " ".join(p.text.split())
        if "WITNESS STATEMENT OF" in text.upper():
            break
        if text.upper().startswith("BETWEEN"):
            seen_between = True
            continue
        if seen_between and text.lower() in {"applicant", "respondent"} and previous:
            out.setdefault(text.title(), previous)
        if text:
            previous = text
    return out


def _body_paragraphs(doc) -> list[Paragraph]:
    "The statement's body in a rendered document: below the title, down to (not including) the statement of truth."
    paras = doc.paragraphs
    start = next((i for i, p in enumerate(paras[: HEADING_BLOCK_PARAS + 12]) if "WITNESS STATEMENT OF" in p.text.upper()), None)
    if start is None:
        return []
    body = []
    for p in paras[start + 1 :]:
        if TRUTH_RE.match(p.text) or TRUTH_HEADING_RE.match(p.text):
            break
        body.append(p)
    return body


def _docx_runs(paragraph) -> list[Any]:
    from docx.text.run import Run as DocxRun

    return [DocxRun(r, paragraph) for r in paragraph._p.iterchildren(qn("w:r"))]


def _docx_split_at(paragraph, pos: int) -> bool:
    "Make ``pos`` a run boundary in a Word paragraph; False when the run there holds a picture (left whole)."
    offset = 0
    for run in _docx_runs(paragraph):
        text = run.text
        end = offset + len(text)
        if offset < pos < end:
            if run._r.xpath(".//w:drawing | .//w:pict"):
                return False
            twin = copy.deepcopy(run._r)
            run._r.addnext(twin)
            cut = pos - offset
            run.text = text[:cut]
            from docx.text.run import Run as DocxRun

            DocxRun(twin, paragraph).text = text[cut:]
            return True
        offset = end
    return True


def _docx_set_bold(paragraph, start: int, end: int, bold: bool) -> None:
    if start >= end or not (_docx_split_at(paragraph, start) and _docx_split_at(paragraph, end)):
        return
    offset = 0
    for run in _docx_runs(paragraph):
        length = len(run.text)
        if length and offset >= start and offset + length <= end:
            run.bold = True if bold else None
        offset += length


def _name_re(name: str) -> re.Pattern[str] | None:
    words = [w for w in str(name or "").split() if w]
    if len(words) < 2:
        return None
    return re.compile(r"(?<![\w'’])" + r"\s+".join(re.escape(w) for w in words) + r"(?![\w])", re.IGNORECASE)


_RESPONDENT_WORD_RE = re.compile(r"\bRespondent\b", re.IGNORECASE)


def house_bold(doc, applicant: str = "", respondent: str = "") -> int:
    "Bold in the statement body, the firm's way: the order names in the \"in support of my application for ...\""
    parties = parties_in_heading(doc)
    patterns = [_name_re(applicant or parties.get("Applicant", "")), _name_re(respondent or parties.get("Respondent", "")), _RESPONDENT_WORD_RE]
    first_seen = [False] * len(patterns)
    changed = 0
    for para in _body_paragraphs(doc):
        text = "".join(r.text for r in _docx_runs(para))
        if not text.strip():
            continue
        shown = [r for r in _docx_runs(para) if r.text.strip()]
        all_bold = bool(shown) and all(r.bold for r in shown)
        spans: list[tuple[int, int, bool]] = []
        support = _SUPPORT_SENTENCE_RE.search(text)
        if support:
            end = text.find(".", support.end())
            end = len(text) if end < 0 else end
            spans += [(m.start(), m.end(), True) for m in _ORDER_NAME_RE.finditer(text, support.end(), end)]
        taken: list[tuple[int, int]] = []
        for k, rx in enumerate(patterns):
            if rx is None:
                continue
            for m in rx.finditer(text):
                if any(m.start() < b and a < m.end() for a, b in taken):
                    continue
                taken.append((m.start(), m.end()))
                if not first_seen[k]:
                    first_seen[k] = True
                    spans.append((m.start(), m.end(), True))
                elif not all_bold:
                    spans.append((m.start(), m.end(), False))
        for start, end, bold in spans:
            _docx_set_bold(para, start, end, bold)
            changed += 1
    return changed


def apply_firm_wording(statement: Statement, data: Mapping[str, Any]) -> None:
    "Put the firm's own wording (the ``ws_firm_wording`` block library) into every recognised boilerplate paragraph."
    from documents import ws_firm_wording as fw

    texts = [p.text for p in statement.paragraphs]
    asked = next((a for a in (fw.orders_asked(t) for t in texts) if a), [])
    codes = asked or fw.codes_of(data.get("OrderCodes"))
    kind = fw.children_kind(texts, str(data.get("FamilyMatters") or ""))
    for para, result in zip(statement.paragraphs, fw.apply_blocks(texts, codes, kind)):
        if result.changed:
            para.runs = _keep_format(para.runs, result.text)
            _bold_support_orders(para)


def clean(
    original: Path | str,
    output: Path | str,
    data: Mapping[str, Any],
    *,
    protected: Iterable[str] = (),
    recorded_court: str = "",
    postcode_sources: Sequence[tuple[str, str]] = (),
    service_area: str = "domestic-abuse",
    keep_opening: bool = False,
) -> dict[str, Any]:
    "Read, clean and render; returns the report. The original is only read."
    protected = list(protected) + [str(data.get(k) or "") for k in ("ClientName", "RespondentName")]
    statement = read_original(original, protected=protected, keep_opening=keep_opening)
    court = resolve_court(statement, recorded_court=recorded_court, postcode_sources=postcode_sources, service_area=service_area)
    payload = dict(data)
    body_names = names_in_body(statement)
    if body_names.get("RespondentName"):
        payload["RespondentName"] = body_names["RespondentName"]
    if court.get("court") and not payload.get("CourtName"):
        payload["CourtName"] = court["court"]
    if not payload.get("CourtName"):
        payload["CourtName"] = COURT_TO_CONFIRM
    payload.setdefault("CurrentDate", "")
    payload["AddressWithheld"] = not keep_opening and not str(payload.get("ClientAddress") or "").strip()
    apply_firm_wording(statement, payload)
    gaps = gaps_for_a_person(statement.paragraphs)
    render(statement, output, payload)
    applied = [e for e in statement.edits if e.applied]
    skipped = [e for e in statement.edits if not e.applied]
    return {
        "output": str(output),
        "anchor": statement.anchor_text,
        "paragraphs_copied": len(statement.paragraphs),
        "numbering": statement.numbering_mode,
        "spelling_applied": [{"from": e.before or e.original, "to": e.after or e.replacement, "para": e.label} for e in applied],
        "spelling_left_for_review": [{"word": e.before or e.original, "why": e.reason, "para": e.label, "suggestion": e.after or e.replacement} for e in skipped],
        "checker": statement.checker,
        "spelling_checked": statement.spelling_checked,
        "model_check_failures": statement.model_check_failures,
        "court": court,
        "applicant_address_withheld": statement.applicant_address_withheld,
        "applicant_postcode_found": [p.split(" ")[0] for p in statement.postcodes],
        "other_postcodes_ignored": [p.split(" ")[0] for p in statement.other_postcodes],
        "exhibits": statement.exhibits.summary(),
        "heading_needs_person": statement.heading_needs_person,
        "for_a_person": gaps,
        "notes": statement.notes,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("original", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--client", required=True)
    parser.add_argument("--respondent", default="")
    parser.add_argument("--role", default="Applicant")
    parser.add_argument("--reference", default="")
    parser.add_argument("--matters", default="", help="FamilyMatters line under the case number.")
    parser.add_argument("--ordinal", default="First")
    parser.add_argument("--court", default="", help="Court already recorded for the matter.")
    parser.add_argument("--postcode-source", action="append", default=[], metavar="NAME=POSTCODE", help="Fallback postcode, in priority order (repeatable).")
    parser.add_argument("--service-area", default="domestic-abuse", choices=["domestic-abuse", "childcare-arrangements"])
    parser.add_argument("--protect", action="append", default=[], help="Extra name never to spell-correct (repeatable).")
    args = parser.parse_args(argv)
    sources = [tuple(item.split("=", 1)) for item in args.postcode_source]
    data = {
        "ClientName": args.client,
        "ClientRole": args.role,
        "RespondentName": args.respondent,
        "InternalCaseReferenceNumber": args.reference,
        "FamilyMatters": args.matters,
        "WitnessStatementOrdinal": args.ordinal,
    }
    try:
        report = clean(args.original, args.output, data, protected=args.protect, recorded_court=args.court, postcode_sources=sources, service_area=args.service_area)
    except CleanupError as exc:
        print(f"ws_cleanup: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
