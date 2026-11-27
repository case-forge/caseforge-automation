from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil import intake_log


def test_returns_empty_list_when_intake_file_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(intake_log, "REPO_ROOT", tmp_path)
    assert intake_log.load_referralpartner_intake_log_today("2026-08-03") == []


def _write_intake(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_filters_to_todays_referrals_with_accepted_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(intake_log, "REPO_ROOT", tmp_path)
    path = tmp_path / "telemetry" / "referralpartner-intake" / "intake.jsonl"
    _write_intake(
        path,
        [
            {"name": "Referral Today", "referral_date": "2026-08-03", "status": "inserted"},
            {"name": "Referral Yesterday", "referral_date": "2026-08-02", "status": "inserted"},
            {"name": "Rejected Today", "referral_date": "2026-08-03", "status": "rejected"},
        ],
    )
    rows = intake_log.load_referralpartner_intake_log_today("2026-08-03")
    assert [row["name"] for row in rows] == ["Referral Today"]


def test_already_in_sql_status_also_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(intake_log, "REPO_ROOT", tmp_path)
    path = tmp_path / "telemetry" / "referralpartner-intake" / "intake.jsonl"
    _write_intake(
        path,
        [{"name": "Test Referral", "referral_date": "2026-08-03", "status": "already-in-sql"}],
    )
    rows = intake_log.load_referralpartner_intake_log_today("2026-08-03")
    assert len(rows) == 1


def test_skips_rows_with_no_name_and_malformed_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(intake_log, "REPO_ROOT", tmp_path)
    path = tmp_path / "telemetry" / "referralpartner-intake" / "intake.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                json.dumps({"name": "", "referral_date": "2026-08-03", "status": "inserted"}),
                "not json",
                json.dumps({"name": "Good Referral", "referral_date": "2026-08-03", "status": "inserted"}),
            ]
        ),
        encoding="utf-8",
    )
    rows = intake_log.load_referralpartner_intake_log_today("2026-08-03")
    assert [row["name"] for row in rows] == ["Good Referral"]


def test_summary_includes_order_type_respondent_and_c8_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(intake_log, "REPO_ROOT", tmp_path)
    path = tmp_path / "telemetry" / "referralpartner-intake" / "intake.jsonl"
    _write_intake(
        path,
        [
            {
                "name": "Fixture Client",
                "referral_date": "2026-08-03",
                "status": "inserted",
                "has_c8": True,
                "fields": {"order_type": "NMO", "respondent_name": "Fixture Respondent"},
            }
        ],
    )
    rows = intake_log.load_referralpartner_intake_log_today("2026-08-03")
    assert rows[0]["orders"] == "NMO"
    assert rows[0]["referral_source"] == "ReferralPartner"
    assert rows[0]["summary"] == "NMO · R: Fixture Respondent · C8"


def test_dedupes_by_case_insensitive_name_keeping_last_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(intake_log, "REPO_ROOT", tmp_path)
    path = tmp_path / "telemetry" / "referralpartner-intake" / "intake.jsonl"
    _write_intake(
        path,
        [
            {"name": "Jane Doe", "referral_date": "2026-08-03", "status": "inserted", "fields": {"order_type": "NMO"}},
            {"name": "JANE DOE", "referral_date": "2026-08-03", "status": "inserted", "fields": {"order_type": "NMO PSO"}},
        ],
    )
    rows = intake_log.load_referralpartner_intake_log_today("2026-08-03")
    assert len(rows) == 1
    assert rows[0]["orders"] == "NMO PSO"


def test_merge_combines_disjoint_names():
    merged = intake_log.merge_new_client_rows(
        [{"name": "Alice Example"}],
        [{"name": "Bob Example"}],
    )
    assert {row["name"] for row in merged} == {"Alice Example", "Bob Example"}


def test_merge_is_case_insensitive_on_name_and_secondary_overlays_primary():
    merged = intake_log.merge_new_client_rows(
        [{"name": "Jane Bloggs", "orders": "NMO"}],
        [{"name": "jane bloggs", "orders": "NMO PSO"}],
    )
    assert len(merged) == 1
    assert merged[0]["orders"] == "NMO PSO"


def test_merge_only_overwrites_with_truthy_values():
    merged = intake_log.merge_new_client_rows(
        [{"name": "Jane Bloggs", "orders": "NMO"}],
        [{"name": "Jane Bloggs", "orders": ""}],
    )
    assert merged[0]["orders"] == "NMO"


def test_merge_skips_rows_with_no_name():
    merged = intake_log.merge_new_client_rows(
        [{"name": "Jane Bloggs"}],
        [{"orders": "NMO"}],
    )
    assert len(merged) == 1
    assert merged[0]["name"] == "Jane Bloggs"


def test_merge_preserves_first_seen_order():
    merged = intake_log.merge_new_client_rows(
        [{"name": "Charlie"}, {"name": "Alice"}],
        [{"name": "Bob"}],
    )
    assert [row["name"] for row in merged] == ["Charlie", "Alice", "Bob"]
