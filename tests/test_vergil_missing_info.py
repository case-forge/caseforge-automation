from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _make_db(path: Path, *, with_address_text: bool) -> None:
    text_col = "address_text TEXT," if with_address_text else ""
    with sqlite3.connect(path) as conn:
        conn.executescript(
            f"""
            CREATE TABLE people (
                person_id INTEGER PRIMARY KEY, canonical_name TEXT, dob_iso TEXT,
                email_primary TEXT, phone_primary TEXT, {text_col}
                address_line1 TEXT, address_line2 TEXT, address_line3 TEXT, address_line4 TEXT, address_postcode TEXT
            );
            CREATE TABLE matters (
                matter_id INTEGER PRIMARY KEY, primary_person_id INTEGER, canonical_name TEXT, closed_at TEXT
            );
            """
        )
        people = [
            (1, "Complete Client", "1990-01-01", "a@example.invalid", "01632 960001", "1 Test Road", "", "", "", "TE1 1ST"),
            (2, "No Address", "1990-01-02", "b@example.invalid", "", "", "", "", "", ""),
            (3, "No Contact", "1990-01-03", "", "", "2 Test Road", "", "", "", "TE2 2ST"),
            (4, "No Dob", "", "c@example.invalid", "", "3 Test Road", "", "", "", "TE3 3ST"),
            (5, "Closed Gap", "", "", "", "", "", "", "", ""),
            (6, "Phone Only", "1990-01-06", "", "01632 960006", "4 Test Road", "", "", "", ""),
        ]
        for person in people:
            conn.execute(
                "INSERT INTO people (person_id, canonical_name, dob_iso, email_primary, phone_primary, "
                "address_line1, address_line2, address_line3, address_line4, address_postcode) VALUES (?,?,?,?,?,?,?,?,?,?)",
                person,
            )
        for matter_id, person_id, closed in ((101, 1, None), (102, 2, None), (103, 3, None), (104, 4, None), (105, 5, "2026-01-01"), (106, 6, None)):
            conn.execute(
                "INSERT INTO matters (matter_id, primary_person_id, canonical_name, closed_at) VALUES (?,?,?,?)",
                (matter_id, person_id, f"Matter {matter_id}", closed),
            )


@pytest.fixture
def missing_info(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite3"
    _make_db(db, with_address_text=False)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    import clientdb_sql

    importlib.reload(clientdb_sql)
    from vergil import missing_info as mi

    importlib.reload(mi)
    return mi, db


def test_open_matters_missing_something_are_listed_with_what_is_missing(missing_info):
    mi, _ = missing_info
    found = {row["matter_id"]: row["missing"] for row in mi.list_matters_missing_info()}
    assert found == {
        "102": ["address"],
        "103": ["telephone or email"],
        "104": ["date of birth"],
    }


def test_a_complete_client_and_a_closed_matter_are_not_listed(missing_info):
    mi, _ = missing_info
    ids = {row["matter_id"] for row in mi.list_matters_missing_info()}
    assert "101" not in ids
    assert "105" not in ids


def test_a_phone_alone_is_enough_contact_and_an_address_line_without_a_postcode_counts_as_an_address(missing_info):
    mi, _ = missing_info
    ids = {row["matter_id"] for row in mi.list_matters_missing_info()}
    assert "106" not in ids


def test_an_unsplit_address_text_counts_as_an_address(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite3"
    _make_db(db, with_address_text=True)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE people SET address_text = '9 Old Lane, Testville' WHERE person_id = 2")
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    import clientdb_sql

    importlib.reload(clientdb_sql)
    from vergil import missing_info as mi

    importlib.reload(mi)
    assert "102" not in {row["matter_id"] for row in mi.list_matters_missing_info()}


def test_the_review_entry_describes_the_gap_without_any_client_detail(missing_info):
    mi, _ = missing_info
    entry = mi.review_entry({"matter_id": "103", "missing": ["address", "telephone or email"], "client_name": "Someone"})
    assert entry["review_id"] == "auto:103"
    assert entry["matter_id"] == "103"
    assert entry["field_label"] == "Missing information"
    assert entry["note"] == "Missing: address, telephone or email"
    assert entry["flagged_by"] == "Automatic"
    assert entry["resolved_at"] is None


def test_a_client_with_no_folder_gets_its_own_line_never_missing_referral_form():
    pytest.importorskip("graph_files")
    from vergil import missing_info

    assert missing_info.no_folder_entry("9301", "no_folder")["field_label"] == "No folder recorded"
    assert missing_info.no_folder_entry("9301", "folder_not_found")["field_label"] == "Recorded folder not found"
    entry = missing_info.no_folder_entry("9301", "no_folder")
    assert entry["field_name"] == "no_folder_for_referral" and entry["field_name"] != missing_info.referral_entry("9301")["field_name"]
    assert "Missing referral form" not in entry["note"] and entry["client_name"] == ""
