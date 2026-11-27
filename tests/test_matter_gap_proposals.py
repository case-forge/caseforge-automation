from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from sql import matter_gap_proposals as g

TODAY = dt.date(2026, 9, 25)



def test_company_ref_needs_a_real_past_date_and_reports_the_label():
    text = "Our ref: 260515/02FL and also 261399/01FL and 991231/01FL and 270101/01FL"
    assert g.company_ref_candidates(text, TODAY) == [("260515/02FL", True)]


def test_company_ref_is_not_matched_inside_a_longer_token():
    assert g.company_ref_candidates("x1260515/02FL 260515/02FLX", TODAY) == []


def test_court_number_shape_and_type_letter():
    found = g.court_number_candidates("Case No: ZZ26F77777.\n\nSome other paragraph that is long enough to push the label out of range, AB25P11111, not AB123456C or ZZ99 9ZZ")
    assert found == [("ZZ26F77777", True), ("AB25P11111", False)]
    assert g.ref_type_for("ZZ26F77777") == "court_family"
    assert g.ref_type_for("AB25P11111") == "court_children"
    assert g.ref_type_for("AB25C11111") is None


@pytest.mark.parametrize("name,expected", [
    ("25.04.2024 Hearing-SURNAME", dt.date(2024, 4, 25)),
    ("26.07.23-Hearing-SURNAME", dt.date(2023, 7, 26)),
    ("Hearing 30 March 2024", dt.date(2024, 3, 30)),
    ("Hearing 05.11.2025", dt.date(2025, 11, 5)),
])
def test_hearing_folder_date_parses(name, expected):
    assert g.hearing_folder_date(name, TODAY) == (expected, "")


@pytest.mark.parametrize("name,why", [
    ("Court Orders-SURNAME", "not_a_hearing_folder"),
    ("Final Hearing", "no_date_in_name"),
    ("31.02.2025 Hearing", "invalid_date"),
    ("Hearing 20 05 2010", "date_out_of_range"),
    ("12.03.2025 Hearing vacated", "vacated_or_cancelled_wording"),
])
def test_hearing_folder_date_refuses_what_it_cannot_settle(name, why):
    assert g.hearing_folder_date(name, TODAY) == (None, why)


def test_counsel_pairs_are_verbatim_and_need_the_label():
    text = "Counsel: Ms Jane Doe of Example Chambers to attend. Nobody, Example Chambers alone is not counsel."
    assert g.counsel_candidates(text) == [("Ms Jane Doe", "Example Chambers")]


def test_counsel_from_chambers_needs_a_cue_and_no_other_side_wording():
    cued = "We have instructed counsel for the hearing. Kind regards Ms Jane Doe from 3 Sample Court Chambers"
    assert g.counsel_candidates(cued) == [("Ms Jane Doe", "3 Sample Court Chambers")]
    assert g.counsel_candidates("Ms Jane Doe from 3 Sample Court Chambers rang about lunch") == []
    assert g.counsel_candidates("Counsel for the respondent, Mr John Roe from Other Chambers, attended") == []


def test_greeting_words_are_not_part_of_the_counsel_name():
    text = "Brief to counsel. Dear Ms Jane Doe from 3 Sample Court Chambers"
    assert g.counsel_candidates(text) == [("Ms Jane Doe", "3 Sample Court Chambers")]
    assert g.counsel_candidates("Brief to counsel. Thanks Doe from 3 Sample Court Chambers") == []



def _state(**over):
    base = {"matters": {}, "refs": [], "hearings": [], "mined_company": {}, "mined_court": {},
            "mined_counsel": {}, "folders": []}
    base.update(over)
    return base


def _m(open_=True, company="", ref_date="2026-01-05"):
    return {"open": open_, "company_reference": company, "ref_date": ref_date}


def _h(hid, mid=None, case="", date="2026-10-01", state="ok", reason="", counsel="", chambers="", text=""):
    return {"hearing_id": hid, "matter_id": mid, "case_ref": case, "date": date, "review_state": state,
            "review_reason": reason, "counsel": counsel, "chambers": chambers, "text": text}


def _rules(props, rule):
    return [p for p in props if p["rule"] == rule]


def test_company_reference_is_reconciled_between_its_two_homes():
    state = _state(matters={1: _m(company="260101/01FL"), 2: _m()},
                   refs=[{"matter_id": 2, "ref_type": "company_ref", "value": "260102/01FL"}])
    props, conflicts, _ = g.build_proposals(state, TODAY)
    assert _rules(props, "company_ref_reconcile_to_references")[0]["args"]["matter_id"] == 1
    assert _rules(props, "company_ref_reconcile_to_matters")[0]["args"] == {"matter_id": 2, "value": "260102/01FL"}
    assert conflicts == []


def test_a_single_labelled_company_reference_is_high_and_a_shared_one_is_a_conflict():
    mined = {"260301/01FL": {"docs": {"d1"}, "labelled": 1}}
    state = _state(matters={1: _m(), 2: _m()}, mined_company={1: mined, 2: mined})
    props, conflicts, _ = g.build_proposals(state, TODAY)
    assert _rules(props, "company_ref_from_documents") == []
    assert {c["reason"] for c in conflicts} == {"proposed_for_several_matters"}
    state = _state(matters={1: _m()}, mined_company={1: mined})
    props, _, _ = g.build_proposals(state, TODAY)
    p = _rules(props, "company_ref_from_documents")[0]
    assert (p["confidence"], p["evidence"]) == ("high", [{"item_id": "d1"}])


def test_two_company_candidates_in_one_matter_are_a_conflict():
    mined = {"260301/01FL": {"docs": {"d1"}, "labelled": 1}, "260302/01FL": {"docs": {"d2"}, "labelled": 1}}
    props, conflicts, _ = g.build_proposals(_state(matters={1: _m()}, mined_company={1: mined}), TODAY)
    assert props == [] and conflicts[0]["reason"] == "several_candidates"


def test_generation_candidates_are_counted_never_proposed():
    state = _state(matters={1: _m(), 2: _m(ref_date=""), 3: _m(open_=False)})
    props, _, summary = g.build_proposals(state, TODAY)
    assert props == []
    assert summary["company_reference_generation_candidates"] == {"open_matters_without_any": 2, "of_which_with_a_referral_date": 1}


def test_court_number_is_proposed_once_typed_and_flags_a_second_candidate():
    one = {"ZZ26F77777": {"docs": {"d1"}, "labelled": 1, "order_docs": 1}}
    props, _, _ = g.build_proposals(_state(matters={1: _m()}, mined_court={1: one}), TODAY)
    p = _rules(props, "court_number_from_documents")[0]
    assert (p["args"]["ref_type"], p["confidence"]) == ("court_family", "high")

    two = {"ZZ26F77777": {"docs": {"d1"}, "labelled": 1, "order_docs": 1}, "ZZ26F88888": {"docs": {"d2"}, "labelled": 0, "order_docs": 0}}
    props, conflicts, _ = g.build_proposals(_state(matters={1: _m()}, mined_court={1: two}), TODAY)
    assert props == [] and conflicts[0]["reason"] == "several_candidates"


def test_a_hearing_case_number_breaks_the_tie_between_two_candidates():
    two = {"ZZ26F77777": {"docs": {"d1"}, "labelled": 0, "order_docs": 0}, "ZZ26F88888": {"docs": {"d2"}, "labelled": 0, "order_docs": 0}}
    state = _state(matters={1: _m()}, mined_court={1: two}, hearings=[_h(1, mid=1, case="ZZ26F88888")])
    props, _, _ = g.build_proposals(state, TODAY)
    assert _rules(props, "court_number_from_documents")[0]["args"]["value"] == "ZZ26F88888"


def test_court_number_held_by_another_matter_or_care_letter_is_a_conflict():
    found = {"ZZ26F77777": {"docs": {"d1"}, "labelled": 1, "order_docs": 1}, "ZZ26C55555": {"docs": {"d3"}, "labelled": 1, "order_docs": 0}}
    state = _state(matters={1: _m(), 2: _m()}, mined_court={1: found},
                   refs=[{"matter_id": 2, "ref_type": "court_family", "value": "ZZ26F77777"}])
    props, conflicts, _ = g.build_proposals(state, TODAY)
    assert props == []
    assert {c["reason"] for c in conflicts} == {"held_by_another_matter", "unmapped_case_letter"}


def test_existing_court_reference_is_left_alone_and_a_strong_difference_is_flagged():
    found = {"ZZ26F99999": {"docs": {"d1", "d2"}, "labelled": 2, "order_docs": 1}}
    state = _state(matters={1: _m()}, mined_court={1: found}, refs=[{"matter_id": 1, "ref_type": "court_family", "value": "ZZ26F77777"}])
    props, conflicts, _ = g.build_proposals(state, TODAY)
    assert props == [] and conflicts[0]["reason"] == "differs_from_existing"


def test_unlinked_hearing_links_through_an_existing_or_a_proposed_reference():
    state = _state(matters={1: _m(), 2: _m()},
                   refs=[{"matter_id": 1, "ref_type": "court_family", "value": "ZZ26F77777"}],
                   mined_court={2: {"ZZ26P00000": {"docs": {"d"}, "labelled": 1, "order_docs": 1}}},
                   hearings=[_h(1, case="ZZ26F77777"), _h(2, case="ZZ26P00000"), _h(3, case="ZZ26F99999")])
    props, _, _ = g.build_proposals(state, TODAY)
    links = {p["args"]["hearing_id"]: (p["args"]["matter_id"], p["confidence"]) for p in _rules(props, "hearing_link_by_case_number")}
    assert links == {1: (1, "high"), 2: (2, "medium")}


def test_hearing_folder_creates_a_hearing_only_when_none_exists_that_day():
    state = _state(matters={1: _m()},
                   hearings=[_h(1, mid=1, date="2026-03-02", state="needs_review", reason="no hearing time stated")],
                   folders=[{"matter_id": 1, "date": "2026-03-02", "item_id": "f1"},
                            {"matter_id": 1, "date": "2026-11-12", "item_id": "f2"},
                            {"matter_id": 1, "date": "2025-05-01", "item_id": "f3"}])
    props, _, _ = g.build_proposals(state, TODAY)
    assert [p["args"]["hearing_id"] for p in _rules(props, "hearing_confirmed_by_folder")] == [1]
    created = {p["args"]["hearing_date"]: p["args"]["review_state"] for p in _rules(props, "hearing_from_folder_name")}
    assert created == {"2026-11-12": "needs_review", "2025-05-01": "ok"}


def test_a_weekend_review_reason_is_never_confirmed_by_a_folder():
    state = _state(matters={1: _m()}, hearings=[_h(1, mid=1, date="2026-03-01", state="needs_review", reason="date falls on a weekend")],
                   folders=[{"matter_id": 1, "date": "2026-03-01", "item_id": "f1"}])
    props, _, _ = g.build_proposals(state, TODAY)
    assert _rules(props, "hearing_confirmed_by_folder") == []


def test_counsel_from_the_hearing_text_is_high_and_from_matter_documents_needs_one_pair():
    text = "Counsel: Mr John Roe, Sample Chambers"
    state = _state(matters={1: _m()}, hearings=[_h(1, text=text), _h(2, mid=1), _h(3, mid=1, counsel="Someone", chambers="Set")],
                   mined_counsel={1: [{"pair": ["Ms A Person", "Other Chambers"], "item_id": "d9", "modified": "2026-09-01"}]})
    props, _, _ = g.build_proposals(state, TODAY)
    got = {p["args"]["hearing_id"]: (p["rule"], p["confidence"], p["args"]["chambers"]) for p in props if p["op"] == "set_counsel"}
    assert got == {1: ("counsel_from_hearing_text", "high", "Sample Chambers"),
                   2: ("counsel_from_documents", "medium", "Other Chambers")}


def test_two_counsel_in_a_matter_are_split_by_the_nearest_document_or_flagged():
    docs = [{"pair": ["A One", "Alpha Chambers"], "item_id": "d1", "modified": "2026-09-20"},
            {"pair": ["B Two", "Beta Chambers"], "item_id": "d2", "modified": "2025-01-01"}]
    state = _state(matters={1: _m()}, hearings=[_h(1, mid=1, date="2026-10-01"), _h(2, mid=1, date="2026-02-01")], mined_counsel={1: docs})
    props, conflicts, _ = g.build_proposals(state, TODAY)
    assert [(p["args"]["hearing_id"], p["args"]["counsel"]) for p in props if p["op"] == "set_counsel"] == [(1, "A One")]
    assert conflicts[0]["reason"] == "several_counsel_in_matter"


def test_mining_skips_c8_chunks_and_other_matters():
    chunks = [
        {"matter_id": "1", "item_id": "a", "doc_type": "order", "text": "Case No ZZ26F77777 Our ref 260301/01FL"},
        {"matter_id": "1", "item_id": "b", "doc_type": "other", "c8_protected": True, "text": "ZZ26F99999"},
        {"matter_id": "999", "item_id": "c", "doc_type": "order", "text": "ZZ26F33333"},
        {"matter_id": "folder:x", "item_id": "d", "doc_type": "order", "text": "ZZ26F22222"},
    ]
    company, court, _ = g.mine_chunks(chunks, {1}, TODAY)
    assert list(court) == [1] and list(court[1]) == ["ZZ26F77777"] and court[1]["ZZ26F77777"]["order_docs"] == 1
    assert list(company[1]) == ["260301/01FL"]



SCHEMA = """
CREATE TABLE matters (matter_id INTEGER PRIMARY KEY, company_reference TEXT);
CREATE TABLE matter_references (reference_id INTEGER PRIMARY KEY AUTOINCREMENT, matter_id INTEGER, ref_type TEXT, ref_value TEXT,
  ref_value_normalised TEXT, source TEXT, notes TEXT, is_primary INTEGER, created_utc TEXT, updated_utc TEXT,
  UNIQUE (matter_id, ref_type, ref_value_normalised));
CREATE TABLE matter_hearings (hearing_id INTEGER PRIMARY KEY AUTOINCREMENT, hearing_uid TEXT UNIQUE, matter_id INTEGER, case_ref TEXT DEFAULT '',
  hearing_date TEXT, counsel TEXT NOT NULL DEFAULT '', chambers TEXT NOT NULL DEFAULT '', review_state TEXT DEFAULT 'ok', review_reason TEXT DEFAULT '',
  confidence REAL, source_kind TEXT DEFAULT 'manual', source_subject TEXT DEFAULT '', human_edited INTEGER DEFAULT 0,
  created_utc TEXT, updated_utc TEXT, updated_by TEXT DEFAULT '',
  duration_minutes INTEGER NOT NULL DEFAULT 60, duration_stated INTEGER NOT NULL DEFAULT 1);
CREATE TABLE matter_hearing_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, hearing_id INTEGER, at_utc TEXT, actor TEXT, action TEXT,
  before_json TEXT, after_json TEXT, source_message_id TEXT);
CREATE TABLE clientdb_normalise_log (log_id INTEGER PRIMARY KEY AUTOINCREMENT, run_tag TEXT, table_name TEXT, pk_column TEXT, pk_value TEXT,
  column_name TEXT, old_value TEXT, new_value TEXT, applied_utc TEXT, reverted_utc TEXT);
"""


@pytest.fixture()
def cur():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    conn.executescript("INSERT INTO matters VALUES (1, ''), (2, '260102/01FL');"
                       "INSERT INTO matter_hearings (hearing_uid, matter_id, case_ref, hearing_date, review_state, review_reason) VALUES "
                       "('u1', NULL, 'ZZ26F77777', '2026-11-02', 'needs_review', 'no hearing time stated'),"
                       "('u2', 2, '', '2026-12-01', 'ok', '');")
    yield conn.cursor()
    conn.close()


PROPOSALS = [
    {"rule": "r", "op": "insert_reference", "confidence": "high", "args": {"matter_id": 1, "ref_type": "court_family", "value": "ZZ26F77777"}, "evidence": []},
    {"rule": "r", "op": "set_company_reference", "confidence": "high", "args": {"matter_id": 1, "value": "260101/01FL", "also_reference_row": True}, "evidence": []},
    {"rule": "r", "op": "link_hearing", "confidence": "high", "args": {"hearing_id": 1, "matter_id": 1}, "evidence": []},
    {"rule": "r", "op": "confirm_hearing", "confidence": "high", "args": {"hearing_id": 1}, "evidence": [{"item_id": "f1"}]},
    {"rule": "r", "op": "insert_hearing", "confidence": "medium", "args": {"matter_id": 1, "hearing_date": "2027-01-05", "case_ref": "", "review_state": "needs_review", "review_reason": "x", "source_kind": "folder"}, "evidence": [{"item_id": "f2"}]},
    {"rule": "r", "op": "set_counsel", "confidence": "high", "args": {"hearing_id": 2, "counsel": "A One", "chambers": "Alpha Chambers"}, "evidence": []},
    {"rule": "low", "op": "set_counsel", "confidence": "low", "args": {"hearing_id": 1, "counsel": "X", "chambers": "Y Chambers"}, "evidence": []},
]


def _snapshot(cur):
    return {t: cur.execute(f"SELECT * FROM {t}").fetchall() for t in ("matters", "matter_references", "matter_hearings")}


def test_apply_writes_logs_and_skips_low_confidence(cur):
    result = g.apply_proposals(cur, PROPOSALS, "t1")
    assert result["low"] == {"skipped_low_confidence": 1}
    assert cur.execute("SELECT company_reference FROM matters WHERE matter_id = 1").fetchone()[0] == "260101/01FL"
    assert cur.execute("SELECT count(*) FROM matter_references").fetchone()[0] == 2
    assert cur.execute("SELECT matter_id, review_state FROM matter_hearings WHERE hearing_id = 1").fetchone() == (1, "ok")
    assert cur.execute("SELECT counsel, chambers FROM matter_hearings WHERE hearing_id = 2").fetchone() == ("A One", "Alpha Chambers")
    assert cur.execute("SELECT count(*) FROM matter_hearings WHERE source_kind = 'folder'").fetchone()[0] == 1
    assert cur.execute("SELECT count(*) FROM clientdb_normalise_log WHERE run_tag = 't1'").fetchone()[0] >= 8
    assert cur.execute("SELECT count(*) FROM matter_hearing_events").fetchone()[0] >= 3


def test_a_folder_hearing_marks_its_60_minutes_as_a_placeholder(cur):
    g.apply_proposals(cur, PROPOSALS, "t1")
    row = cur.execute("SELECT duration_minutes, duration_stated FROM matter_hearings WHERE source_kind = 'folder'").fetchone()
    assert row == (60, 0)


def test_a_proposal_that_gives_a_length_is_stated(cur):
    stated = dict(PROPOSALS[4], args={**PROPOSALS[4]["args"], "duration_minutes": 90})
    g.apply_proposals(cur, [stated], "t1")
    row = cur.execute("SELECT duration_minutes, duration_stated FROM matter_hearings WHERE source_kind = 'folder'").fetchone()
    assert row == (90, 1)


def test_apply_is_idempotent(cur):
    g.apply_proposals(cur, PROPOSALS, "t1")
    before = _snapshot(cur)
    again = g.apply_proposals(cur, PROPOSALS, "t2")
    assert _snapshot(cur) == before
    assert all(set(v) <= {"already_present", "skipped_low_confidence"} for v in again.values())


def test_counsel_is_never_overwritten(cur):
    cur.execute("UPDATE matter_hearings SET counsel = 'Typed By Hand', chambers = 'Own Set' WHERE hearing_id = 2")
    g.apply_proposals(cur, PROPOSALS, "t1")
    assert cur.execute("SELECT counsel, chambers FROM matter_hearings WHERE hearing_id = 2").fetchone() == ("Typed By Hand", "Own Set")


def test_revert_restores_everything_it_wrote(cur):
    before = _snapshot(cur)
    g.apply_proposals(cur, PROPOSALS, "t1")
    dry = g.revert_run(cur, "t1", apply=False)
    assert dry["restored"] == dry["entries"] and dry["changed_since"] == 0
    assert _snapshot(cur) != before
    g.revert_run(cur, "t1", apply=True)
    after = _snapshot(cur)
    assert after["matters"] == before["matters"]
    assert after["matter_references"] == before["matter_references"] == []
    assert [(r[0], r[2], r[3], r[5], r[6], r[7]) for r in after["matter_hearings"]] == [(r[0], r[2], r[3], r[5], r[6], r[7]) for r in before["matter_hearings"]]


def test_revert_leaves_a_later_human_edit_alone(cur):
    g.apply_proposals(cur, PROPOSALS, "t1")
    cur.execute("UPDATE matter_hearings SET counsel = 'Changed Later' WHERE hearing_id = 2")
    cur.execute("UPDATE matter_hearings SET human_edited = 1 WHERE review_state = 'needs_review' AND hearing_id > 2")
    out = g.revert_run(cur, "t1", apply=True)
    assert out["changed_since"] >= 2
    assert cur.execute("SELECT counsel FROM matter_hearings WHERE hearing_id = 2").fetchone()[0] == "Changed Later"
    assert cur.execute("SELECT count(*) FROM matter_hearings WHERE source_kind = 'folder'").fetchone()[0] == 1


def test_revert_refuses_a_log_row_it_does_not_recognise(cur):
    cur.execute("INSERT INTO clientdb_normalise_log (run_tag, table_name, pk_column, pk_value, column_name, old_value, new_value) "
                "VALUES ('bad', 'people', 'person_id', '1', 'name_first', 'a', 'b')")
    with pytest.raises(ValueError):
        g.revert_run(cur, "bad", apply=True)



def _md(dates, open_=True, company=""):
    return {"open": open_, "company_reference": company, "ref_date": dates[0] if dates else "", "dates": list(dates)}


def _info(*docs, labelled=1):
    return {"docs": set(docs), "labelled": labelled}


def test_legacy_shape_needs_initials_and_a_real_date():
    assert g.legacy_company_ref_candidates("Our ref: AB/240809/001FL", TODAY) == [("AB/240809/001FL", True)]
    assert g.legacy_company_ref_candidates("see CD/EF/240810/012 FL attached", TODAY) == [("CD/EF/240810/012FL", False)]
    assert g.legacy_company_ref_candidates("AB/999999/001FL xAB/240809/001FL", TODAY) == []


def test_a_reference_carries_its_own_date():
    assert g.ref_date_of("260805/01FL") == dt.date(2026, 8, 5)
    assert g.ref_date_of("AB/240809/001FL") == dt.date(2024, 8, 9)
    assert g.ref_date_of("nonsense") is None
    assert g.near_matter_date("260805/01FL", ["2026-08-12"]) is True
    assert g.near_matter_date("260805/01FL", ["2026-09-30"]) is False
    assert g.near_matter_date("260805/01FL", []) is False


def test_the_referral_date_chooses_between_candidates_in_one_matter():
    mined = {"260301/01FL": _info("d1"), "250101/01FL": _info("d2")}
    state = _state(matters={1: _md(["2026-03-02"])}, mined_company={1: mined})
    props, conflicts, _ = g.build_proposals(state, TODAY)
    p = _rules(props, "company_ref_from_documents")[0]
    assert (p["args"]["value"], p["chosen_by"], p["date_match"], p["confidence"]) == ("260301/01FL", "referral_date", True, "high")
    assert conflicts == []


def test_no_candidate_near_the_referral_date_stays_a_conflict():
    mined = {"260301/01FL": _info("d1"), "250101/01FL": _info("d2")}
    props, conflicts, _ = g.build_proposals(_state(matters={1: _md(["2026-08-02"])}, mined_company={1: mined}), TODAY)
    assert props == [] and conflicts[0]["reason"] == "several_candidates" and conflicts[0]["near_referral_date"] == 0


def test_two_candidates_near_the_date_are_not_guessed_between():
    mined = {"260301/01FL": _info("d1"), "260302/02FL": _info("d2")}
    props, conflicts, _ = g.build_proposals(_state(matters={1: _md(["2026-03-02"])}, mined_company={1: mined}), TODAY)
    assert props == [] and conflicts[0]["reason"] == "several_near_referral_date"


def test_a_reference_the_papers_overwhelmingly_show_is_chosen_at_medium():
    mined = {"260301/01FL": _info("d1", "d2", "d3", "d4"), "260302/02FL": _info("d5")}
    props, conflicts, _ = g.build_proposals(_state(matters={1: _md(["2026-08-02"])}, mined_company={1: mined}), TODAY)
    p = _rules(props, "company_ref_from_documents")[0]
    assert (p["args"]["value"], p["chosen_by"], p["confidence"]) == ("260301/01FL", "document_count", "medium")
    assert conflicts == []


def test_dominance_needs_three_documents_three_times_the_runner_up_and_no_date_against_it():
    thin = {"260301/01FL": _info("d1", "d2"), "260302/02FL": _info("d3")}
    assert g.dominant_reference(thin, []) is None
    close = {"260301/01FL": _info("d1", "d2", "d3", "d4"), "260302/02FL": _info("d5", "d6")}
    assert g.dominant_reference(close, []) is None
    contradicted = {"250101/01FL": _info("d1", "d2", "d3"), "260301/01FL": _info("d4")}
    assert g.dominant_reference(contradicted, ["2026-03-02"]) is None
    assert g.dominant_reference(contradicted, ["2025-01-02"]) == "250101/01FL"
    assert g.dominant_reference(contradicted, []) == "250101/01FL"


def test_a_lone_candidate_far_from_the_date_is_downgraded_not_dropped():
    mined = {"250101/01FL": _info("d1", "d2")}
    props, _, _ = g.build_proposals(_state(matters={1: _md(["2026-03-02"])}, mined_company={1: mined}), TODAY)
    p = _rules(props, "company_ref_from_documents")[0]
    assert (p["confidence"], p["date_match"]) == ("medium", False)


def test_the_older_house_style_is_a_separate_rule_and_never_beats_the_standard_one():
    legacy = {"AB/240809/001FL": _info("d1")}
    props, _, _ = g.build_proposals(_state(matters={1: _md(["2024-08-09"])}, mined_company={}, mined_company_legacy={1: legacy}), TODAY)
    p = _rules(props, "company_ref_legacy_from_documents")[0]
    assert (p["style"], p["args"]["value"]) == ("legacy", "AB/240809/001FL")
    both = g.build_proposals(_state(matters={1: _md(["2024-08-09"])}, mined_company={1: {"240809/01FL": _info("d2")}},
                                    mined_company_legacy={1: legacy}), TODAY)[0]
    assert _rules(both, "company_ref_legacy_from_documents") == [] and _rules(both, "company_ref_from_documents")[0]["style"] == "standard"


def test_a_reference_two_matters_share_is_corrected_on_the_one_its_documents_do_not_show():
    ref = "260301/01FL"
    state = _state(
        matters={1: _md(["2026-03-01"], company=ref), 2: _md(["2026-03-01"], company=ref)},
        mined_company={1: {ref: _info("d1")}, 2: {"260301/02FL": _info("d2")}},
    )
    props, _, _ = g.build_proposals(state, TODAY)
    fix = _rules(props, "company_ref_collision_replace")[0]
    assert fix["op"] == "replace_company_reference" and fix["args"] == {"matter_id": 2, "old": ref, "new": "260301/02FL"}
    assert fix["genuine_matter"] == 1 and fix["evidence"] == [{"item_id": "d2"}]


def test_a_shared_reference_is_not_copied_between_a_matters_two_homes():
    ref = "260301/01FL"
    state = _state(matters={1: _md(["2026-03-01"], company=ref), 2: _md(["2026-03-01"])},
                   refs=[{"matter_id": 2, "ref_type": "company_ref", "value": ref}])
    props, conflicts, _ = g.build_proposals(state, TODAY)
    assert _rules(props, "company_ref_reconcile_to_references") == [] and _rules(props, "company_ref_reconcile_to_matters") == []
    assert {"rule": "company_ref_reconcile", "matter_id": 1, "reason": "value_held_by_another_matter"} in conflicts
    assert {"rule": "company_ref_reconcile", "matter_id": 2, "reason": "value_held_by_another_matter"} in conflicts


def test_the_wrong_holder_gets_the_reference_its_own_papers_overwhelmingly_show():
    ref = "260301/01FL"
    state = _state(
        matters={1: _md(["2026-03-01"], company=ref), 2: _md(["2026-08-09"], company=ref)},
        mined_company={1: {ref: _info("d1")}, 2: {"260720/01FL": _info("e1", "e2", "e3", "e4"), "260101/01FL": _info("e5")}},
    )
    props, _, _ = g.build_proposals(state, TODAY)
    fix = _rules(props, "company_ref_collision_replace")[0]
    assert fix["args"] == {"matter_id": 2, "old": ref, "new": "260720/01FL"} and fix["chosen_by"] == "document_count"


def test_a_shared_reference_with_nothing_to_tell_them_apart_is_a_conflict():
    ref = "260301/01FL"
    state = _state(matters={1: _md(["2026-08-01"], company=ref), 2: _md(["2026-08-01"], company=ref)})
    props, conflicts, _ = g.build_proposals(state, TODAY)
    assert _rules(props, "company_ref_collision_replace") == []
    collision = [c for c in conflicts if c["rule"] == "company_ref_collision"]
    assert collision[0]["reason"] == "cannot_tell_which_matter_holds_it"


def test_a_wrong_holder_with_no_other_reference_in_its_documents_is_flagged_not_cleared():
    ref = "260301/01FL"
    state = _state(matters={1: _md(["2026-03-01"], company=ref), 2: _md(["2026-03-01"], company=ref)}, mined_company={1: {ref: _info("d1")}})
    props, conflicts, _ = g.build_proposals(state, TODAY)
    assert _rules(props, "company_ref_collision_replace") == []
    assert [(c["reason"], c["matter_id"], c["genuine_matter"]) for c in conflicts if c["rule"] == "company_ref_collision"] == [
        ("wrong_holder_has_no_other_reference_in_its_documents", 2, 1)]


def test_an_unmapped_case_letter_is_offered_as_court_ref_but_stays_a_conflict():
    found = {"ZZ26C77777": {"docs": {"d1"}, "labelled": 1, "order_docs": 1}}
    props, conflicts, _ = g.build_proposals(_state(matters={1: _m()}, mined_court={1: found}), TODAY)
    p = _rules(props, "court_number_unmapped_letter_as_court_ref")[0]
    assert (p["args"]["ref_type"], p["style"], p["args"]["letter"]) == ("court_ref", "court_ref", "C")
    assert conflicts[0]["reason"] == "unmapped_case_letter"
    files = g.split_proposal_files(props)
    assert files["proposals.json"] == [] and files["proposals-review.json"] == [p]


def test_the_owner_review_files_are_kept_apart_from_the_main_file():
    props = [{"style": "standard", "rule": "a"}, {"rule": "b"}, {"style": "legacy", "rule": "c"}, {"style": "court_ref", "rule": "d"}]
    files = g.split_proposal_files(props)
    assert [p["rule"] for p in files["proposals.json"]] == ["a", "b"]
    assert [p["rule"] for p in files["proposals-legacy.json"]] == ["c"]
    assert [p["rule"] for p in files["proposals-review.json"]] == ["d"]


def test_mine_text_serves_documents_read_directly_and_fills_the_legacy_map():
    company, court, legacy = {1: {}}, {1: {}}, {1: {}}
    g.mine_text(1, "f1", "Our ref: 260301/01FL and AB/240809/001FL. Case No ZZ26F77777", company, court, legacy, TODAY, "order")
    assert list(company[1]) == ["260301/01FL"] and list(legacy[1]) == ["AB/240809/001FL"]
    assert court[1]["ZZ26F77777"]["order_docs"] == 1



def _f(item, name, path="Live/Alpha", size=1000):
    return {"item_id": item, "path": f"{path}/{name}", "name": name, "size": size}


def test_the_reading_plan_takes_the_best_papers_first_and_only_for_matters_that_need_them():
    roots = [("Live/Alpha/", 1), ("Live/Beta/", 2), ("Live/", 9)]
    items = [
        _f("a", "Invoice 12.docx", "Live/Alpha"), _f("b", "Client Care Letter.docx", "Live/Alpha"), _f("c", "Notice of Acting.pdf", "Live/Alpha"),
        _f("d", "Client Care Letter.docx", "Live/Alpha/Old"),
        _f("e", "Photo.jpg", "Live/Alpha"), _f("f", "Client Care Letter.docx", "Live/Beta"), _f("g", "Client Care Letter.docx", "Live/Alpha", size=99_000_000),
        _f("h", "Sealed order.pdf", "Live/Alpha"),
    ]
    plan = g.plan_file_reads(items, roots, company_targets={1}, court_targets=set(), per_matter=2)
    assert list(plan) == [1]
    assert [f["name"] for f in plan[1]] == ["Client Care Letter.docx", "Notice of Acting.pdf"]
    assert plan[1][0]["purpose"] == "company:ccl"
    both = g.plan_file_reads(items, roots, company_targets={1}, court_targets={1}, per_matter=10)
    assert [f["purpose"] for f in both[1]] == ["company:ccl", "company:noa", "company:invoice", "court:order"]


def test_read_targets_are_open_matters_lacking_the_thing_plus_every_shared_holder():
    matters = {1: _md([], company="260301/01FL"), 2: _md([], company="260301/01FL", open_=False), 3: _md([]), 4: _md([], company="260302/01FL"),
               5: _md([], open_=False)}
    refs = [{"matter_id": 4, "ref_type": "court_family", "value": "ZZ26F11111"}, {"matter_id": 3, "ref_type": "company_ref", "value": "260303/01FL"}]
    company, court = g.read_targets(matters, refs)
    assert company == {1, 2}
    assert court == {1, 3}


def test_a_letters_reference_is_read_from_its_header(tmp_path):
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_paragraph("Dear client")
    d.sections[0].header.paragraphs[0].text = "Our ref: 260301/01FL"
    path = tmp_path / "letter.docx"
    d.save(str(path))
    text = g.docx_text_with_headers(path)
    assert g.company_ref_candidates(text, TODAY) == [("260301/01FL", True)]



@pytest.fixture()
def shared(cur):
    cur.execute("DELETE FROM matters")
    cur.executescript("INSERT INTO matters VALUES (1, '260301/01FL'), (2, '260301/01FL'), (3, '');")
    for mid in (1, 2):
        cur.execute("INSERT INTO matter_references (matter_id, ref_type, ref_value, ref_value_normalised, created_utc, updated_utc) "
                    "VALUES (?, 'company_ref', '260301/01FL', '260301/01FL', 't', 't')", (mid,))
    return cur


FIX = [{"rule": "company_ref_collision_replace", "op": "replace_company_reference", "confidence": "medium",
        "args": {"matter_id": 2, "old": "260301/01FL", "new": "260301/02FL"}, "evidence": [{"item_id": "d2"}]}]


def test_the_correction_changes_both_homes_logs_them_and_reverts(shared):
    before = _snapshot(shared)
    out = g.apply_proposals(shared, FIX, "s3")
    assert out["company_ref_collision_replace"] == {"applied": 1}
    assert shared.execute("SELECT company_reference FROM matters WHERE matter_id IN (1, 2) ORDER BY 1").fetchall() == [("260301/01FL",), ("260301/02FL",)]
    assert shared.execute("SELECT ref_value, ref_value_normalised FROM matter_references WHERE matter_id = 2").fetchone() == ("260301/02FL", "260301/02FL")
    assert shared.execute("SELECT ref_value FROM matter_references WHERE matter_id = 1").fetchone()[0] == "260301/01FL"
    assert shared.execute("SELECT count(*) FROM clientdb_normalise_log WHERE run_tag = 's3'").fetchone()[0] == 3
    dry = g.revert_run(shared, "s3", apply=False)
    assert dry["restored"] == dry["entries"] == 3
    g.revert_run(shared, "s3", apply=True)
    assert _snapshot(shared)["matters"] == before["matters"]
    assert [r[3:5] for r in _snapshot(shared)["matter_references"]] == [r[3:5] for r in before["matter_references"]]


def test_the_correction_is_idempotent_and_refuses_a_value_held_elsewhere(shared):
    g.apply_proposals(shared, FIX, "s3")
    again = g.apply_proposals(shared, FIX, "s4")
    assert again["company_ref_collision_replace"] == {"old_value_not_present": 1}
    shared.execute("UPDATE matters SET company_reference = '260301/01FL' WHERE matter_id = 2")
    shared.execute("UPDATE matter_references SET ref_value = '260301/01FL', ref_value_normalised = '260301/01FL' WHERE matter_id = 2")
    shared.execute("UPDATE matters SET company_reference = '260301/02FL' WHERE matter_id = 3")
    blocked = g.apply_proposals(shared, FIX, "s5")
    assert blocked["company_ref_collision_replace"] == {"new_value_held_by_another_matter": 1}
    assert shared.execute("SELECT company_reference FROM matters WHERE matter_id = 2").fetchone()[0] == "260301/01FL"



def _set(mid, value, also_row=False, rule="set"):
    return [{"rule": rule, "op": "set_company_reference", "confidence": "high",
             "args": {"matter_id": mid, "value": value, "also_reference_row": also_row}, "evidence": []}]


def test_setting_a_reference_another_matter_holds_is_refused_and_reported(cur):
    refused = []
    out = g.apply_proposals(cur, _set(1, "260102/01fl "), "d1", refused=refused)
    assert out["set"] == {"value_held_by_another_matter": 1}
    assert refused == [{"rule": "set", "op": "set_company_reference", "matter_id": 1, "reason": "value_held_by_another_matter"}]
    assert cur.execute("SELECT company_reference FROM matters WHERE matter_id = 1").fetchone()[0] == ""
    assert cur.execute("SELECT count(*) FROM clientdb_normalise_log").fetchone()[0] == 0


def test_a_reference_held_only_in_another_matters_reference_row_is_refused_too(cur):
    cur.execute("INSERT INTO matters VALUES (3, '')")
    cur.execute("INSERT INTO matter_references (matter_id, ref_type, ref_value, ref_value_normalised, created_utc, updated_utc) "
                "VALUES (3, 'company_ref', '260105/01FL', '260105/01FL', 't', 't')")
    out = g.apply_proposals(cur, _set(1, "260105/01FL"), "d2")
    assert out["set"] == {"value_held_by_another_matter": 1}
    assert cur.execute("SELECT company_reference FROM matters WHERE matter_id = 1").fetchone()[0] == ""


def test_a_fresh_reference_is_set_and_logged(cur):
    refused = []
    out = g.apply_proposals(cur, _set(1, "260103/01FL", also_row=True), "d3", refused=refused)
    assert out["set"] == {"applied": 1} and refused == []
    assert cur.execute("SELECT company_reference FROM matters WHERE matter_id = 1").fetchone()[0] == "260103/01FL"
    assert cur.execute("SELECT matter_id FROM matter_references WHERE ref_value_normalised = '260103/01FL'").fetchall() == [(1,)]
    assert cur.execute("SELECT count(*) FROM clientdb_normalise_log WHERE run_tag = 'd3'").fetchone()[0] == 2


def test_setting_the_same_reference_again_on_the_same_matter_is_a_no_op(cur):
    g.apply_proposals(cur, _set(1, "260103/01FL", also_row=True), "d4")
    before = _snapshot(cur)
    refused = []
    again = g.apply_proposals(cur, _set(1, "260103/01FL", also_row=True), "d5", refused=refused)
    assert again["set"] == {"already_present": 1} and refused == []
    assert _snapshot(cur) == before
    assert cur.execute("SELECT count(*) FROM clientdb_normalise_log WHERE run_tag = 'd5'").fetchone()[0] == 0


def test_a_company_reference_row_another_matter_holds_is_refused(cur):
    prop = [{"rule": "row", "op": "insert_reference", "confidence": "high",
             "args": {"matter_id": 1, "ref_type": "company_ref", "value": "260102/01FL"}, "evidence": []}]
    refused = []
    out = g.apply_proposals(cur, prop, "d6", refused=refused)
    assert out["row"] == {"value_held_by_another_matter": 1}
    assert refused[0]["matter_id"] == 1
    assert cur.execute("SELECT count(*) FROM matter_references").fetchone()[0] == 0
