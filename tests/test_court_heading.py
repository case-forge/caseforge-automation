import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from documents import court_heading as ch

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PART_IV = "IN THE MATTER OF AN APPLICATION UNDER PART IV OF THE FAMILY LAW ACT 1996"
SECTION_8 = "AND IN THE MATTER OF AN APPLICATION UNDER SECTION 8 OF THE CHILDREN ACT 1989"


def _doc(margin_cm: float = 2):
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, Cm(margin_cm))
    doc.add_paragraph("Body text.")
    return doc


def _heading(doc, **kw):
    args = dict(
        court="Exampletown", order_codes=["NMO"],
        parties=[("Testa Fakename", "Applicant"), ("Rory Fakename", "Respondent")], title="Notice of Acting",
    )
    args.update(kw)
    return ch.build_court_heading(doc, **args)


def test_the_heading_lines_come_in_order_above_the_body_and_never_use_a_table():
    doc = _doc()
    _heading(doc)
    assert [p.text for p in doc.paragraphs] == [
        "IN THE FAMILY COURT SITTING AT EXAMPLETOWN",
        "CASE NO:",
        PART_IV,
        "BETWEEN:",
        "TESTA FAKENAME",
        "Applicant",
        "-and-",
        "RORY FAKENAME",
        "Respondent",
        "NOTICE OF ACTING",
        "Body text.",
    ]
    assert not doc.tables


def test_each_name_is_centred_and_its_role_sits_right_aligned_on_the_line_below_with_no_tab_stops():
    doc = _doc()
    p = _heading(doc)
    names, roles, joiner = (p[4], p[7]), (p[5], p[8]), p[6]
    assert all(n.alignment == WD_ALIGN_PARAGRAPH.CENTER for n in names)
    assert all(r.alignment == WD_ALIGN_PARAGRAPH.RIGHT for r in roles)
    assert joiner.alignment == WD_ALIGN_PARAGRAPH.CENTER and joiner.text == "-and-"
    assert not any(x.paragraph_format.tab_stops for x in p) and not any("\t" in x.text for x in p)


def test_the_case_number_is_on_its_own_line_below_the_court_line():
    doc = _doc()
    court, case = _heading(doc, case_no="zz26f00247")[:2]
    assert court.text == "IN THE FAMILY COURT SITTING AT EXAMPLETOWN" and "\t" not in court.text
    assert case.text == "CASE NO: ZZ26F00247"
    assert case.runs[0].underline and case.runs[0].bold
    assert case.alignment == WD_ALIGN_PARAGRAPH.RIGHT


def test_a_blank_case_number_leaves_room_to_write_it_in():
    blank = _heading(_doc())[1]
    assert blank.text == "CASE NO:" and blank.alignment == WD_ALIGN_PARAGRAPH.RIGHT
    assert round(blank.paragraph_format.right_indent.cm, 2) == ch.CASE_NO_WRITE_SPACE_CM
    numbered = _heading(_doc(), case_no="zz26f00247")[1]
    assert not numbered.paragraph_format.right_indent


def test_the_title_sits_between_heavy_full_width_single_rules():
    title = _heading(_doc())[-1]
    assert not title.paragraph_format.left_indent and not title.paragraph_format.right_indent
    ind = title._p.pPr.find(W + "ind")
    assert ind is not None and ind.get(W + "left") == "0" and ind.get(W + "right") == "0"
    borders = title._p.pPr.find(W + "pBdr")
    assert borders is not None and [b.tag.rsplit("}", 1)[1] for b in borders] == ["top", "bottom"]
    for edge in borders:
        assert (edge.get(W + "val"), edge.get(W + "sz"), edge.get(W + "space"), edge.get(W + "color")) == ("single", "24", "8", "000000")
    assert title.alignment == WD_ALIGN_PARAGRAPH.CENTER


def test_the_gap_above_and_below_and_is_the_same_so_the_respondent_is_never_closer_to_it():
    p = _heading(_doc())
    applicant_role, joiner = p[5], p[6]
    assert applicant_role.paragraph_format.space_after.pt == joiner.paragraph_format.space_after.pt == ch.PARTY_GAP_PT
    assert joiner.paragraph_format.space_before.pt == 0 and p[7].paragraph_format.space_before.pt == 0


def test_matter_lines_carry_the_real_wording_the_first_without_and():
    assert ch.matter_lines(["NMO"]) == [PART_IV]
    assert ch.matter_lines(["CAO"]) == [SECTION_8.removeprefix("AND ")]
    assert ch.matter_lines(["NMO", "OO", "CAO"], ["Ann Example"]) == [
        PART_IV, SECTION_8, "AND IN THE MATTER OF ANN EXAMPLE (MINOR)"]
    assert ch.matter_lines(["PSO"], ["A One", "B Two", "C Three"])[-1] == "AND IN THE MATTER OF A ONE, B TWO AND C THREE (MINORS)"
    assert ch.matter_lines(["SIO"], "A ONE AND B TWO (MINORS)")[-1] == "AND IN THE MATTER OF A ONE AND B TWO (MINORS)"
    assert ch.matter_lines([]) == [] and ch.matter_lines(["NMO"], ["Ann Example"]) == [PART_IV], "no guessed Act, no children without a children order"


def test_minors_text_is_names_only_joined_with_commas_and_and():
    assert ch.minors_text(["Ann Example"]) == "ANN EXAMPLE (MINOR)"
    assert ch.minors_text(["A", "B", "C"]) == "A, B AND C (MINORS)"
    assert ch.minors_text([]) == ""


def test_court_lines():
    assert ch.court_line("Stockport") == "In the Family Court sitting at Stockport"
    assert ch.court_line("Stockport County Court and Family Court") == "In the Family Court sitting at Stockport"
    assert ch.court_line("Central Family Court") == "In the Family Court sitting at Central Family Court"
    assert ch.court_line("IN THE FAMILY COURT SITTING AT PORTSMOUTH") == "In the Family Court sitting at PORTSMOUTH"


def test_a_finder_name_cut_short_at_civil_names_the_place_only():
    assert ch.court_line("Swansea Civil") == "In the Family Court sitting at Swansea"
    assert ch.court_line("Swansea Civil and Family Justice Centre") == "In the Family Court sitting at Swansea"


def test_court_line_names_the_place_only():
    for given in (
        "Worcester Combined Court",
        "Worcester Combined Court Centre",
        "Worcester County Court",
        "Worcester Family Court",
        "Worcester Justice Centre",
        "The Family Court at Worcester Combined Court",
    ):
        assert ch.court_line(given) == "In the Family Court sitting at Worcester", given
    assert ch.court_line("Leeds Combined Court Centre") == "In the Family Court sitting at Leeds"
    assert ch.court_line("Combined Court") == "In the Family Court sitting at Combined Court"


def test_the_real_part_iv_line_is_one_line_at_the_final_margins_and_a_longer_one_wraps():
    doc = _doc(margin_cm=3.17)
    paragraphs = _heading(doc, margins_cm=2.0)
    part_iv = paragraphs[2]
    assert part_iv.text == PART_IV
    assert part_iv.runs[0].font.name == "Arial" and part_iv.runs[0].font.size.pt == 12
    width = (Cm(21) - Cm(4)) / 12700
    assert width < ch.text_width_pt(PART_IV) <= width + ch.MATTER_OVERHANG_PT, "just too long for the text width, within the 0.75 cm overhang"
    assert abs(part_iv.paragraph_format.right_indent.pt + ch.MATTER_OVERHANG_PT) < 0.1, "so it reaches into the margin and stays on one line"
    assert not part_iv.paragraph_format.left_indent
    doc2 = _doc()
    p2 = _heading(doc2, order_codes=["NMO", "CAO"], minors=["Ann Example"])
    section_8 = p2[3]
    assert section_8.text == SECTION_8
    assert ch.text_width_pt(SECTION_8) > width + ch.MATTER_OVERHANG_PT, "longer than the overhang allows"
    assert section_8.paragraph_format.right_indent.pt == 0, "so it wraps inside the margins"


def test_the_margins_argument_sets_the_page_before_measuring():
    doc = _doc(margin_cm=3.17)
    _heading(doc, margins_cm=2.0)
    assert abs(doc.sections[0].left_margin - Cm(2.0)) < 700 and abs(doc.sections[0].right_margin - Cm(2.0)) < 700
    wide = _heading(_doc(margin_cm=3.17))
    assert wide[2].paragraph_format.right_indent.pt == 0



import pytest

from documents import court_of_record
from documents import family_court_names as fcn


@pytest.mark.parametrize("name", [
    "King's Lynn Magistrates' Court and Family Court",
    "KING'S LYNN MAGISTRATES' COURT AND",
    "King’s Lynn Magistrates’ Court and Family Court",
    "In the Family Court sitting at King's Lynn Magistrates' Court and Family Court",
])
def test_a_magistrates_and_family_court_is_printed_by_its_own_place(name):
    line = ch.court_line(name).lower()
    assert "agistrate" not in line
    assert line.startswith("in the family court sitting at king") and line.endswith("lynn")


@pytest.mark.parametrize("name", [
    "Examplebury Magistrates' Court",
    "Examplebury Magistrates Court",
])
def test_a_pure_magistrates_court_is_to_be_confirmed_never_printed(name):
    line = ch.court_line(name)
    assert line == "In the Family Court sitting at [COURT TO BE CONFIRMED]"
    assert "agistrate" not in line


def test_ordinary_courts_are_unchanged():
    assert ch.court_line("Huddersfield") == "In the Family Court sitting at Huddersfield"
    assert ch.court_line("Norwich Combined Court Centre") == "In the Family Court sitting at Norwich"
    assert ch.court_line("Central Family Court") == "In the Family Court sitting at Central Family Court"


def test_every_court_field_goes_through_printable_court():
    assert fcn.printable_court("King's Lynn Magistrates' Court and Family Court") == "King's Lynn Magistrates' Court and Family Court"
    assert fcn.printable_court("Examplebury Magistrates' Court") == fcn.COURT_TO_CONFIRM
    assert fcn.printable_court("Reading") == "Reading"
    assert fcn.printable_court("") == ""


def test_finder_and_filed_papers_never_yield_a_magistrates_venue():
    assert court_of_record.venue_from_finder_name("King's Lynn Magistrates' Court and Family Court") == "King's Lynn"
    assert court_of_record.venue_from_finder_name("King’s Lynn Magistrates’ Court and Family Court") == "King’s Lynn"
    assert court_of_record.venue_from_finder_name("Examplebury Magistrates' Court") == ""
    assert court_of_record.venue_from_finder_name("Reading County Court and Family Court") == "Reading"
    assert court_of_record.extract_court_from_text("IN THE FAMILY COURT AT KING'S LYNN MAGISTRATES' COURT AND") == "King's Lynn"
    assert court_of_record.extract_court_from_text("IN THE FAMILY COURT AT EXAMPLEBURY MAGISTRATES' COURT") == ""
    rows = [{"name": "Examplebury Magistrates' Court"}, {"name": "Norwich Combined Court Centre"}]
    assert court_of_record.first_family_court(rows)["name"] == "Norwich Combined Court Centre"


def test_suggest_court_skips_only_pure_magistrates_courts():
    def finder(postcode, service_area, **kw):
        return {"ok": True, "courts": [{"name": "Examplebury Magistrates' Court"}, {"name": "Reading County Court and Family Court"}]}
    result = court_of_record.suggest_court([("ws", "RG1 1AA")], finder=finder)
    assert result["status"] == "suggested" and result["court"] == "Reading"
    assert result["alternatives"] == []
    only = court_of_record.suggest_court([("ws", "RG1 1AA")], finder=lambda *a, **k: {"ok": True, "courts": [{"name": "X Magistrates' Court"}]})
    assert only["status"] == "tbc"


def test_the_court_is_read_from_the_old_one_line_heading_and_the_new_two_line_heading():
    from documents import court_of_record, placeholder_check

    old = "IN THE FAMILY COURT AT BIRMINGHAM\tCASE NO:\nIN THE MATTER OF PART IV"
    new = "IN THE FAMILY COURT AT BIRMINGHAM\nCASE NO:\nIN THE MATTER OF PART IV"
    assert court_of_record.extract_court_from_text(old) == "Birmingham"
    assert court_of_record.extract_court_from_text(new) == "Birmingham"
    assert placeholder_check.find_placeholders(old) == [] and placeholder_check.find_placeholders(new) == []
    assert placeholder_check.find_placeholders("IN THE FAMILY COURT AT\nCASE NO:\n")


def test_court_line_drops_the_finders_bracketed_tail_and_civil_justice_centre():
    place = "In the Family Court sitting at Manchester"
    assert ch.court_line("Manchester Civil Justice Centre (Civil and Family Courts)") == place
    assert ch.court_line("Manchester County and Family Court") == place
    assert ch.court_line("Manchester Civil and Family Justice Centre") == place


def test_the_nearest_family_court_is_the_court_whatever_the_building():
    rows = [
        {"name": "Colchester Magistrates' Court and Family Court", "distance_miles": 1.2},
        {"name": "Ipswich Magistrates' Court", "distance_miles": 14.9},
        {"name": "Chelmsford Justice Centre", "distance_miles": 21.9},
    ]
    assert court_of_record.first_family_court(rows)["name"] == "Colchester Magistrates' Court and Family Court"
    assert court_of_record.venue_from_finder_name("Colchester Magistrates' Court and Family Court") == "Colchester"

    def finder(postcode, service_area, **kw):
        return {"ok": True, "courts": rows}
    result = court_of_record.suggest_court([("ws", "TE1 1ST")], finder=finder)
    assert result["status"] == "suggested" and result["court"] == "Colchester"
    assert result["alternatives"] == ["Chelmsford Justice Centre"]
    nearer = [rows[1], {"name": "Norwich Combined Court Centre", "distance_miles": 30}, rows[0]]
    assert court_of_record.first_family_court(nearer)["name"] == "Norwich Combined Court Centre"
    lynn = [{"name": "King's Lynn Magistrates' Court and Family Court", "distance_miles": 0.8}, {"name": "Norwich Combined Court Centre", "distance_miles": 40}]
    assert court_of_record.suggest_court([("ws", "TE2 2ST")], finder=lambda *a, **k: {"ok": True, "courts": lynn})["court"] == "King's Lynn"
    county = [{"name": "Reading County Court and Family Court"}, {"name": "Oxford Combined Court Centre"}]
    assert court_of_record.first_family_court(county)["name"] == "Reading County Court and Family Court"


def test_the_three_party_gaps_are_the_same_and_every_heading_line_is_single_spaced():
    doc = _doc()
    paragraphs = _heading(doc)
    texts = [p.text for p in paragraphs]
    first_role, and_line = texts.index("Applicant"), texts.index("-and-")
    respondent_name = texts.index("RORY FAKENAME")
    after = lambda p: p.paragraph_format.space_after.pt
    before = lambda p: p.paragraph_format.space_before.pt
    gap_above = after(paragraphs[first_role]) + before(paragraphs[and_line])
    gap_below = after(paragraphs[and_line]) + before(paragraphs[respondent_name])
    assert gap_above == gap_below == ch.PARTY_GAP_PT
    assert all(p.paragraph_format.line_spacing == 1.0 for p in paragraphs)


def test_every_heading_leaves_clear_space_below_the_title():
    doc = _doc()
    title = _heading(doc)[-1]
    assert title.paragraph_format.space_after.pt >= 24
    assert title.paragraph_format.space_after.pt == ch.TITLE_GAP_PT


def _row(name, miles):
    return {"name": name, "distance_miles": miles}


def test_an_easy_court_as_near_is_chosen_over_a_portal_or_call_first_court():
    pytest.importorskip("onboarding.pipeline.portal_courts")
    assert court_of_record.first_family_court(
        [_row("Telford County Court and Family Court", 23.9), _row("Worcester Combined Court", 24.0)]
    )["name"] == "Worcester Combined Court"
    assert court_of_record.first_family_court(
        [_row("Redditch Magistrates' Court", 0.8), _row("Birmingham Civil and Family Justice Centre", 13.0), _row("Worcester Combined Court", 13.9)]
    )["name"] == "Worcester Combined Court"


def test_a_portal_court_stands_when_no_easy_court_is_near_or_distances_are_missing():
    rows = [_row("Kingston-upon-Hull Combined Court Centre", 18.1), _row("Lincoln County Court and Family Court", 19.7), _row("York County Court and Family Court", 38.0)]
    assert court_of_record.first_family_court(rows)["name"] == "Kingston-upon-Hull Combined Court Centre"
    assert court_of_record.first_family_court(
        [{"name": "Telford County Court and Family Court"}, {"name": "Worcester Combined Court"}]
    )["name"] == "Telford County Court and Family Court"


def test_an_easy_nearest_court_is_kept():
    assert court_of_record.first_family_court(
        [_row("Worcester Combined Court", 5.0), _row("Sampletown Family Court", 5.5)]
    )["name"] == "Worcester Combined Court"


def test_central_family_court_is_named_whole_in_the_heading_and_the_record():
    assert ch.court_line("Central") == "In the Family Court sitting at Central Family Court"
    assert court_of_record.venue_from_finder_name("Central Family Court") == "Central Family Court"
    assert court_of_record.venue_from_finder_name("Worcester Combined Court") == "Worcester"
