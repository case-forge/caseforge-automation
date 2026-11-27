import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from documents.letters import dating as d

D = dt.date


def test_opening_is_a_week_after_arrival_and_never_post_dated():
    assert d.letter_date("opening", D(2026, 10, 20), arrival=D(2026, 10, 1)) == (D(2026, 10, 8), D(2026, 10, 8))
    assert d.letter_date("opening", D(2026, 10, 3), arrival=D(2026, 10, 1))[0] == D(2026, 10, 3)


def test_court_outcome_is_a_week_after_the_hearing():
    assert d.letter_date("court-outcome", D(2026, 11, 30), hearing=D(2026, 11, 2))[0] == D(2026, 11, 9)


def test_closing_is_a_month_after_last_order_or_following_note():
    assert d.letter_date("closing", D(2026, 12, 1), last_order=D(2026, 9, 1))[0] == D(2026, 10, 1)
    assert d.letter_date("closing", D(2026, 12, 1), last_order=D(2026, 9, 1), notes=[D(2026, 10, 10)])[0] == D(2026, 11, 10)


def test_a_note_a_year_later_does_not_move_the_closing_letter():
    out = d.letter_date("closing", D(2027, 12, 1), last_order=D(2026, 9, 1), notes=[D(2027, 9, 5)])
    assert out == (D(2026, 10, 1), D(2026, 10, 1))


def test_notes_chain_only_while_within_six_months_of_each_other():
    notes = [D(2027, 1, 1), D(2027, 6, 1), D(2028, 6, 1)]
    assert d.closing_anchor(D(2026, 9, 1), notes) == D(2027, 6, 1)


def test_month_end_is_clamped():
    assert d.add_months(D(2026, 1, 31), 1) == D(2026, 2, 28)


def test_unknown_anchor_leaves_today():
    assert d.letter_date("opening", D(2026, 10, 20)) == (D(2026, 10, 20), None)
