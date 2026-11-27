from __future__ import annotations

import sys
from pathlib import Path

import pytest
from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from documents import court_of_record as cor
from documents.docx_template_fill import SIGNATURE_BLOCK_LINES, replace_signature_lines


@pytest.mark.parametrize(
    "finder_name, venue",
    [
        ("Huddersfield County Court and Family Court", "Huddersfield"),
        ("Clerkenwell and Shoreditch County Court and Family Court", "Clerkenwell and Shoreditch"),
        ("Bradford Combined Court Centre", "Bradford"),
        ("Wakefield Civil and Family Justice Centre", "Wakefield"),
        ("East London Family Court", "East London"),
        ("Barnsley Law Courts", "Barnsley"),
        ("Swansea Civil Justice Centre", "Swansea"),
        ("Unfamiliar Tribunal", "Unfamiliar Tribunal"),
    ],
)
def test_venue_from_finder_name(finder_name, venue):
    assert cor.venue_from_finder_name(finder_name) == venue


@pytest.mark.parametrize(
    "finder_name",
    ["Huddersfield County Court and Family Court", "Wakefield Civil and Family Justice Centre", "Swansea Civil Justice Centre", "Barnsley Law Courts"],
)
def test_the_heading_and_the_venue_step_name_the_same_place(finder_name):
    from documents.court_heading import court_line

    assert court_line(finder_name) == f"In the Family Court sitting at {cor.venue_from_finder_name(finder_name)}"


def _fake_finder(result):
    seen = []

    def finder(postcode, area, **kwargs):
        seen.append((postcode, area))
        return result

    finder.seen = seen
    return finder


def test_suggest_court_uses_the_first_valid_postcode_in_priority_order():
    finder = _fake_finder({"ok": True, "nearest_courts": [{"name": "Huddersfield County Court and Family Court", "distance_miles": 0.4}]})
    out = cor.suggest_court([("statement", "no postcode"), ("FL401", "zz99 1zz"), ("C8", "ZZ99 2ZZ")], "domestic-abuse", finder=finder)
    assert out["status"] == "suggested" and out["court"] == "Huddersfield" and out["postcode_source"] == "FL401"
    assert finder.seen == [("ZZ99 1ZZ", "domestic-abuse")]


def test_suggest_court_is_tbc_without_a_postcode_or_a_result():
    assert cor.suggest_court([("statement", "nothing")], finder=_fake_finder({}))["status"] == "tbc"
    assert cor.suggest_court([("FL401", "ZZ99 1ZZ")], finder=_fake_finder({"ok": False, "message": "down"}))["status"] == "tbc"


def test_replace_signature_lines_swaps_signed_and_dated_for_the_house_block():
    doc = Document()
    doc.add_paragraph("Body text")
    doc.add_paragraph("Signed")
    doc.add_paragraph("")
    doc.add_paragraph("Dated")
    assert replace_signature_lines(doc)
    texts = [p.text for p in doc.paragraphs]
    assert texts.count("Signed") == 0 and texts.count("Dated") == 0
    assert [t for t in texts if t in SIGNATURE_BLOCK_LINES] == list(SIGNATURE_BLOCK_LINES)


def test_replace_signature_lines_leaves_a_document_without_them_alone():
    doc = Document()
    doc.add_paragraph("Nothing to sign here")
    assert replace_signature_lines(doc) is False
