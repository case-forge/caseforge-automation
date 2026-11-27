import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.sql import clean_sql_withheld_contact_markers as cleaner


def _make_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE people (
                person_id INTEGER PRIMARY KEY,
                canonical_name TEXT,
                phone_primary TEXT,
                phone_digits TEXT,
                email_primary TEXT,
                updated_utc TEXT
            );
            CREATE TABLE matters (
                matter_id INTEGER PRIMARY KEY,
                primary_person_id INTEGER,
                has_c8 INTEGER,
                withheld_fields TEXT,
                updated_utc TEXT
            );
            CREATE TABLE matter_parties (
                matter_party_id INTEGER PRIMARY KEY,
                matter_id INTEGER,
                role TEXT,
                display_name TEXT,
                address_text TEXT,
                phone_primary TEXT,
                phone_digits TEXT,
                phone_digits_key TEXT,
                email_primary TEXT,
                email_primary_key TEXT,
                updated_utc TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO people VALUES (1, 'Jane Client', 'w.h. 07700 900123', '', 'withhold jane@example.test', NULL)"
        )
        conn.execute("INSERT INTO matters VALUES (10, 1, 0, '', NULL)")
        conn.execute(
            """
            INSERT INTO matter_parties VALUES (
                100, 10, 'Applicant', 'Jane Client',
                'w/h - 1 Example Street',
                'withhold phone: 07700 900123',
                '',
                '',
                'W.H. jane@example.test',
                '',
                NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO matter_parties VALUES (
                101, 10, 'Respondent', 'John Respondent',
                'w/h - 2 Other Street',
                '',
                '',
                '',
                '',
                '',
                NULL
            )
            """
        )


def test_strip_leading_withheld_marker_variants():
    assert cleaner.strip_leading_withheld_marker("w.h. 1 Example Street") == ("1 Example Street", True)
    assert cleaner.strip_leading_withheld_marker("w/h - 1 Example Street") == ("1 Example Street", True)
    assert cleaner.strip_leading_withheld_marker("withhold email: jane@example.test") == ("jane@example.test", True)
    assert cleaner.strip_leading_withheld_marker("Withheld by C8") == ("", True)
    assert cleaner.strip_leading_withheld_marker("Whitehall Road") == ("Whitehall Road", False)


def test_strip_leading_withheld_marker_does_not_corrupt_real_c8_style_addresses():
    assert cleaner.strip_leading_withheld_marker("C8, 15 Example Road, London") == (
        "C8, 15 Example Road, London",
        False,
    )
    assert cleaner.strip_leading_withheld_marker("Confidential, 12 Example Court, ZZ99 9ZZ") == (
        "Confidential, 12 Example Court, ZZ99 9ZZ",
        False,
    )
    assert cleaner.strip_leading_withheld_marker("C8 address withheld") == ("", True)
    assert cleaner.strip_leading_withheld_marker("C8: withheld") == ("", True)
    assert cleaner.strip_leading_withheld_marker("protected by court order") == ("", True)


def test_clean_contacts_updates_applicant_fields_and_c8_flags(tmp_path: Path, monkeypatch):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    monkeypatch.delenv("CASEFORGE_SQL_DISABLE_LOCAL_SQLITE_DEFAULT", raising=False)

    dry = cleaner.clean_contacts(apply=False)
    assert dry["applied"] is False
    assert dry["party_contact_updates"] == 4
    assert dry["people_contact_updates"] == 2
    assert dry["matter_c8_updates"] == 1
    assert dry["non_applicant_marker_fields"] == 1

    result = cleaner.clean_contacts(apply=True)
    assert result["applied"] is True

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        matter = conn.execute("SELECT has_c8, withheld_fields FROM matters WHERE matter_id = 10").fetchone()
        applicant = conn.execute("SELECT * FROM matter_parties WHERE matter_party_id = 100").fetchone()
        respondent = conn.execute("SELECT * FROM matter_parties WHERE matter_party_id = 101").fetchone()
        person = conn.execute("SELECT * FROM people WHERE person_id = 1").fetchone()

    assert matter["has_c8"] == 1
    assert matter["withheld_fields"] == "Applicant address; Applicant email; Applicant phone"
    assert applicant["address_text"] == "1 Example Street"
    assert applicant["phone_primary"] == "07700 900123"
    assert applicant["phone_digits"] == "07700900123"
    assert applicant["phone_digits_key"] == "07700900123"
    assert applicant["email_primary"] == "jane@example.test"
    assert applicant["email_primary_key"] == "jane@example.test"
    assert respondent["address_text"] == "2 Other Street"
    assert person["phone_primary"] == "07700 900123"
    assert person["phone_digits"] == "07700900123"
    assert person["email_primary"] == "jane@example.test"
