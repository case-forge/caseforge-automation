from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import child_age

TODAY = dt.date(2026, 9, 27)


def test_age_turns_over_on_the_birthday_not_before():
    assert child_age.age_on("2016-09-27", TODAY) == 10
    assert child_age.age_on("2016-09-28", TODAY) == 9


def test_age_is_none_for_unparseable_or_future_dob():
    assert child_age.age_on("", TODAY) is None
    assert child_age.age_on("not a date", TODAY) is None
    assert child_age.age_on("2030-01-01", TODAY) is None


def test_a_stored_age_is_replaced_not_trusted():
    stale = "Milo James Eldertest (2016-10-02, age 9)"
    assert child_age.with_live_ages(stale, TODAY) == "Milo James Eldertest (2016-10-02, age 9)"
    stale_by_a_year = "Milo James Eldertest (2016-10-02, age 7)"
    assert child_age.with_live_ages(stale_by_a_year, TODAY) == "Milo James Eldertest (2016-10-02, age 9)"


def test_the_age_moves_when_the_date_moves():
    summary = "Ivy Reedtest (2020-03-04)"
    assert child_age.with_live_ages(summary, dt.date(2026, 3, 3)) == "Ivy Reedtest (2020-03-04, age 5)"
    assert child_age.with_live_ages(summary, dt.date(2026, 3, 4)) == "Ivy Reedtest (2020-03-04, age 6)"


def test_every_child_in_the_summary_gets_an_age():
    summary = "Ivy Reedtest (2020-03-04); Sam T Reedtest (2018-12-25, age 6); New Child"
    assert child_age.with_live_ages(summary, TODAY) == (
        "Ivy Reedtest (2020-03-04, age 6); Sam T Reedtest (2018-12-25, age 7); New Child"
    )


def test_a_future_dob_loses_its_stale_age_rather_than_keeping_it():
    assert child_age.with_live_ages("Baby (2030-01-01, age 4)", TODAY) == "Baby (2030-01-01)"


def test_text_without_a_dob_is_untouched():
    assert child_age.with_live_ages("", TODAY) == ""
    assert child_age.with_live_ages("Two children, names to follow", TODAY) == "Two children, names to follow"
    assert child_age.with_live_ages("Ivy Reedtest (born March 2020)", TODAY) == "Ivy Reedtest (born March 2020)"


def test_strip_ages_leaves_the_dob():
    assert child_age.strip_ages("Ivy Reedtest (2020-03-04, age 6); Sam (2018-12-25)") == (
        "Ivy Reedtest (2020-03-04); Sam (2018-12-25)"
    )
