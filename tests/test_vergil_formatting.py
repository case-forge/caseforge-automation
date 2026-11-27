from __future__ import annotations

import datetime as real_dt
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil import formatting



@pytest.fixture
def freeze(monkeypatch):

    def _freeze(instant_utc: real_dt.datetime | None = None, today: real_dt.date | None = None):
        fake = types.SimpleNamespace(
            datetime=real_dt.datetime,
            date=real_dt.date,
            timezone=real_dt.timezone,
            timedelta=real_dt.timedelta,
        )
        if instant_utc is not None:
            frozen_datetime = type("_FrozenDatetime", (real_dt.datetime,), {})

            def _now(cls, tz=None):
                return instant_utc if tz is None else instant_utc.astimezone(tz)

            frozen_datetime.now = classmethod(_now)
            fake.datetime = frozen_datetime
        if today is not None:
            frozen_date = type("_FrozenDate", (real_dt.date,), {})
            frozen_date.today = classmethod(lambda cls: today)
            fake.date = frozen_date
            monkeypatch.setattr(formatting, "london_today", lambda: today)
        monkeypatch.setattr(formatting, "dt", fake)

    return _freeze



@pytest.mark.parametrize(
    "iso,expected",
    [
        ("", ""),
        (None, ""),
        ("not-a-date", ""),
        ("2024-01-01T10:00:00Z", "01 Jan"),
        ("2024-01-01T10:00:00", "01 Jan"),
        ("2024-06-15T23:30:00Z", "16 Jun"),
    ],
)
def test_format_session_date(iso, expected):
    assert formatting.format_session_date(iso) == expected



@pytest.mark.parametrize(
    "size,expected",
    [
        (0, "0 B"),
        (512, "512 B"),
        (2048, "2.0 KB"),
        (5 * 1024 * 1024, "5.0 MB"),
        (1024 ** 3, "1.0 GB"),
        (1024 ** 4, "1024.0 GB"),
    ],
)
def test_format_bytes(size, expected):
    assert formatting.format_bytes(size) == expected



@pytest.mark.parametrize(
    "value,expected",
    [
        ("", None),
        (None, None),
        ("not-a-date", None),
        (
            "2024-01-01T10:00:00Z",
            real_dt.datetime(2024, 1, 1, 10, 0, 0, tzinfo=real_dt.timezone.utc),
        ),
        (
            "2024-01-01T10:00:00+02:00",
            real_dt.datetime(2024, 1, 1, 10, 0, 0, tzinfo=real_dt.timezone(real_dt.timedelta(hours=2))),
        ),
    ],
)
def test_parse_iso_dt(value, expected):
    assert formatting.parse_iso_dt(value) == expected



def test_format_countdown_invalid_target_is_unknown():
    assert formatting.format_countdown("") == "Unknown"
    assert formatting.format_countdown("garbage") == "Unknown"


def test_format_countdown_future(freeze):
    freeze(instant_utc=real_dt.datetime(2026, 1, 1, 10, 0, 0, tzinfo=real_dt.timezone.utc))
    assert formatting.format_countdown("2026-01-01T12:30:00Z") == "2h 30m"


def test_format_countdown_past_is_negative(freeze):
    freeze(instant_utc=real_dt.datetime(2026, 1, 1, 10, 0, 0, tzinfo=real_dt.timezone.utc))
    assert formatting.format_countdown("2026-01-01T09:00:00Z") == "-1h 0m"



@pytest.mark.parametrize(
    "until_str,expected",
    [
        ("", ""),
        ("garbage", "garbage"),
        ("2024-01-01T10:00:00Z", "1 Jan, 10:00"),
        ("2024-06-15T23:30:00Z", "16 Jun, 00:30"),
    ],
)
def test_format_outage_time(until_str, expected):
    assert formatting.format_outage_time(until_str) == expected



@pytest.mark.parametrize(
    "value,expected",
    [
        ("", None),
        ("no date in this text", None),
        ("15/05/2026", real_dt.date(2026, 5, 15)),
        ("15.05.2026", real_dt.date(2026, 5, 15)),
        ("15-05-26", real_dt.date(2026, 5, 15)),
        ("2026-05-15", real_dt.date(2026, 5, 15)),
        ("hearing listed for 15th May 2026", real_dt.date(2026, 5, 15)),
        ("hearing on 1 June 2027", real_dt.date(2027, 6, 1)),
        ("31/02/2026", None),
    ],
)
def test_parse_hearing_date(value, expected):
    assert formatting.parse_hearing_date(value) == expected



@pytest.mark.parametrize(
    "value,expected",
    [
        ("", None),
        ("no time here", None),
        ("10:30", (10, 30)),
        ("at 10:30", (10, 30)),
        ("10:30 PM", (22, 30)),
        ("at 2pm", (14, 0)),
        ("12:15 AM", (0, 15)),
        ("12:00 PM", (12, 0)),
        ("25:00", None),
    ],
)
def test_parse_hearing_time(value, expected):
    assert formatting.parse_hearing_time(value) == expected



@pytest.mark.parametrize(
    "value,expected",
    [
        (None, ""),
        ((9, 5), "09:05"),
        ((23, 59), "23:59"),
        ((0, 0), "00:00"),
    ],
)
def test_format_hearing_time(value, expected):
    assert formatting.format_hearing_time(value) == expected



def test_format_run_time(freeze):
    freeze(instant_utc=real_dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=real_dt.timezone.utc))
    result = formatting.format_run_time()
    assert result == (
        "London time: Thursday 01 January 2026, 12:00 GMT\n"
        "UTC: Thursday 01 January 2026, 12:00 UTC"
    )



@pytest.mark.parametrize(
    "text,expected",
    [
        ("", {}),
        ("nothing matches this line", {}),
        (
            "Smith / Client 1, 2",
            {"client": "Smith", "caller": "Client", "codes": ["1", "2"], "line": "Smith / Client 1, 2"},
        ),
        (
            "garbage first line\nJones / Court 3",
            {"client": "Jones", "caller": "Court", "codes": ["3"], "line": "Jones / Court 3"},
        ),
        (
            "Lichentest / other 4,4,5",
            {"client": "Lichentest", "caller": "Other", "codes": ["4", "5"], "line": "Lichentest / other 4,4,5"},
        ),
        (
            "Kim / respondent 2",
            {"client": "Kim", "caller": "Respondent", "codes": ["2"], "line": "Kim / respondent 2"},
        ),
    ],
)
def test_parse_attendance_switchboard_shorthand(text, expected):
    assert formatting.parse_attendance_switchboard_shorthand(text) == expected


def test_attendance_switchboard_callers_table_is_the_expected_shape():
    assert formatting.ATTENDANCE_SWITCHBOARD_CALLERS == {
        "client": "Client",
        "court": "Court",
        "respondent": "Respondent",
        "counsel": "Counsel",
        "other": "Other",
    }



def test_parse_backdate_last_weekday(freeze):
    freeze(today=real_dt.date(2026, 7, 29))
    assert formatting.parse_backdate("last monday") == real_dt.date(2026, 7, 27)
    assert formatting.parse_backdate("last wednesday") == real_dt.date(2026, 7, 22)


def test_parse_backdate_month_day(freeze):
    freeze(today=real_dt.date(2026, 1, 1))
    assert formatting.parse_backdate("backdate to 1 may") == real_dt.date(2026, 5, 1)
    assert formatting.parse_backdate("may 1st 2027") == real_dt.date(2027, 5, 1)


def test_parse_backdate_iso_form(freeze):
    freeze(today=real_dt.date(2026, 1, 1))
    assert formatting.parse_backdate("backdate to 2025-12-25") == real_dt.date(2025, 12, 25)
    assert formatting.parse_backdate("from 2025-12-25") == real_dt.date(2025, 12, 25)


def test_parse_backdate_no_match_returns_none(freeze):
    freeze(today=real_dt.date(2026, 1, 1))
    assert formatting.parse_backdate("no date mentioned at all") is None



@pytest.mark.parametrize(
    "value,expected",
    [
        ("", ""),
        (None, ""),
        ("not-a-date-at-all", "not-a-date"),
        ("2026-05-01T00:00:00Z", "1 May"),
        ("2026-12-25T09:30:00+00:00", "25 December"),
    ],
)
def test_format_an_fast_date(value, expected):
    assert formatting.format_an_fast_date(value) == expected


def test_month_names_table_is_the_expected_shape():
    assert formatting.MONTH_NAMES[0] == ""
    assert formatting.MONTH_NAMES[1] == "January"
    assert formatting.MONTH_NAMES[12] == "December"
    assert len(formatting.MONTH_NAMES) == 13



@pytest.mark.parametrize(
    "value,expected",
    [
        ("", ""),
        (None, ""),
        ("plain text", "plain text"),
        ("<strong>bold</strong>", "bold"),
        ("a<br>b", "ab"),
        ("  extra   space  ", "extra space"),
        ("<a href='x'>link</a> tail", "link tail"),
    ],
)
def test_clean_markdown_cell(value, expected):
    assert formatting.clean_markdown_cell(value) == expected



def test_markdown_cell_passes_short_text_through():
    assert formatting.markdown_cell("hello") == "hello"


def test_markdown_cell_collapses_internal_whitespace():
    assert formatting.markdown_cell("a   b\nc") == "a b c"


def test_markdown_cell_none_and_falsy_become_empty_string():
    assert formatting.markdown_cell(None) == ""
    assert formatting.markdown_cell(0) == ""


def test_markdown_cell_truncates_at_limit_with_ellipsis():
    text = "x" * 200
    result = formatting.markdown_cell(text, limit=10)
    assert result == "x" * 9 + "..."
    assert len(result) == 12


def test_markdown_cell_default_limit_is_180():
    text = "y" * 250
    result = formatting.markdown_cell(text)
    assert result == "y" * 179 + "..."


def test_markdown_cell_escapes_pipe_characters():
    assert formatting.markdown_cell("a|b|c") == "a/b/c"


def test_markdown_cell_does_not_truncate_text_exactly_at_limit():
    text = "z" * 180
    assert formatting.markdown_cell(text) == text



def test_markdown_table_empty_rows_returns_empty_string():
    assert formatting.markdown_table(["A", "B"], []) == ""


def test_markdown_table_builds_header_divider_and_body():
    result = formatting.markdown_table(["Name", "Status"], [["Alice", "OK"], ["Bob", "Late"]])
    lines = result.split("\n")
    assert lines[0] == "| Name | Status |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| Alice | OK |"
    assert lines[3] == "| Bob | Late |"


def test_markdown_table_cell_values_are_cleaned_through_markdown_cell():
    result = formatting.markdown_table(["Col"], [["a|b" + "z" * 200]])
    body_cell = result.split("\n")[2]
    assert body_cell == "| " + formatting.markdown_cell("a|b" + "z" * 200) + " |"
    assert "..." in body_cell
    assert "a/b" in body_cell


def test_markdown_table_header_cells_use_the_narrower_80_char_limit():
    long_header = "H" * 200
    result = formatting.markdown_table([long_header], [["x"]])
    header_line = result.split("\n")[0]
    assert header_line == "| " + "H" * 79 + "... |"


def test_markdown_table_single_column():
    result = formatting.markdown_table(["Only"], [["a"], ["b"]])
    assert result.split("\n") == ["| Only |", "| --- |", "| a |", "| b |"]
