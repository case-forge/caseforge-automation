from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from documents import spelling_autofix as sa


def test_osa_distance_counts_adjacent_swap_as_one():
    assert sa.osa_distance("recieved", "received") == 1
    assert sa.osa_distance("cente", "centre") == 1
    assert sa.osa_distance("cente", "cent") == 1
    assert sa.osa_distance("abc", "xyz") == 3


def test_unique_closest_candidate_is_applied():
    assert sa.choose_replacement("definately", ["definitely"]) == ("definitely", "")


def test_adjacent_swap_beats_a_tied_substitution():
    replacement, reason = sa.choose_replacement("recieved", ["relieved", "received"])
    assert (replacement, reason) == ("received", "")


def test_genuine_tie_is_left_for_a_human():
    replacement, reason = sa.choose_replacement("cente", ["cent", "centre"])
    assert replacement == ""
    assert reason.startswith("ambiguous")


def test_far_suggestions_are_not_applied():
    assert sa.choose_replacement("dupatta", ["quota", "mutt"])[0] == ""


def test_us_spelling_takes_the_british_counterpart_over_a_tie():
    if not sa._us_uk_words()[0]:
        pytest.skip("system word lists not installed")
    assert sa.choose_replacement("color", ["colour", "colon"]) == ("colour", "")


def test_no_checker_is_called_from_here():
    assert not hasattr(sa, "plan_edits") and not hasattr(sa, "prose_lint")
