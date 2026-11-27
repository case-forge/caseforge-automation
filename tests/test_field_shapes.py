from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import field_shapes


def test_looks_like_nino_matches_real_shape():
    assert field_shapes.looks_like_nino("QQ123456C")
    assert field_shapes.looks_like_nino("  pk827897b  ")


def test_looks_like_nino_rejects_non_nino():
    assert not field_shapes.looks_like_nino("13259990002")
    assert not field_shapes.looks_like_nino("URN-2026-991")
    assert not field_shapes.looks_like_nino("")


def test_looks_like_email_whole_string():
    assert field_shapes.looks_like_email("solicitor@example.org")
    assert not field_shapes.looks_like_email("Anika Mallardtest")
    assert not field_shapes.looks_like_email("not an email at all")


def test_looks_like_email_search_anywhere():
    assert field_shapes.looks_like_email(
        "Contact her at test@example.com for more info", whole_string=False
    )
    assert not field_shapes.looks_like_email("no email in this sentence", whole_string=False)


def test_looks_like_uk_phone():
    assert field_shapes.looks_like_uk_phone("07700900988")
    assert field_shapes.looks_like_uk_phone("+44 7700 900988")
    assert not field_shapes.looks_like_uk_phone("not a number")


def test_looks_like_uk_postcode():
    assert field_shapes.looks_like_uk_postcode("AB1 2CD")
    assert field_shapes.looks_like_uk_postcode("ab12cd")
    assert not field_shapes.looks_like_uk_postcode("not a postcode")


def test_looks_like_val_company_reference():
    assert field_shapes.looks_like_val_company_reference("260811/01FL")
    assert not field_shapes.looks_like_val_company_reference("QQ123456C")


def test_classify_picks_the_right_shape():
    assert field_shapes.classify("QQ123456C") == "nino"
    assert field_shapes.classify("solicitor@example.org") == "email"
    assert field_shapes.classify("AB1 2CD") == "uk_postcode"
    assert field_shapes.classify("260811/01FL") == "caseforge_company_reference"
    assert field_shapes.classify("07700900988") == "uk_phone"
    assert field_shapes.classify("Anika Mallardtest") is None
    assert field_shapes.classify("") is None


def test_classify_checks_nino_before_looser_shapes():
    assert field_shapes.classify("QQ123456C") == "nino"


def test_reject_if_wrong_shape_allows_a_real_match():
    assert field_shapes.reject_if_wrong_shape("QQ123456C", "nino") is False
    assert field_shapes.reject_if_wrong_shape("solicitor@example.org", "email") is False


def test_reject_if_wrong_shape_catches_the_name_as_email_failure_mode():
    assert field_shapes.reject_if_wrong_shape("Anika Mallardtest", "email") is True


def test_reject_if_wrong_shape_catches_the_original_nino_as_crime_ref_incident():
    assert field_shapes.reject_if_wrong_shape("QQ123456C", "caseforge_company_reference") is True


def test_reject_if_wrong_shape_fails_open_on_an_unknown_expected_shape():
    assert field_shapes.reject_if_wrong_shape("anything", "some_unregistered_shape") is False
