from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from documents import summary_conveyor as sc




def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE matters (
            matter_id INTEGER PRIMARY KEY,
            primary_person_id INTEGER,
            client_role TEXT,
            company_reference TEXT,
            has_c8 INTEGER,
            order_requested_text TEXT,
            children_summary TEXT,
            live_matter_folder TEXT,
            legal_aid_tracker_status TEXT,
            partner_status TEXT,
            relationship_start TEXT,
            relationship_end TEXT,
            referral_sent_at TEXT,
            source_email_sent_at TEXT
        );
        CREATE TABLE people (
            person_id INTEGER PRIMARY KEY,
            canonical_name TEXT,
            dob_iso TEXT,
            phone_primary TEXT,
            email_primary TEXT
        );
        CREATE TABLE matter_parties (
            matter_id INTEGER,
            role TEXT,
            display_name TEXT,
            dob_iso TEXT,
            address_text TEXT,
            phone_primary TEXT,
            phone_digits TEXT,
            email_primary TEXT
        );
        CREATE TABLE matter_references (
            reference_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            ref_type TEXT NOT NULL,
            ref_value TEXT NOT NULL,
            ref_value_normalised TEXT NOT NULL,
            source TEXT NOT NULL,
            notes TEXT,
            is_primary INTEGER NOT NULL DEFAULT 0,
            created_utc TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        );
        CREATE TABLE matter_order_types (
            matter_id INTEGER,
            order_type_code TEXT
        );
        CREATE TABLE matter_children (
            matter_id INTEGER,
            child_name TEXT,
            dob_iso TEXT,
            gender TEXT,
            parental_responsibility TEXT,
            notes TEXT
        );
        CREATE TABLE matter_live_status (
            matter_id INTEGER,
            latest_live_status TEXT,
            order_status TEXT,
            sealed_order_status TEXT,
            service_status TEXT,
            next_hearing_text TEXT,
            awaiting_next_step TEXT,
            last_client_chase TEXT,
            last_material_email_received TEXT,
            last_material_email_subject TEXT,
            draft_order_status TEXT
        );
        CREATE TABLE matter_bank_details (
            matter_id INTEGER,
            account_name TEXT,
            account_number TEXT,
            sort_code TEXT,
            amount TEXT,
            notes TEXT
        );
        CREATE TABLE matter_incidents (
            matter_id INTEGER,
            incident_date TEXT,
            incident_type TEXT,
            summary TEXT,
            police_called INTEGER,
            crime_reference TEXT,
            arrest_status TEXT,
            bail_status TEXT,
            confidence TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def _insert_matter(conn: sqlite3.Connection, **fields) -> None:
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    conn.execute(f"INSERT INTO matters ({cols}) VALUES ({placeholders})", tuple(fields.values()))


def test_children_summary_shows_the_live_age_not_a_stored_one(monkeypatch, tmp_path):
    import datetime as dt

    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))

    conn = sqlite3.connect(db)
    _insert_matter(conn, matter_id=1, children_summary="Ivy Reedtest (2020-03-04, age 1)")
    conn.commit()
    conn.close()

    today = dt.date.today()
    expected = today.year - 2020 - ((today.month, today.day) < (3, 4))
    assert sc.facts("1")["children_summary"] == f"Ivy Reedtest (2020-03-04, age {expected})"




def test_facts_tbc_on_missing_fields(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))

    conn = sqlite3.connect(db)
    _insert_matter(conn, matter_id=1)
    conn.commit()
    conn.close()

    f = sc.facts("1")
    assert f["client_name"] == "TBC"
    assert f["client_role"] == "TBC"
    assert f["company_reference"] == "TBC"
    assert f["order_requested_text"] == "TBC"
    assert f["children_summary"] == "TBC"
    assert f["court"] == "TBC"
    assert f["has_c8"] is False
    assert f["parties"] == []
    assert f["children"] == []
    assert f["bank_details"] == []
    assert f["order_type_codes"] == []
    assert f["references"] == []
    assert f["live_status"]["latest_live_status"] == "TBC"
    assert f["live_status"]["next_hearing_text"] == "TBC"


def test_facts_requires_matter_id():
    import pytest

    with pytest.raises(ValueError):
        sc.facts("")




def _c8_matter_with_parties(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO people (person_id, canonical_name, dob_iso, phone_primary, email_primary) "
        "VALUES (1, 'Jane Example', '1990-01-02', '07700900001', 'jane@example.test')"
    )
    _insert_matter(
        conn,
        matter_id=1,
        primary_person_id=1,
        client_role="Applicant",
        has_c8=1,
    )
    conn.execute(
        "INSERT INTO matter_parties (matter_id, role, display_name, dob_iso, address_text, "
        "phone_primary, phone_digits, email_primary) VALUES "
        "(1, 'Applicant', 'Jane Example', '1990-01-02', '1 Secret St', '07700900001', "
        "'07700900001', 'jane@example.test')"
    )
    conn.execute(
        "INSERT INTO matter_parties (matter_id, role, display_name, dob_iso, address_text, "
        "phone_primary, phone_digits, email_primary) VALUES "
        "(1, 'Respondent', 'John Example', '1988-05-05', '2 Open Rd', '07700900002', "
        "'07700900002', 'john@example.test')"
    )
    conn.commit()


def test_facts_returns_real_c8_values_unredacted(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    conn = sqlite3.connect(db)
    _c8_matter_with_parties(conn)
    conn.close()

    f = sc.facts("1")
    assert f["has_c8"] is True
    assert f["client_phone"] == "07700900001"
    assert f["client_email"] == "jane@example.test"
    applicant = next(p for p in f["parties"] if p["role"] == "Applicant")
    assert applicant["address_text"] == "1 Secret St"


def test_internal_and_barrister_renderers_show_the_real_c8_address(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    conn = sqlite3.connect(db)
    _c8_matter_with_parties(conn)
    conn.close()

    f = sc.facts("1")
    for render in (sc.render_snapshot, sc.render_brief):
        text = render(f)
        assert "C8 PROTECTED MATTER" in text
        assert sc.C8_WITHHELD not in text
    assert "1 Secret St" in sc.render_snapshot(f)


def test_court_facing_renderers_still_redact_the_c8_address(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    conn = sqlite3.connect(db)
    _c8_matter_with_parties(conn)
    conn.close()

    f = sc.facts("1")
    raw_secrets = ("1 Secret St", "07700900001", "jane@example.test")
    for render in (sc.render_chronology, sc.render_bundle_summary):
        text = render(f)
        assert "C8 PROTECTED MATTER" in text
        for secret in raw_secrets:
            assert secret not in text

    text = sc.render_bundle_summary(f)
    assert "2 Open Rd" in text and "John Example" in text


def test_mutation_skipping_the_redaction_call_would_leak(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    conn = sqlite3.connect(db)
    _c8_matter_with_parties(conn)
    conn.close()

    f = sc.facts("1")
    unmutated = sc._parties_block(sc._redact_for_disclosure(f))
    mutated = sc._parties_block(f)
    assert "1 Secret St" not in unmutated, "the real, unmutated call path must redact"
    assert "1 Secret St" in mutated, (
        "sanity: the mutated (unredacted) call path must leak, or this test "
        "proves nothing about the redaction call actually mattering"
    )


def test_no_c8_banner_and_no_redaction_when_flag_unset(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))

    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO people (person_id, canonical_name, phone_primary, email_primary) "
        "VALUES (1, 'Jane Example', '07700900001', 'jane@example.test')"
    )
    _insert_matter(conn, matter_id=1, primary_person_id=1, client_role="Applicant", has_c8=0)
    conn.commit()
    conn.close()

    f = sc.facts("1")
    assert f["has_c8"] is False
    assert f["client_phone"] == "07700900001"
    assert f["client_email"] == "jane@example.test"
    assert "C8 PROTECTED MATTER" not in sc.render_snapshot(f)
    assert "C8 PROTECTED MATTER" not in sc.render_bundle_summary(f)




def _fully_populated_matter(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO people (person_id, canonical_name, dob_iso, phone_primary, email_primary) "
        "VALUES (1, 'Jane Example', '1990-01-02', '07700900001', 'jane@example.test')"
    )
    _insert_matter(
        conn,
        matter_id=1,
        primary_person_id=1,
        client_role="Applicant",
        company_reference="260101/01FL",
        has_c8=0,
        order_requested_text="Non-Molestation Order",
        children_summary="A Child (2020)",
        legal_aid_tracker_status="granted",
        partner_status="submitted",
        referral_sent_at="2026-05-18",
        source_email_sent_at="2026-05-18T09:30:03Z",
    )
    conn.execute(
        "INSERT INTO matter_parties (matter_id, role, display_name, dob_iso, address_text, "
        "phone_primary, phone_digits, email_primary) VALUES "
        "(1, 'Respondent', 'John Example', '1988-05-05', '2 Open Rd', '07700900002', "
        "'07700900002', 'john@example.test')"
    )
    conn.execute("INSERT INTO matter_order_types (matter_id, order_type_code) VALUES (1, 'nmo')")
    conn.execute(
        "INSERT INTO matter_children (matter_id, child_name, dob_iso, gender, "
        "parental_responsibility, notes) VALUES (1, 'A Child', '2020-03-01', 'female', "
        "'Client has PR', '')"
    )
    conn.execute(
        "INSERT INTO matter_live_status (matter_id, latest_live_status, order_status, "
        "sealed_order_status, service_status, next_hearing_text, awaiting_next_step, "
        "last_client_chase, last_material_email_received, last_material_email_subject, "
        "draft_order_status) VALUES (1, 'Awaiting hearing', 'made', 'awaited', 'outstanding', "
        "'2026-09-01 10:00 West London', 'Chase sealed order', '2026-08-01', "
        "'2026-08-02T09:00:00Z', 'Re: hearing bundle', 'sent')"
    )
    conn.execute(
        "INSERT INTO matter_bank_details (matter_id, account_name, account_number, sort_code, "
        "amount, notes) VALUES (1, 'Jane Example', '12345678', '11-22-33', '500', '')"
    )
    conn.execute(
        "INSERT INTO matter_incidents (matter_id, incident_date, incident_type, summary, "
        "police_called, crime_reference, arrest_status, bail_status, confidence) VALUES "
        "(1, '2026-08-01', 'pushed her against the wall', 'Physical altercation.', 1, "
        "'44269990001', 'no arrest made', '', 'high')"
    )


def test_every_renderer_section_renders_on_full_matter(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    conn = sqlite3.connect(db)
    _fully_populated_matter(conn)
    conn.commit()
    conn.close()

    f = sc.facts("1")

    snapshot = sc.render_snapshot(f)
    assert "## Parties" in snapshot
    assert "## Source map" in snapshot
    assert "John Example" in snapshot

    chronology = sc.render_chronology(f)
    assert "| Date | Event | Outcome | Source |" in chronology
    assert "Thin is correct" in chronology

    brief = sc.render_brief(f)
    for heading in ("## Posture", "## Hearing", "## Client and representation", "## Order sought", "## Compressed facts", "### Children and safeguarding", "## What counsel is asked to cover"):
        assert heading in brief
    assert "matter_abuse_themes is declined" in brief
    assert "2026-08-01: pushed her against the wall (ref 44269990001)" in brief
    assert "ref 44269990001; no arrest made" in brief

    bundle = sc.render_bundle_summary(f)
    for heading in ("## Case Header", "## Applications and Orders", "## Parties", "## Children", "## Current Procedural Position", "## Hearing Purpose", "## Factual Summary"):
        assert heading in bundle


def test_every_renderer_section_renders_on_near_empty_matter(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    conn = sqlite3.connect(db)
    _insert_matter(conn, matter_id=2)
    conn.commit()
    conn.close()

    f = sc.facts("2")
    for name, render in sc.RENDERERS.items():
        text = render(f)
        assert "TBC" in text, name
        assert text.strip(), name




def test_chronology_entries_are_ascending(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    conn = sqlite3.connect(db)
    _insert_matter(conn, matter_id=1, referral_sent_at="2026-01-01")
    conn.execute(
        "INSERT INTO matter_live_status (matter_id, last_client_chase, "
        "last_material_email_received) VALUES (1, '2026-06-01', '2026-03-15T00:00:00Z')"
    )
    conn.commit()
    conn.close()

    f = sc.facts("1")
    entries = sc.chronology_entries(f)
    dates = [e["sort_date"] for e in entries]
    assert dates == sorted(dates)
    assert len(entries) == 3
    assert entries[0]["event"] == "Referral received"
    assert entries[-1]["event"] == "Last client chase"

    rendered = sc.render_chronology(f)
    idx = [rendered.index(e["date"]) for e in entries]
    assert idx == sorted(idx)


def test_chronology_reports_no_dates_recorded_when_empty(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    conn = sqlite3.connect(db)
    _insert_matter(conn, matter_id=1)
    conn.commit()
    conn.close()

    f = sc.facts("1")
    assert sc.chronology_entries(f) == []
    assert "No dated SQL facts recorded yet" in sc.render_chronology(f)




def test_parse_dated_recognises_iso_and_month_year_only():
    assert sc._parse_dated("2026-05-18")[1] == "2026-05-18"
    assert sc._parse_dated("2026-05-18T09:30:03Z")[1] == "2026-05-18T09:30:03Z"
    parsed = sc._parse_dated("March 2020")
    assert parsed is not None and parsed[0].year == 2020 and parsed[0].month == 3
    assert sc._parse_dated("TBC") is None
    assert sc._parse_dated("") is None
    assert sc._parse_dated("sometime last year") is None




def test_closing_exists_but_is_not_registered_anywhere(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    conn = sqlite3.connect(db)
    _insert_matter(conn, matter_id=1)
    conn.commit()
    conn.close()

    f = sc.facts("1")
    text = sc.closing(f)
    assert "DRAFT ONLY" in text
    assert "closure policy not settled" in text

    assert "closing" not in sc.RENDERERS
    assert sc.closing not in sc.RENDERERS.values()

    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("variant", choices=sorted(sc.RENDERERS.keys()))
    try:
        ap.parse_args(["closing"])
        raised = False
    except SystemExit:
        raised = True
    assert raised, "the CLI must not accept 'closing' as a variant"




def test_latest_incident_line_tbc_when_no_dated_incidents():
    assert sc._latest_incident_line({"incidents": []}) == "TBC — no dated matter_incidents rows recorded"
    undated = [{"incident_date": "TBC", "incident_type": "TBC", "crime_reference": "TBC"}]
    assert sc._latest_incident_line({"incidents": undated}) == "TBC — no dated matter_incidents rows recorded"


def test_latest_incident_line_picks_the_most_recent_by_date():
    incidents = [
        {"incident_date": "2026-01-05", "incident_type": "earlier incident", "crime_reference": "TBC"},
        {"incident_date": "2026-08-01", "incident_type": "later incident", "crime_reference": "TBC"},
    ]
    assert sc._latest_incident_line({"incidents": incidents}) == "2026-08-01: later incident"


def test_police_bail_crime_line_tbc_when_no_incidents():
    assert sc._police_bail_crime_line({"incidents": []}) == "TBC"


def test_police_bail_crime_line_joins_populated_fields_only():
    incidents = [
        {"crime_reference": "REF1", "arrest_status": "TBC", "bail_status": "TBC"},
        {"crime_reference": "TBC", "arrest_status": "TBC", "bail_status": "TBC"},
    ]
    assert sc._police_bail_crime_line({"incidents": incidents}) == "ref REF1"




def test_main_writes_output_file(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db))
    conn = sqlite3.connect(db)
    _insert_matter(conn, matter_id=1, company_reference="260101/01FL")
    conn.commit()
    conn.close()

    out = tmp_path / "snapshot.md"
    rc = sc.main(["snapshot", "--matter-id", "1", "--output", str(out)])
    assert rc == 0
    assert out.exists()
    assert "260101/01FL" in out.read_text(encoding="utf-8")
