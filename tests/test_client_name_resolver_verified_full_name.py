import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "sql"))

from sql import client_name_resolver as cnr


def _candidate(name: str, verified_middle: str = "") -> cnr.CandidateRecord:
    candidate = cnr.CandidateRecord(
        canonical_name=name,
        root_card_path=Path("."),
        query_forms=cnr.build_query_forms(name),
    )
    candidate.verified_name_middle = verified_middle
    return candidate


def _score(query: str, candidate: cnr.CandidateRecord):
    score_parts: list[int] = []
    match_sources: list[str] = []
    support_signals: list[str] = []
    cnr.score_verified_full_name(
        cnr.build_query_forms(query), candidate, score_parts, match_sources, support_signals
    )
    return score_parts, match_sources


def test_full_legal_name_matches_a_verified_middle_name():
    candidate = _candidate("Graham Damsontest", verified_middle="Daniel Heathtest")
    score_parts, match_sources = _score("Graham Daniel Heathtest Damsontest", candidate)
    assert score_parts == [40]
    assert "verified_full_name:middle_match" in match_sources


def test_never_fires_without_a_verified_middle_name():
    candidate = _candidate("Simone Ashtest")
    score_parts, match_sources = _score("Simone Slatetest Ashtest", candidate)
    assert score_parts == []
    assert match_sources == []


def test_a_wrong_middle_name_does_not_match_a_real_verified_one():
    candidate = _candidate("Graham Damsontest", verified_middle="Daniel Heathtest")
    score_parts, match_sources = _score("Graham Wrongname Damsontest", candidate)
    assert score_parts == []
    assert match_sources == []


def test_first_or_last_token_mismatch_never_fires():
    candidate = _candidate("Graham Damsontest", verified_middle="Daniel Heathtest")
    score_parts, match_sources = _score("Graham Daniel Heathtest Ashtest", candidate)
    assert score_parts == []
    assert match_sources == []


def test_a_two_token_query_never_fires_regardless_of_verified_middle():
    candidate = _candidate("Graham Damsontest", verified_middle="Daniel Heathtest")
    score_parts, match_sources = _score("Graham Damsontest", candidate)
    assert score_parts == []
    assert match_sources == []
