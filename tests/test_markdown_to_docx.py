from __future__ import annotations

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import pytest
from docx import Document

from documents import markdown_to_docx as m


def test_convert_file_renders_headings_and_bold(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text("# Title\n\n## Section\n\nPlain text with **bold** and *italic* runs.\n")
    dest = tmp_path / "doc.docx"

    m.convert_file(source, dest)

    doc = Document(str(dest))
    texts = [p.text for p in doc.paragraphs if p.text]
    assert "Title" in texts
    assert "Section" in texts
    assert any("Plain text with bold and italic runs" in t for t in texts)


def test_convert_file_renders_pipe_table(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text("| A | B |\n|---|---|\n| 1 | 2 |\n")
    dest = tmp_path / "doc.docx"

    m.convert_file(source, dest)

    doc = Document(str(dest))
    assert len(doc.tables) == 1
    table = doc.tables[0]
    assert [c.text for c in table.rows[0].cells] == ["A", "B"]
    assert [c.text for c in table.rows[1].cells] == ["1", "2"]


def test_convert_file_applies_house_style(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text("Some body text.\n")
    dest = tmp_path / "doc.docx"

    m.convert_file(source, dest)

    doc = Document(str(dest))
    section = doc.sections[0]
    assert section.left_margin == m.LEFT_MARGIN
    assert section.top_margin == m.TOP_MARGIN
    body_run = next(r for p in doc.paragraphs for r in p.runs if r.text.strip())
    assert body_run.font.name == m.FONT_NAME
    assert body_run.font.size == m.FONT_SIZE


def test_convert_file_keeps_signature_block_together(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text(
        "Some closing paragraph.\n\n"
        "SIGNED: ____________________________\n\n"
        "DATE: ____________________________\n\n"
        "NAME: ____________________________\n"
    )
    dest = tmp_path / "doc.docx"

    m.convert_file(source, dest)

    doc = Document(str(dest))
    labelled = [p for p in doc.paragraphs if p.text.strip()]
    signed_idx = next(i for i, p in enumerate(labelled) if p.text.startswith("SIGNED:"))
    date_idx = next(i for i, p in enumerate(labelled) if p.text.startswith("DATE:"))
    assert labelled[signed_idx].paragraph_format.keep_with_next is True
    assert labelled[date_idx].paragraph_format.keep_with_next is True


def test_convert_file_raises_on_pandoc_failure(tmp_path):
    source = tmp_path / "missing.md"
    dest = tmp_path / "doc.docx"

    with pytest.raises(RuntimeError):
        m.convert_file(source, dest)
