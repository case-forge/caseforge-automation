from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil import hearings




def _independent_working_days_count(start: dt.date, end: dt.date) -> int:
    if end <= start:
        return 0
    days = [start + dt.timedelta(days=i) for i in range(1, (end - start).days + 1)]
    return len([d for d in days if d.weekday() < 5])


@pytest.mark.parametrize(
    "start,end",
    [
        (dt.date(2026, 6, 19), dt.date(2026, 6, 26)),
        (dt.date(2026, 6, 1), dt.date(2026, 6, 5)),
        (dt.date(2026, 6, 1), dt.date(2026, 6, 1)),
        (dt.date(2026, 6, 20), dt.date(2026, 6, 22)),
        (dt.date(2026, 1, 1), dt.date(2026, 3, 1)),
    ],
)
def test_working_days_between_matches_independent_count(start, end):
    assert hearings.working_days_between(start, end) == _independent_working_days_count(start, end)


def test_working_days_between_same_day_is_zero():
    d = dt.date(2026, 6, 15)
    assert hearings.working_days_between(d, d) == 0


def test_working_days_between_excludes_uk_bank_holidays():
    start = dt.date(2026, 12, 24)
    end = dt.date(2026, 12, 29)
    assert hearings.working_days_between(start, end) == 1


def test_working_days_between_end_before_start_is_zero():
    start = dt.date(2026, 6, 26)
    end = dt.date(2026, 6, 19)
    assert hearings.working_days_between(start, end) == 0




def _write_calendar_state(monkeypatch, tmp_path, payload):
    monkeypatch.setattr(hearings, "REPO_ROOT", tmp_path)
    telemetry_dir = tmp_path / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    (telemetry_dir / "startup-hearing-calendar-state.json").write_text(
        __import__("json").dumps(payload), encoding="utf-8"
    )


def test_calendar_hearing_state_reads_clients_dict(monkeypatch, tmp_path):
    _write_calendar_state(monkeypatch, tmp_path, {"clients": {"jane doe": {"location": "Central Family Court"}}})
    assert hearings.calendar_hearing_state() == {"jane doe": {"location": "Central Family Court"}}


def test_calendar_hearing_state_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(hearings, "REPO_ROOT", tmp_path)
    assert hearings.calendar_hearing_state() == {}


def test_calendar_hearing_state_non_dict_clients_returns_empty(monkeypatch, tmp_path):
    _write_calendar_state(monkeypatch, tmp_path, {"clients": ["not", "a", "dict"]})
    assert hearings.calendar_hearing_state() == {}




def test_calendar_state_time_parses_time_from_hearing_key():
    entry = {"hearing_key": "jane doe|2026-06-19|10:30 AM"}
    assert hearings.calendar_state_time(entry) == (10, 30)


def test_calendar_state_time_falls_back_to_start_local():
    entry = {"hearing_key": "too|short", "start_local": "at 14:00"}
    assert hearings.calendar_state_time(entry) == (14, 0)


def test_calendar_state_time_returns_none_when_nothing_parses():
    assert hearings.calendar_state_time({}) is None




def test_latest_hearing_row_filters_by_client_and_date():
    rows = [
        {"client_match": "Jane Doe", "hearing_date": "19.06.2026", "category": "other", "received_utc": "2026-06-01T00:00:00Z"},
        {"client_match": "Someone Else", "hearing_date": "19.06.2026", "category": "court", "received_utc": "2026-06-02T00:00:00Z"},
    ]
    result = hearings.latest_hearing_row(rows, "Jane Doe", dt.date(2026, 6, 19))
    assert result["client_match"] == "Jane Doe"


def test_latest_hearing_row_no_match_returns_empty_dict():
    rows = [{"client_match": "Jane Doe", "hearing_date": "19.06.2026", "category": "court", "received_utc": "x"}]
    assert hearings.latest_hearing_row(rows, "Jane Doe", dt.date(2026, 7, 1)) == {}


def test_latest_hearing_row_tie_break_is_by_court_first_then_latest_received():
    rows = [
        {"client_match": "Jane Doe", "hearing_date": "19.06.2026", "category": "court", "received_utc": "2026-06-05T00:00:00Z", "from": "court-row"},
        {"client_match": "Jane Doe", "hearing_date": "19.06.2026", "category": "counsel", "received_utc": "2026-06-01T00:00:00Z", "from": "non-court-row"},
    ]
    result = hearings.latest_hearing_row(rows, "Jane Doe", dt.date(2026, 6, 19))
    assert result["from"] == "non-court-row"


def test_latest_hearing_row_within_same_category_picks_latest_received():
    rows = [
        {"client_match": "Jane Doe", "hearing_date": "19.06.2026", "category": "court", "received_utc": "2026-06-01T00:00:00Z", "from": "earlier"},
        {"client_match": "Jane Doe", "hearing_date": "19.06.2026", "category": "court", "received_utc": "2026-06-05T00:00:00Z", "from": "later"},
    ]
    result = hearings.latest_hearing_row(rows, "Jane Doe", dt.date(2026, 6, 19))
    assert result["from"] == "later"




def test_court_from_rows_returns_sender_of_matching_court_row():
    rows = [
        {"client_match": "Jane Doe", "category": "court", "hearing_date": "19.06.2026", "from": '"Central Family Court" <court@example.test>'},
        {"client_match": "Jane Doe", "category": "counsel", "hearing_date": "19.06.2026", "from": "Barrister <b@example.test>"},
    ]
    assert hearings.court_from_rows(rows, "Jane Doe", dt.date(2026, 6, 19)) == "Central Family Court"


def test_court_from_rows_no_court_category_returns_empty():
    rows = [{"client_match": "Jane Doe", "category": "counsel", "hearing_date": "19.06.2026", "from": "x"}]
    assert hearings.court_from_rows(rows, "Jane Doe", dt.date(2026, 6, 19)) == ""


def test_court_from_rows_date_mismatch_is_skipped():
    rows = [{"client_match": "Jane Doe", "category": "court", "hearing_date": "20.06.2026", "from": "Court <c@example.test>"}]
    assert hearings.court_from_rows(rows, "Jane Doe", dt.date(2026, 6, 19)) == ""




@pytest.mark.parametrize(
    "raw,expected",
    [
        ('"Jane Doe" <jane@example.test>', "Jane Doe"),
        ("Jane Doe <jane@example.test>", "Jane Doe"),
        ("jane@example.test", "jane@example.test"),
        ("  Extra   Space  <x@example.test>", "Extra Space"),
        ("", ""),
    ],
)
def test_sender_name(raw, expected):
    assert hearings.sender_name(raw) == expected




def _write_chambers_data(monkeypatch, tmp_path, chambers):
    monkeypatch.setattr(hearings, "_CHAMBERS_DOMAIN_CACHE", None)
    data_file = tmp_path / "finder-data.json"
    monkeypatch.setenv("CHAMBERS_FINDER_DATA_PATH", str(data_file))
    data_file.write_text(__import__("json").dumps({"chambers": chambers}), encoding="utf-8")


def test_chambers_name_from_sender_matches_domain(monkeypatch, tmp_path):
    _write_chambers_data(monkeypatch, tmp_path, [{"email": "clerks@example-chambers.test", "name": "1 Example Chambers"}])
    assert hearings.chambers_name_from_sender("Barrister <b@example-chambers.test>") == "1 Example Chambers"


def test_chambers_name_from_sender_no_match_returns_empty(monkeypatch, tmp_path):
    _write_chambers_data(monkeypatch, tmp_path, [{"email": "clerks@example-chambers.test", "name": "1 Example Chambers"}])
    assert hearings.chambers_name_from_sender("Someone <person@unrelated.test>") == ""


def test_chambers_name_from_sender_no_at_sign_returns_empty(monkeypatch, tmp_path):
    _write_chambers_data(monkeypatch, tmp_path, [])
    assert hearings.chambers_name_from_sender("not-an-email") == ""


def test_chambers_name_from_sender_caches_across_calls(monkeypatch, tmp_path):
    _write_chambers_data(monkeypatch, tmp_path, [{"email": "clerks@a-chambers.test", "name": "A Chambers"}])
    assert hearings.chambers_name_from_sender("x@a-chambers.test") == "A Chambers"

    (tmp_path / "finder-data.json").write_text(
        __import__("json").dumps({"chambers": [{"email": "clerks@a-chambers.test", "name": "Renamed Chambers"}]}),
        encoding="utf-8",
    )
    assert hearings.chambers_name_from_sender("x@a-chambers.test") == "A Chambers"

    monkeypatch.setattr(hearings, "_CHAMBERS_DOMAIN_CACHE", None)
    assert hearings.chambers_name_from_sender("x@a-chambers.test") == "Renamed Chambers"




def test_hearing_detail_no_hearing_date_returns_empty_dict():
    row = {"client": "Jane Doe", "next_hearing": "no date here"}
    assert hearings.hearing_detail(row, [], {}) == {}


def test_hearing_detail_assembles_full_card():
    row = {
        "client": "Jane Doe",
        "next_hearing": "19.06.2026",
        "counsel_response_status": "Confirmed",
        "awaiting": "Order from court",
    }
    rows = [
        {
            "client_match": "Jane Doe",
            "hearing_date": "19.06.2026 at 10:30",
            "category": "counsel",
            "received_utc": "2026-06-01T00:00:00Z",
            "from": "Barrister <b@a-chambers.test>",
        }
    ]
    calendar_state = {}
    detail = hearings.hearing_detail(row, rows, calendar_state)
    assert detail["client"] == "Jane Doe"
    assert detail["date"] == dt.date(2026, 6, 19)
    assert detail["time"] == "10:30"
    assert detail["counsel"] == "Counsel: Confirmed - Barrister"
    assert detail["awaiting"] == "Order from court"


def test_hearing_detail_uses_calendar_state_court_and_time_before_row_lookup():
    row = {"client": "Jane Doe", "next_hearing": "19.06.2026"}
    calendar_state = {
        "jane doe": {
            "location": "Central Family Court",
            "hearing_label": "First Hearing",
            "hearing_key": "jane doe|2026-06-19|09:00",
        }
    }
    detail = hearings.hearing_detail(row, [], calendar_state)
    assert detail["client_key"] == "jane doe"
    assert detail["court"] == "Central Family Court"
    assert detail["hearing_label"] == "First Hearing"
    assert detail["time"] == "09:00"


def test_hearing_detail_chambers_lookup_failure_falls_back_to_sender_name(monkeypatch, tmp_path):
    _write_chambers_data(monkeypatch, tmp_path, [])
    row = {"client": "Jane Doe", "next_hearing": "19.06.2026", "counsel_response_status": "Confirmed"}
    rows = [
        {
            "client_match": "Jane Doe",
            "hearing_date": "19.06.2026",
            "category": "counsel",
            "received_utc": "2026-06-01T00:00:00Z",
            "from": "Barrister Bob <b@unlisted-chambers.test>",
        }
    ]
    detail = hearings.hearing_detail(row, rows, {})
    assert detail["counsel"] == "Counsel: Confirmed - Barrister Bob"




def test_hearing_badge_counts_buckets_by_working_day_tranche():
    today = dt.date(2026, 6, 15)
    details = [
        {"date": today},
        {"date": today - dt.timedelta(days=1)},
        {"date": today + dt.timedelta(days=1)},
        {"date": today + dt.timedelta(days=8)},
        {"date": today + dt.timedelta(days=25)},
        {"date": None},
    ]
    counts = hearings.hearing_badge_counts(details, today)
    assert counts["same_day"] == 1
    assert counts["high"] == 1
    wd = hearings.working_days_between(today, today + dt.timedelta(days=8))
    expected_key = "high" if wd <= 3 else "normal" if wd <= 7 else "low" if wd <= 14 else None
    assert expected_key is not None
    assert counts[expected_key] >= 1
    assert sum(counts.values()) <= len(details)


def test_hearing_badge_counts_empty_list():
    assert hearings.hearing_badge_counts([], dt.date(2026, 6, 15)) == {
        "same_day": 0,
        "high": 0,
        "normal": 0,
        "low": 0,
    }




def test_redundant_awaiting_empty_text_is_redundant():
    assert hearings.redundant_awaiting("", dt.date(2026, 6, 19)) is True


def test_redundant_awaiting_matching_hearing_on_date_is_redundant():
    assert hearings.redundant_awaiting("Hearing on 19.06.2026", dt.date(2026, 6, 19)) is True


def test_redundant_awaiting_matching_slash_date_format_is_redundant():
    assert hearings.redundant_awaiting("Hearing on 19/06/2026", dt.date(2026, 6, 19)) is True


def test_redundant_awaiting_different_content_is_not_redundant():
    assert hearings.redundant_awaiting("Order from court awaited", dt.date(2026, 6, 19)) is False


def test_redundant_awaiting_hearing_on_wrong_date_is_not_redundant():
    assert hearings.redundant_awaiting("Hearing on 20.06.2026", dt.date(2026, 6, 19)) is False




def test_active_case_status_reformats_live_status_dates():
    row = {"latest_live_status": "Hearing listed for 19.06.2026"}
    assert hearings.active_case_status(row) == "Hearing listed for 19 June 2026"


def test_active_case_status_falls_back_to_change_summary():
    row = {"changed_fields": ["status"], "change_summary": "Status changed on 01.06.2026"}
    assert hearings.active_case_status(row) == "Status changed on 1 June 2026"


def test_active_case_status_falls_back_to_counsel_status():
    row = {"counsel_response_status": "Awaiting reply"}
    assert hearings.active_case_status(row) == "Counsel: Awaiting reply"


def test_active_case_status_empty_row_returns_empty_string():
    assert hearings.active_case_status({}) == ""


def test_active_case_status_change_summary_without_changed_fields_is_not_used():
    row = {"change_summary": "Status changed on 01.06.2026"}
    assert hearings.active_case_status(row) == ""




def test_court_contact_card_for_obligation_builds_card_on_success(monkeypatch):
    ob = {"matter_ref": "1234", "client": "Jane Doe"}
    monkeypatch.setattr(
        hearings.court_finder, "resolve_client_applicant_postcode",
        lambda query: {"ok": True, "postcode": "ZZ99 9ZZ"},
    )
    monkeypatch.setattr(hearings.court_finder, "normalise_postcode", lambda pc: "ZZ99 9ZZ")
    monkeypatch.setattr(
        hearings.court_finder, "find_nearest_courts",
        lambda postcode, service, detail_limit: {"ok": True, "top_courts": []},
    )
    monkeypatch.setattr(hearings.court_finder, "service_slug_for_label", lambda label: "slug")
    monkeypatch.setattr(
        hearings.court_finder, "build_court_contact_card",
        lambda result, ref: f"card for {ref}",
    )
    assert hearings.court_contact_card_for_obligation(ob) == "card for 1234"


def test_court_contact_card_for_obligation_empty_query_returns_none():
    assert hearings.court_contact_card_for_obligation({}) is None


def test_court_contact_card_for_obligation_postcode_lookup_failure_returns_none(monkeypatch):
    monkeypatch.setattr(
        hearings.court_finder, "resolve_client_applicant_postcode",
        lambda query: {"ok": False},
    )
    assert hearings.court_contact_card_for_obligation({"client": "Jane Doe"}) is None


def test_court_contact_card_for_obligation_blank_postcode_returns_none(monkeypatch):
    monkeypatch.setattr(
        hearings.court_finder, "resolve_client_applicant_postcode",
        lambda query: {"ok": True, "postcode": ""},
    )
    monkeypatch.setattr(hearings.court_finder, "normalise_postcode", lambda pc: "")
    assert hearings.court_contact_card_for_obligation({"client": "Jane Doe"}) is None


def test_court_contact_card_for_obligation_find_nearest_courts_failure_returns_none(monkeypatch):
    monkeypatch.setattr(
        hearings.court_finder, "resolve_client_applicant_postcode",
        lambda query: {"ok": True, "postcode": "ZZ99 9ZZ"},
    )
    monkeypatch.setattr(hearings.court_finder, "normalise_postcode", lambda pc: "ZZ99 9ZZ")
    monkeypatch.setattr(hearings.court_finder, "service_slug_for_label", lambda label: "slug")
    monkeypatch.setattr(
        hearings.court_finder, "find_nearest_courts",
        lambda postcode, service, detail_limit: {"ok": False},
    )
    assert hearings.court_contact_card_for_obligation({"client": "Jane Doe"}) is None


def test_court_contact_card_for_obligation_swallows_exceptions(monkeypatch):
    def _raise(query):
        raise RuntimeError("boom")

    monkeypatch.setattr(hearings.court_finder, "resolve_client_applicant_postcode", _raise)
    assert hearings.court_contact_card_for_obligation({"client": "Jane Doe"}) is None




def test_calendar_finder_result_rows_non_dict_returns_empty():
    assert hearings.calendar_finder_result_rows("not a dict") == []
    assert hearings.calendar_finder_result_rows(None) == []


def test_calendar_finder_result_rows_top_level_result_dict():
    assert hearings.calendar_finder_result_rows({"result": {"a": 1}}) == [{"a": 1}]


def test_calendar_finder_result_rows_top_level_results_list():
    payload = {"results": [{"a": 1}, {"a": 2}, "not-a-dict"]}
    assert hearings.calendar_finder_result_rows(payload) == [{"a": 1}, {"a": 2}]


def test_calendar_finder_result_rows_nested_results_and_result():
    payload = {
        "result": {
            "results": [{"a": 1}],
            "result": {"a": 2},
        },
    }
    rows = hearings.calendar_finder_result_rows(payload)
    assert rows == [{"results": [{"a": 1}], "result": {"a": 2}}, {"a": 1}, {"a": 2}]


def test_calendar_finder_result_rows_empty_dict_returns_empty():
    assert hearings.calendar_finder_result_rows({}) == []




def _no_startup_data(monkeypatch):
    monkeypatch.setattr(hearings, "latest_json", lambda pattern: (None, None))


def test_build_hearing_tool_response_returns_none_without_any_data(monkeypatch):
    _no_startup_data(monkeypatch)
    assert hearings.build_hearing_tool_response("what hearings are coming up") is None


def test_build_hearing_tool_response_includes_startup_run_when_scorecard_present(monkeypatch):
    def _fake_latest_json(pattern):
        if "scorecard" in pattern:
            return Path("scorecard-2026-06-19.json"), {"run_utc": "2026-06-19T06:00:00Z"}
        return None, None

    monkeypatch.setattr(hearings, "latest_json", _fake_latest_json)
    result = hearings.build_hearing_tool_response("hearings")
    assert "Startup run: 2026-06-19T06:00:00Z" in result
    assert "Tranches: same-day 0, high 0, normal 0, low 0." in result


def test_build_hearing_tool_response_no_dated_hearings_names_the_source_file(monkeypatch):
    def _fake_latest_json(pattern):
        if "graph-startup" in pattern:
            return Path("2026-06-19-readonly.json"), {"client_statuses": [], "rows": []}
        return None, None

    monkeypatch.setattr(hearings, "latest_json", _fake_latest_json)
    result = hearings.build_hearing_tool_response("hearings")
    assert "No dated hearings were parsed from 2026-06-19-readonly.json." in result


def test_build_hearing_tool_response_lists_and_sorts_dated_hearings(monkeypatch):
    graph = {
        "client_statuses": [
            {"client": "Priya Cedartest", "next_hearing": "30.06.2030"},
            {"client": "Jordan Aldertest", "next_hearing": "19.06.2030"},
        ],
        "rows": [],
    }

    def _fake_latest_json(pattern):
        if "graph-startup" in pattern:
            return Path("readonly.json"), graph
        return None, None

    monkeypatch.setattr(hearings, "latest_json", _fake_latest_json)
    monkeypatch.setattr(hearings, "calendar_hearing_state", lambda: {})
    result = hearings.build_hearing_tool_response("hearings")

    lines = result.splitlines()
    jordan_line = next(line for line in lines if "Jordan Aldertest" in line)
    priya_line = next(line for line in lines if "Priya Cedartest" in line)
    assert lines.index(jordan_line) < lines.index(priya_line)
    assert "19 June 2030" in jordan_line


def test_build_hearing_tool_response_shows_awaiting_when_not_redundant(monkeypatch):
    graph = {
        "client_statuses": [
            {
                "client": "Jordan Aldertest",
                "next_hearing": "19.06.2030",
                "awaiting": "Order from court",
            },
        ],
        "rows": [],
    }

    def _fake_latest_json(pattern):
        if "graph-startup" in pattern:
            return Path("readonly.json"), graph
        return None, None

    monkeypatch.setattr(hearings, "latest_json", _fake_latest_json)
    monkeypatch.setattr(hearings, "calendar_hearing_state", lambda: {})
    result = hearings.build_hearing_tool_response("hearings")
    assert "Awaiting: Order from court" in result


def test_build_hearing_tool_response_suppresses_redundant_awaiting_text(monkeypatch):
    graph = {
        "client_statuses": [
            {
                "client": "Jordan Aldertest",
                "next_hearing": "19.06.2030",
                "awaiting": "Hearing on 19.06.2030",
            },
        ],
        "rows": [],
    }

    def _fake_latest_json(pattern):
        if "graph-startup" in pattern:
            return Path("readonly.json"), graph
        return None, None

    monkeypatch.setattr(hearings, "latest_json", _fake_latest_json)
    monkeypatch.setattr(hearings, "calendar_hearing_state", lambda: {})
    result = hearings.build_hearing_tool_response("hearings")
    assert "Awaiting:" not in result
