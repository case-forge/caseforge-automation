from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import recipient_identity as ri

CLIENT_A = "Jane Doe"
MATTER_A = "101"
OTHER_ADDRESS = "bob.example@example.org"
OTHER_CLIENT = ri.RecordedOwner(OTHER_ADDRESS, "Bob Example", matter_id="202", person_id="7")


def _check(body, addresses=(OTHER_ADDRESS,), owners=(OTHER_CLIENT,), **kw):
    kw.setdefault("expected_matter_id", MATTER_A)
    return ri.check_client_recipient(
        expected_names=kw.pop("expected_names", [CLIENT_A]),
        addresses=list(addresses),
        body=body,
        owner_lookup=kw.pop("owner_lookup", ri.OwnerLookup(tuple(owners))),
        **kw,
    )


@pytest.mark.parametrize(
    "body",
    [
        "Dear Sir/Madam,<br>An update.",
        "An update on your case.",
        "Our ref 101\n\nDear Jane,\nAn update.",
    ],
    ids=["sir-madam", "no-greeting", "greets-the-expected-client-on-a-later-line"],
)
def test_another_clients_address_needs_confirmation_whatever_the_greeting(body):
    check = _check(body)
    assert check.decision == ri.NEEDS_CONFIRMATION
    assert f"{OTHER_ADDRESS}: this address belongs to a different client on record (matter 202)" in check.reason
    assert "Bob Example" not in check.reason


@pytest.mark.parametrize("body", ["Dear Bob,<br>An update on your case.", "Our ref 101<br><br>Dear Bob,<br>An update."],
                         ids=["greets-the-other-client", "greeting-on-a-later-line"])
def test_greeting_the_other_client_is_refused_not_confirmable(body):
    check = _check(body)
    assert check.decision == ri.REFUSE and "greeting" in check.reason


def test_with_the_matter_known_only_a_record_on_that_matter_is_exempt():
    own_matter = ri.RecordedOwner("jd1990@example.com", "", matter_id=MATTER_A)
    assert not ri.other_client_owners(["jd1990@example.com"], ri.OwnerLookup((own_matter,)), expected_names=[], expected_matter_id=MATTER_A)
    same_name = ri.RecordedOwner("jane.doe@example.com", "DOE, Jane", matter_id="303", person_id="9")
    check = _check("Dear Jane,", addresses=["jane.doe@example.com"], owners=[same_name])
    assert check.decision == ri.NEEDS_CONFIRMATION
    assert "different client on record (matter 303)" in check.reason


@pytest.mark.parametrize("other_name", ["Jan Doe", "J Doe", "Jane Doe", "Janet Doe", "Jane"])
def test_a_similar_name_on_another_matter_never_exempts_an_address_that_carries_the_clients_name(other_name):
    owner = ri.RecordedOwner("jdoe@example.org", other_name, matter_id="999")
    check = _check("Dear Sir/Madam,", addresses=["jdoe@example.org"], owners=[owner])
    assert check.decision == ri.NEEDS_CONFIRMATION


@pytest.mark.parametrize("other_name, exempt", [("DOE, Jane", True), ("Jane Doe", True), ("Jan Doe", False), ("J Doe", False), ("Jane", False)])
def test_with_no_matter_known_only_an_exact_full_name_is_exempt(other_name, exempt):
    owner = ri.RecordedOwner("jdoe@example.org", other_name, matter_id="999")
    found = ri.other_client_owners(["jdoe@example.org"], ri.OwnerLookup((owner,)), expected_names=[CLIENT_A])
    assert (not found) is exempt


def test_a_greeting_never_stands_in_for_the_expected_client_in_the_owner_check():
    owner = ri.RecordedOwner("john.roe@example.org", "John Roe", matter_id="999")
    assert not ri.other_client_owners(["john.roe@example.org"], ri.OwnerLookup((owner,)), expected_names=[])
    check = ri.check_client_recipient(
        expected_names=[], addresses=["john.roe@example.org"], body="Dear John,",
        owner_lookup=ri.OwnerLookup((owner,)), expected_matter_id=MATTER_A,
    )
    assert check.decision == ri.NEEDS_CONFIRMATION


def test_a_record_with_no_name_on_another_matter_counts_as_another_client():
    nameless = ri.RecordedOwner(OTHER_ADDRESS, "", matter_id="202")
    assert _check("Dear Jane,", owners=[nameless]).decision == ri.NEEDS_CONFIRMATION


def test_an_address_on_the_expected_clients_record_and_another_is_the_expected_clients():
    shared = [OTHER_CLIENT, ri.RecordedOwner(OTHER_ADDRESS, CLIENT_A, matter_id=MATTER_A)]
    assert not ri.other_client_owners([OTHER_ADDRESS], ri.OwnerLookup(tuple(shared)), expected_names=[CLIENT_A])


@pytest.mark.parametrize(("address", "body"), [("jane.doe@example.com", "Dear Jane,"), ("bob.smith@example.com", "Dear Jane,")])
def test_an_address_recorded_against_nobody_is_unchanged(address, body):
    before = ri.check_client_recipient(expected_names=[CLIENT_A], addresses=[address], body=body)
    after = _check(body, addresses=[address], owners=[])
    assert (after.decision, after.reason) == (before.decision, before.reason)


def test_a_failed_lookup_needs_confirmation_rather_than_reading_as_nobody():
    check = _check("Dear Jane,", addresses=["jane.doe@example.com"], owner_lookup=ri.OwnerLookup(error="the client database lookup failed: OperationalError"))
    assert check.decision == ri.NEEDS_CONFIRMATION
    assert "could not be checked" in check.reason


def test_with_no_expected_client_there_is_nothing_to_differ_from():
    assert not ri.other_client_owners([OTHER_ADDRESS], ri.OwnerLookup((OTHER_CLIENT,)), expected_names=[])
    failed = ri.check_client_recipient(expected_names=[], addresses=[OTHER_ADDRESS], body="Thanks.", owner_lookup=ri.OwnerLookup(error="x"))
    assert failed.decision == ri.ALLOW_UNKNOWN


def test_a_greeting_to_the_other_client_still_refuses_when_the_expected_clients_address_is_also_there():
    check = _check(
        "Dear Bob,", addresses=["jane.doe@example.com", OTHER_ADDRESS], recorded_addresses=["jane.doe@example.com"]
    )
    assert check.decision == ri.REFUSE and "greeting" in check.reason


def test_a_greeting_to_a_third_person_still_refuses():
    assert _check("Dear Charlie,").decision == ri.REFUSE


def test_the_other_client_address_is_matched_as_a_mailbox():
    owner = ri.RecordedOwner("bob.example@gmail.com", "Bob Example", matter_id="202")
    assert _check("Dear Jane,", addresses=["BobExample+tag@googlemail.com"], owners=[owner]).decision == ri.NEEDS_CONFIRMATION


def test_the_owner_can_flip_the_decision_to_refuse(monkeypatch):
    monkeypatch.setattr(ri, "OTHER_CLIENT_ADDRESS_DECISION", ri.REFUSE)
    check = _check("Dear Sir/Madam,")
    assert check.decision == ri.REFUSE
    assert "belongs to a different client on record" in check.reason


def test_owner_lookup_from_rows_skips_blank_emails():
    lookup = ri.OwnerLookup.from_rows(
        [
            {"email": " Bob.Example@Example.org ", "owner_name": "Bob Example", "matter_id": 202, "person_id": 7},
            {"email": None, "owner_name": "No Email", "matter_id": 203, "person_id": 8},
        ]
    )
    assert lookup.owners == (ri.RecordedOwner(OTHER_ADDRESS, "Bob Example", "202", "7"),)




def _load_clientdb_sql(monkeypatch, db_path: Path):
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(db_path))
    import clientdb_sql

    return importlib.reload(clientdb_sql)


def _make_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE people (person_id INTEGER PRIMARY KEY, canonical_name TEXT, email_primary TEXT);
            CREATE TABLE matters (matter_id INTEGER PRIMARY KEY, primary_person_id INTEGER, client_role TEXT);
            CREATE TABLE matter_parties (
                matter_party_id INTEGER PRIMARY KEY, matter_id INTEGER, role TEXT,
                display_name TEXT, email_primary TEXT
            );
            INSERT INTO people VALUES (1, 'Jane Doe', 'jane.doe@example.com');
            INSERT INTO people VALUES (2, 'Bob Example', ' Bob.Example@Example.org ');
            INSERT INTO people VALUES (3, 'Gail Mosstest', 'gail.mailbox@gmail.com');
            INSERT INTO people VALUES (4, 'Rhoda Respondent-Client', NULL);
            INSERT INTO matters VALUES (101, 1, 'Applicant');
            INSERT INTO matters VALUES (202, 2, '');
            INSERT INTO matters VALUES (303, 3, 'applicant');
            INSERT INTO matters VALUES (404, 4, 'Respondent');
            INSERT INTO matter_parties VALUES (1, 101, 'Respondent', 'Other Side', 'other.side@example.net');
            INSERT INTO matter_parties VALUES (2, 202, 'Applicant', 'Bob Example', 'robert.alt@example.org');
            INSERT INTO matter_parties VALUES (3, 404, 'Respondent', 'Rhoda Respondent-Client', 'rhoda@example.net');
            INSERT INTO matter_parties VALUES (4, 404, 'Applicant', 'Their Opponent', 'opponent@example.net');
            """
        )


def test_find_client_email_records_matches_people_and_the_clients_own_party_rows(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    clientdb_sql = _load_clientdb_sql(monkeypatch, db)

    rows = clientdb_sql.find_client_email_records(["BOB.EXAMPLE@example.org"])
    assert [(str(r["matter_id"]), str(r["person_id"]), r["owner_name"]) for r in rows] == [("202", "2", "Bob Example")]

    alt = clientdb_sql.find_client_email_records(["robert.alt@example.org"])
    assert [(str(r["matter_id"]), str(r["person_id"])) for r in alt] == [("202", "2")]

    gmail = clientdb_sql.find_client_email_records(["GailMailbox+x@googlemail.com"])
    assert [str(r["matter_id"]) for r in gmail] == ["303"]

    respondent_client = clientdb_sql.find_client_email_records(["rhoda@example.net"])
    assert [str(r["matter_id"]) for r in respondent_client] == ["404"]


def test_find_client_email_records_ignores_the_other_side(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    clientdb_sql = _load_clientdb_sql(monkeypatch, db)
    assert clientdb_sql.find_client_email_records(["other.side@example.net", "opponent@example.net", "nobody@example.com"]) == []
    assert clientdb_sql.find_client_email_records(["", "not-an-address"]) == []


def test_client_email_owner_lookup_reports_a_failed_lookup(monkeypatch, tmp_path):
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()
    clientdb_sql = _load_clientdb_sql(monkeypatch, db)
    lookup = clientdb_sql.client_email_owner_lookup([OTHER_ADDRESS])
    assert lookup.owners == () and lookup.error.startswith("the client database lookup failed")


def test_client_email_owner_lookup_feeds_the_check(monkeypatch, tmp_path):
    db = tmp_path / "clientdb.sqlite"
    _make_db(db)
    clientdb_sql = _load_clientdb_sql(monkeypatch, db)
    check = _check("Dear Sir/Madam,", owner_lookup=clientdb_sql.client_email_owner_lookup([OTHER_ADDRESS]))
    assert check.decision == ri.NEEDS_CONFIRMATION and "matter 202" in check.reason
    own = _check("Dear Jane,", addresses=["jane.doe@example.com"], owner_lookup=clientdb_sql.client_email_owner_lookup(["jane.doe@example.com"]))
    assert own.decision == ri.ALLOW
