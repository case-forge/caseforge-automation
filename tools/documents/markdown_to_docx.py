#!/usr/bin/env python3
"Render a plain CaseForge house-style markdown document to .docx via pandoc."

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.shared import Emu, Pt, RGBColor

FONT_NAME = "Arial"
FONT_SIZE = Pt(12)
LEFT_MARGIN = Emu(1143000)
TOP_MARGIN = Emu(914400)
FONT_COLOR = RGBColor(0, 0, 0)
HEADING_SPACE_BEFORE = Pt(6)
HEADING_SPACE_AFTER = Pt(0)
BODY_SPACE_BEFORE = Pt(0)
BODY_SPACE_AFTER = Pt(3)

_SIGNATURE_LABEL_RE = re.compile(r"^(SIGNED|DATE|NAME):", re.IGNORECASE)


def _apply_house_style(doc: Document) -> None:
    section = doc.sections[0]
    section.left_margin = LEFT_MARGIN
    section.right_margin = LEFT_MARGIN
    section.top_margin = TOP_MARGIN
    section.bottom_margin = TOP_MARGIN
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            run.font.name = FONT_NAME
            run.font.size = FONT_SIZE
            run.font.color.rgb = FONT_COLOR
        is_heading = paragraph.style.name.startswith(("Heading", "Title"))
        pf = paragraph.paragraph_format
        pf.space_before = HEADING_SPACE_BEFORE if is_heading else BODY_SPACE_BEFORE
        pf.space_after = HEADING_SPACE_AFTER if is_heading else BODY_SPACE_AFTER
        pf.line_spacing = 1.0
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.name = FONT_NAME
                        run.font.size = FONT_SIZE
                        run.font.color.rgb = FONT_COLOR


def _keep_signature_block_together(doc: Document) -> None:
    "Force the trailing SIGNED:/NAME:/DATE: block onto one page."
    paragraphs = doc.paragraphs
    label_indices = [i for i, p in enumerate(paragraphs) if _SIGNATURE_LABEL_RE.match(p.text.strip())]
    if len(label_indices) < 2:
        return
    start = max(0, label_indices[0] - 1)
    end = label_indices[-1]
    for idx in range(start, end):
        paragraphs[idx].paragraph_format.keep_with_next = True


def convert_file(source: Path, destination: Path) -> None:
    result = subprocess.run(
        ["pandoc", str(source), "-o", str(destination), "--standalone"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pandoc failed ({result.returncode}): {result.stderr.strip()}")

    doc = Document(str(destination))
    _apply_house_style(doc)
    _keep_signature_block_together(doc)
    doc.save(str(destination))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Source .md file")
    parser.add_argument("destination", type=Path, help="Output .docx path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    convert_file(args.source, args.destination)
    print(f"Wrote {args.destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
