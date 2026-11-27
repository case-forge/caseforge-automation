#!/usr/bin/env python3
"Documenso-ready forms, built from Markdown sources."

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = REPO_ROOT / "templates" / "New Client Templates" / "Documenso Forms"

TOKEN = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
PAGE_BREAK = "<!-- page -->"
FIELD_TYPES = {"TEXT", "DROPDOWN", "SIGNATURE", "DATE", "NAME", "EMAIL", "NUMBER", "CHECKBOX"}

ROW_MM = 7.2
LINE_MM = 5.6
SIGNATURE_MM = 14.0

SERIF = '"Times New Roman", "Liberation Serif", Times, serif'
CSS = """
@page { size: 210mm 297mm; margin: 0 }
* { box-sizing: border-box }
html, body { margin: 0; padding: 0 }
body { font-family: SERIF; font-size: BODYpt; line-height: 1.15; color: #000 }
section.page { width: 210mm; height: 297mm; padding: 25.4mm 25.4mm 20mm; overflow: hidden; page-break-after: always }
section.page:last-child { page-break-after: auto }
div[data-custom-style] p { margin: 0 }
[data-custom-style="Firm Name"] { font: bold 28pt "Bodoni MT", "Bodoni 72", Didot, SERIF; text-align: center; line-height: 1.1 }
[data-custom-style="Firm Address"] { text-align: center; font-size: 12pt; text-decoration: underline }
[data-custom-style="Firm Regulation"] { text-align: center; font: bold 8pt Arial, "Liberation Sans", sans-serif; margin-bottom: 5mm }
[data-custom-style="Form Title"] { font-size: 20pt; font-weight: bold; text-decoration: underline; margin: 4mm 0 4mm }
[data-custom-style="Form Title Centre"] { font-size: 20pt; font-weight: bold; text-decoration: underline; text-align: center; margin: 0 0 8mm }
p { margin: 0 0 4.2mm }
table { border-collapse: collapse; width: 100%; table-layout: fixed; margin: 0 0 3mm }
td { border: 0; padding: LABELPADmm 2mm 0 0; vertical-align: top }
td.has-slot { padding: 0; border-bottom: 0.25mm solid #000 }
.slot { display: block; margin: 0 0.4mm 0.4mm }
.slot.inline { display: inline-block; width: 80mm; margin: 0 0 0 2mm; vertical-align: bottom }
.hint { display: block; font-size: 8.5pt; font-style: italic; line-height: 1.2; padding: 0.6mm 0 0.8mm }
.underline { text-decoration: underline }
""".replace("SERIF", SERIF)


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise SystemExit("source is missing YAML front matter")
    end = text.index("\n---\n", 4)
    return yaml.safe_load(text[4:end]) or {}, text[end + 5 :].lstrip("\n")


def validate(meta: dict[str, Any], body: str, name: str) -> dict[str, dict[str, Any]]:
    fields = meta.get("fields") or {}
    for key, spec in fields.items():
        if spec.get("type") not in FIELD_TYPES:
            raise SystemExit(f"{name}: field {key!r} has unknown type {spec.get('type')!r}")
        if spec["type"] == "DROPDOWN" and not spec.get("options"):
            raise SystemExit(f"{name}: dropdown {key!r} has no options")
    used = TOKEN.findall(body)
    undefined = sorted(set(used) - set(fields))
    unused = sorted(set(fields) - set(used))
    dupes = sorted({k for k in used if used.count(k) > 1})
    if undefined or unused or dupes:
        raise SystemExit(f"{name}: undefined tokens {undefined}, unused fields {unused}, repeated tokens {dupes}")
    return fields


def slot_height_mm(spec: dict[str, Any]) -> float:
    if spec["type"] == "SIGNATURE":
        return SIGNATURE_MM
    return ROW_MM + (int(spec.get("lines", 1)) - 1) * LINE_MM


def option_hint(spec: dict[str, Any]) -> str:
    return " · ".join(str(o) for o in spec["options"])




def _html_tokens(chunk: str, fields: dict[str, dict[str, Any]]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        spec = fields[key]
        css_class = "slot inline" if spec.get("inline") else "slot"
        slot = f'<span class="{css_class}" data-key="{key}" style="height:{slot_height_mm(spec):.1f}mm"></span>'
        if spec["type"] == "DROPDOWN":
            slot += f'<span class="hint">{html.escape(option_hint(spec))}</span>'
        return slot

    return TOKEN.sub(repl, chunk)


def _pandoc(args: list[str], stdin: str) -> str:
    result = subprocess.run(["pandoc", *args], input=stdin, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise SystemExit(f"pandoc failed: {result.stderr.strip()}")
    return result.stdout


def _css(body_pt: float) -> str:
    label_pad = max(0.0, ROW_MM - 0.8 - body_pt * 1.15 * 0.3528)
    return CSS.replace("BODYpt", f"{body_pt:g}pt").replace("LABELPAD", f"{label_pad:.2f}")


def build_html(body: str, fields: dict[str, dict[str, Any]], title: str, body_pt: float) -> str:
    sections = []
    for chunk in body.split(PAGE_BREAK):
        fragment = _pandoc(
            ["-f", "markdown+pipe_tables+raw_html", "-t", "html", "--columns=20"], _html_tokens(chunk, fields)
        )
        sections.append(f'<section class="page">{fragment}</section>')
    return (
        f'<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
        f"<style>{_css(body_pt)}</style></head><body>{''.join(sections)}</body></html>"
    )


def field_meta(spec: dict[str, Any]) -> dict[str, Any]:
    kind = spec["type"]
    base: dict[str, Any] = {"type": kind.lower(), "label": spec.get("label", ""), "fontSize": spec.get("font_size", 12)}
    if kind == "TEXT":
        base.update(required=bool(spec.get("required")), textAlign="left")
        if spec.get("placeholder"):
            base["placeholder"] = spec["placeholder"]
        if spec.get("chars"):
            base["characterLimit"] = int(spec["chars"])
    elif kind == "DROPDOWN":
        base.update(
            required=bool(spec.get("required")),
            values=[{"value": str(o)} for o in spec["options"]],
        )
    return base


def render_pdf(html_text: str, pdf_path: Path, fields: dict[str, dict[str, Any]], name: str) -> list[dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    measure = """() => {
      document.querySelectorAll('td').forEach(td => { if (td.querySelector('.slot')) td.classList.add('has-slot'); });
      return [...document.querySelectorAll('section.page')].map(sec => {
        const r = sec.getBoundingClientRect();
        return {
          overflow: sec.scrollHeight > sec.clientHeight + 1,
          slots: [...sec.querySelectorAll('.slot')].map(s => {
            const b = s.getBoundingClientRect();
            const host = s.parentElement.getBoundingClientRect();
            return {key: s.dataset.key, inline: s.classList.contains('inline'),
                    inside: b.top >= host.top - 0.5 && b.bottom <= host.bottom + 0.5, x: (b.left - r.left) / r.width * 100, y: (b.top - r.top) / r.height * 100,
                    w: b.width / r.width * 100, h: b.height / r.height * 100};
          }),
        };
      });
    }"""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 900, "height": 1200})
        page.set_content(html_text)
        page.emulate_media(media="print")
        pages = page.evaluate(measure)
        for index, info in enumerate(pages, 1):
            for slot in info["slots"]:
                if slot["inline"] and not slot["inside"]:
                    raise SystemExit(f"{name}: inline field {slot['key']!r} does not sit on its own text line")
            if info["overflow"]:
                raise SystemExit(f"{name}: page {index} overflows one A4 page; split it with {PAGE_BREAK} or trim it")
        page.pdf(path=str(pdf_path), width="210mm", height="297mm", print_background=True, margin=dict(top="0", bottom="0", left="0", right="0"))
        browser.close()

    from pypdf import PdfReader

    if len(PdfReader(str(pdf_path)).pages) != len(pages):
        raise SystemExit(f"{name}: PDF has a different page count than the {len(pages)} authored pages")

    out = []
    for page_no, info in enumerate(pages, 1):
        for slot in info["slots"]:
            spec = fields[slot["key"]]
            out.append(
                {
                    "key": slot["key"],
                    "type": spec["type"],
                    "page": page_no,
                    "positionX": round(slot["x"], 3),
                    "positionY": round(slot["y"], 3),
                    "width": round(slot["w"], 3),
                    "height": round(slot["h"], 3),
                    "fieldMeta": field_meta(spec),
                }
            )
    return out



DOCX_MARK = "⟦{}⟧"
DOCX_MARK_RE = re.compile(r"⟦([a-z0-9_]+)⟧")
PAGE_BREAK_OPENXML = '```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```\n'


def _reference_docx(path: Path, body_pt: float) -> None:
    from docx import Document
    from docx.enum.style import WD_STYLE_TYPE
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    subprocess.run(["pandoc", "-o", str(path), "--print-default-data-file", "reference.docx"], check=True, timeout=120)
    doc = Document(str(path))

    def set_font(style: Any, name: str, size: float, bold: bool | None = None, underline: bool | None = None) -> None:
        style.font.name = name
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        if bold is not None:
            style.font.bold = bold
        if underline is not None:
            style.font.underline = underline
        fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
            fonts.set(qn(f"w:{attr}"), name)
        for attr in ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme"):
            if fonts.get(qn(f"w:{attr}")) is not None:
                del fonts.attrib[qn(f"w:{attr}")]

    for style in doc.styles:
        if style.type == WD_STYLE_TYPE.PARAGRAPH:
            set_font(style, "Times New Roman", body_pt)
    for name in ("Normal", "Body Text", "First Paragraph", "Compact"):
        pf = doc.styles[name].paragraph_format
        pf.space_before, pf.line_spacing = Pt(0), 1.0
        pf.space_after = Pt(0 if name in ("Normal", "Compact") else 12)

    def custom(name: str, font: str, size: float, *, bold=False, underline=False, align=WD_ALIGN_PARAGRAPH.LEFT, before=0, after=0):
        style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style.base_style = doc.styles["Normal"]
        set_font(style, font, size, bold, underline)
        style.paragraph_format.alignment = align
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)

    custom("Firm Name", "Bodoni MT", 28, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    custom("Firm Address", "Times New Roman", 12, underline=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    custom("Firm Regulation", "Arial", 8, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=12)
    custom("Form Title", "Times New Roman", 20, bold=True, underline=True, before=12, after=12)
    custom("Form Title Centre", "Times New Roman", 20, bold=True, underline=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=18)

    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = Cm(2.54)
    doc.save(str(path))


def _cell_borders(cell: Any, **edges: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    for old in tc_pr.findall(qn("w:tcBorders")):
        tc_pr.remove(old)
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), edges.get(edge, "nil"))
        if edge in edges:
            el.set(qn("w:sz"), "4")
            el.set(qn("w:color"), "000000")
        borders.append(el)
    tc_pr.append(borders)


def _postprocess_docx(path: Path, fields: dict[str, dict[str, Any]], body_pt: float) -> None:
    from docx import Document
    from docx.enum.table import WD_ROW_HEIGHT_RULE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm, Pt

    doc = Document(str(path))
    for table in doc.tables:
        tbl_pr = table._tbl.tblPr
        for old in tbl_pr.findall(qn("w:tblBorders")):
            tbl_pr.remove(old)
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:val"), "nil")
            borders.append(el)
        tbl_pr.append(borders)
        for row in table.rows:
            keys: list[str] = []
            for cell in row.cells:
                match = DOCX_MARK_RE.fullmatch(cell.text.strip())
                if not match:
                    _cell_borders(cell)
                    continue
                key = match.group(1)
                keys.append(key)
                spec = fields[key]
                para = cell.paragraphs[0]
                for run in para.runs:
                    run.text = ""
                run = para.runs[0] if para.runs else para.add_run()
                if spec["type"] == "DROPDOWN":
                    run.text = "  ".join(f"\u2610 {o}" for o in spec["options"])
                    run.font.size = Pt(9)
                elif spec.get("placeholder"):
                    run.text = spec["placeholder"]
                    run.font.size = Pt(9)
                    run.font.italic = True
                _cell_borders(cell, bottom="single")
            if keys:
                row.height = Mm(max(slot_height_mm(fields[k]) for k in keys) + 1)
                row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    doc.save(str(path))


def render_docx(body: str, fields: dict[str, dict[str, Any]], docx_path: Path, body_pt: float) -> None:
    def mark(m: re.Match[str]) -> str:
        return "\\_" * 18 if fields[m.group(1)].get("inline") else DOCX_MARK.format(m.group(1))

    chunks = [TOKEN.sub(mark, c) for c in body.split(PAGE_BREAK)]
    md = ("\n\n" + PAGE_BREAK_OPENXML + "\n").join(chunks)
    with tempfile.TemporaryDirectory() as tmp:
        ref = Path(tmp) / "reference.docx"
        _reference_docx(ref, body_pt)
        _pandoc(
            ["-f", "markdown+pipe_tables+raw_attribute", "-t", "docx", "--columns=20", f"--reference-doc={ref}", "-o", str(docx_path)],
            md,
        )
    _postprocess_docx(docx_path, fields, body_pt)




def build(source: Path) -> None:
    meta, body = split_front_matter(source.read_text(encoding="utf-8"))
    name = source.stem
    fields = validate(meta, body, name)
    title = meta.get("title", name)
    body_pt = float(meta.get("body_pt", 12))
    html_text = build_html(body, fields, title, body_pt)
    pdf_path = source.with_suffix(".pdf")
    placed = render_pdf(html_text, pdf_path, fields, name)
    render_docx(body, fields, source.with_suffix(".docx"), body_pt)
    manifest = {
        "template": (meta.get("documenso") or {}).get("title", title),
        "source": source.name,
        "pdf": pdf_path.name,
        "pages": max(f["page"] for f in placed),
        "recipient": {"role": "SIGNER", "placeholderName": "Client"},
        "fields": placed,
    }
    source.with_suffix(".fields.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{name}: {len(placed)} fields on {manifest['pages']} page(s) -> .docx .pdf .fields.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("sources", nargs="*", type=Path, help="Markdown sources (default: every .md in the Documenso Forms folder)")
    args = parser.parse_args(argv)
    sources = args.sources or sorted(DEFAULT_SRC.glob("*.md"))
    if not sources:
        parser.error(f"no sources found in {DEFAULT_SRC}")
    for source in sources:
        build(source)
    return 0


if __name__ == "__main__":
    sys.exit(main())
