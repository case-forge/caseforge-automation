import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "documents" / "client_info_cleaner.py"
spec = importlib.util.spec_from_file_location("client_info_cleaner", SCRIPT)
cleaner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = cleaner
spec.loader.exec_module(cleaner)


def test_witness_statement_beats_fl401_and_flags_decade_typo():
    result = cleaner.clean_client_info(
        {
            "sources": [
                {
                    "source_kind": "witness_statement",
                    "source_label": "Approved witness statement",
                    "facts": {"relationship_end": "2023"},
                },
                {
                    "source_kind": "fl401",
                    "source_label": "FL401",
                    "facts": {"relationship_end": "2013"},
                },
            ]
        }
    )

    assert result["chosen"]["relationship_end"]["value"] == "2023"
    assert result["chosen"]["relationship_end"]["source_kind"] == "witness_statement"
    assert result["summary"]["blockers"] == 1
    assert result["issues"][0]["code"] == "LIKELY_DECADE_TYPO"


def test_referral_beats_fl401_when_witness_statement_has_no_value():
    result = cleaner.clean_client_info(
        {
            "sources": [
                {
                    "source_kind": "referral",
                    "source_label": "referrer referral",
                    "facts": {"relationship_end": "2023"},
                },
                {
                    "source_kind": "fl401",
                    "source_label": "FL401",
                    "facts": {"relationship_end": "2013"},
                },
            ]
        }
    )

    assert result["chosen"]["relationship_end"]["value"] == "2023"
    assert result["chosen"]["relationship_end"]["source_kind"] == "referral"


def test_later_source_date_wins_within_same_priority():
    result = cleaner.clean_client_info(
        {
            "sources": [
                {
                    "source_kind": "referral",
                    "source_label": "Earlier referral",
                    "source_date": "2026-05-18",
                    "facts": {"applicant_phone": "07700 900111"},
                },
                {
                    "source_kind": "intro",
                    "source_label": "Updated intro",
                    "source_date": "2026-05-20",
                    "facts": {"applicant_phone": "07700 900222"},
                },
            ]
        }
    )

    assert result["chosen"]["applicant_phone"]["value"] == "07700 900222"
    assert result["chosen"]["applicant_phone"]["source_label"] == "Updated intro"


def test_current_address_update_replaces_without_history_recommendation():
    result = cleaner.clean_client_info(
        {
            "sql_current": {
                "applicant_address": "1 Old Street, London, ZZ99 9ZZ",
            },
            "sources": [
                {
                    "source_kind": "witness_statement",
                    "source_label": "Approved witness statement",
                    "facts": {
                        "applicant_address": "2 New Street, London, ZZ99 9ZZ",
                    },
                }
            ],
        }
    )

    assert result["updates"] == [
        {
            "field": "applicant_address",
            "target": "matter_parties.address_text[Applicant]",
            "current_value": "1 Old Street, London, ZZ99 9ZZ",
            "new_value": "2 New Street, London, ZZ99 9ZZ",
            "source_kind": "witness_statement",
            "source_label": "Approved witness statement",
            "reason": "replace current value from highest-priority parsed source",
        }
    ]


def test_fl401_address_without_postcode_is_review_issue():
    result = cleaner.clean_client_info(
        {
            "sources": [
                {
                    "source_kind": "fl401",
                    "source_label": "FL401",
                    "facts": {
                        "applicant_address": "10 Example Road, London",
                        "relationship_start": "2020",
                        "relationship_end": "2023",
                    },
                }
            ]
        }
    )

    assert any(issue["code"] == "MISSING_POSTCODE" for issue in result["issues"])
    assert result["summary"]["review"] == 1


def test_c8_applicant_address_does_not_trigger_postcode_issue():
    result = cleaner.clean_client_info(
        {
            "sources": [
                {
                    "source_kind": "witness_statement",
                    "source_label": "Approved witness statement",
                    "facts": {
                        "has_c8": "yes",
                        "applicant_address": "Confidential address",
                    },
                }
            ]
        }
    )

    assert result["issues"] == []
