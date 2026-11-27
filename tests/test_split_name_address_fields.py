from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from sql import split_name_address_fields as norm

PEOPLE = norm.TABLES["people"]
PARTIES = norm.TABLES["matter_parties"]
CHILDREN = norm.TABLES["matter_children"]


def _party(**over) -> dict:
    row = {c: None for c in norm._columns(PARTIES)}
    row["matter_party_id"] = 1
    row.update(over)
    return row




@pytest.mark.parametrize(
    "name, expected",
    [
        ("Amy Ashtest", ("Amy", "", "Ashtest")),
        ("Amy Jane Ashtest", ("Amy", "Jane", "Ashtest")),
        ("Jan van der Berg", ("Jan", "", "van der Berg")),
        ("Mary-Ann de Souza", ("Mary-Ann", "", "de Souza")),
        ("Sam O'Nettletest", ("Sam", "", "O'Nettletest")),
        ("Ali bin Hassan", ("Ali", "", "bin Hassan")),
        ("Amy Jane Van Brooktest", ("Amy", "Jane", "Van Brooktest")),
    ],
)
def test_names_split_with_particles_kept_on_the_surname(name, expected):
    assert norm.classify_name(name) == expected


@pytest.mark.parametrize(
    "name",
    ["Cher", "Al Radishtest", "AMY ASHTEST", "Ashtest, Amy", "Amy Ashtest (aka Reedtest)", "One Two Three Four Five", ""],
)
def test_ambiguous_names_are_refused_not_guessed(name):
    assert norm.classify_name(name) is None




@pytest.mark.parametrize(
    "text, expected",
    [
        ("1 High St, London, ZZ99 9ZZ, UK", "1 High St, London, ZZ99 9ZZ"),
        ("1 High St, London ZZ99 9ZZ U.K.", "1 High St, London ZZ99 9ZZ"),
        ("1 High St, United Kingdom", "1 High St"),
        ("1 High St, London, UK,", "1 High St, London"),
        ("1 High St, UK, UK", "1 High St"),
        ("UK", ""),
        ("1 High St, London", "1 High St, London"),
        ("Flat 3, UK House, ZZ99 1ZZ", "Flat 3, UK House, ZZ99 1ZZ"),
        ("12 Duke Road, Bucks", "12 Duke Road, Bucks"),
    ],
)
def test_strip_uk_suffix_only_removes_a_trailing_country_label(text, expected):
    assert norm.strip_uk_suffix(text) == expected


def test_clean_address_lines_drops_a_uk_line_and_moves_the_rest_up():
    assert norm.clean_address_lines(["1 High St", "London", "UK", ""]) == ["1 High St", "London"]
    assert norm.clean_address_lines(["1 High St", "London, UK", "", ""]) == ["1 High St", "London"]


def test_clean_address_lines_refuses_a_label_in_the_middle_of_a_line():
    assert norm.clean_address_lines(["UK House", "London", "", ""]) is None




def test_uk_only_row_changes_the_text_and_nothing_else():
    row = _party(
        display_name="Amy Ashtest", name_first="Amy", name_last="Ashtest",
        address_text="1 High St, London, ZZ99 9ZZ, UK",
        address_line1="1 High St", address_line2="London", address_postcode="ZZ99 9ZZ",
    )
    updates, findings, rules = norm.plan_row(PARTIES, row)
    assert updates == {"address_text": "1 High St, London, ZZ99 9ZZ"}
    assert findings == []
    assert rules == ["uk_text"]


def test_row_with_text_but_no_lines_is_stripped_then_split():
    row = _party(display_name="Amy Ashtest", name_first="Amy", name_last="Ashtest",
                 address_text="1 High St, Anytown, AB1 2CD, UK")
    updates, _findings, rules = norm.plan_row(PARTIES, row)
    assert updates["address_text"] == "1 High St, Anytown, AB1 2CD"
    assert updates["address_line1"] == "1 High St"
    assert updates["address_line2"] == "Anytown"
    assert updates["address_postcode"] == "AB1 2CD"
    assert rules == ["uk_text", "addr_split"]
    assert "UK" not in " ".join(str(v) for v in updates.values())


def test_uk_line_in_the_structured_columns_is_cleared():
    row = _party(display_name="Amy Ashtest", name_first="Amy", name_last="Ashtest",
                 address_line1="1 High St", address_line2="London", address_line3="UK",
                 address_postcode="ZZ99 9ZZ")
    updates, _f, rules = norm.plan_row(PARTIES, row)
    assert updates == {"address_line1": "1 High St", "address_line2": "London",
                       "address_line3": "", "address_line4": ""}
    assert rules == ["uk_lines"]


def test_a_uk_label_mid_line_is_reported_not_edited():
    row = _party(display_name="Amy Ashtest", name_first="Amy", name_last="Ashtest",
                 address_line1="UK House", address_line2="London")
    updates, findings, _r = norm.plan_row(PARTIES, row)
    assert updates == {}
    assert findings == [("address_lines", "uk_mid_line")]


def test_an_address_that_is_only_the_label_is_reported():
    row = _party(display_name="Amy Ashtest", name_first="Amy", name_last="Ashtest", address_text="UK")
    updates, findings, _r = norm.plan_row(PARTIES, row)
    assert updates == {}
    assert ("address", "uk_only") in findings


def test_two_postcodes_are_ambiguous_and_left_alone():
    row = _party(display_name="Amy Ashtest", name_first="Amy", name_last="Ashtest",
                 address_text="1 High St, AB1 2CD or 2 Low Rd, EF3 4GH")
    updates, findings, _r = norm.plan_row(PARTIES, row)
    assert updates == {}
    assert findings == [("address", "ambiguous")]


def test_a_row_that_already_has_name_parts_keeps_them():
    row = _party(display_name="Amy Jane Ashtest", name_first="Amy", name_middle="", name_last="Jane Ashtest")
    updates, _f, rules = norm.plan_row(PARTIES, row)
    assert updates == {} and rules == []


def test_a_row_with_only_an_empty_string_name_first_is_still_split():
    row = _party(display_name="Amy Ashtest", name_first="", name_last="")
    updates, _f, rules = norm.plan_row(PARTIES, row)
    assert (updates["name_first"], updates["name_last"]) == ("Amy", "Ashtest")
    assert rules == ["name_split"]


def test_children_have_no_address_handling():
    row = {c: None for c in norm._columns(CHILDREN)}
    row.update(child_id=7, child_name="Sam Reedtest")
    updates, _f, _r = norm.plan_row(CHILDREN, row)
    assert updates == {"name_first": "Sam", "name_middle": "", "name_last": "Reedtest"}


def test_planning_is_idempotent():
    row = _party(display_name="Jan van der Berg", address_text="1 High St, Anytown, AB1 2CD, UK")
    updates, _f, _r = norm.plan_row(PARTIES, row)
    row.update(updates)
    assert norm.plan_row(PARTIES, row) == ({}, [], [])


def test_c8_columns_are_never_selected_or_written():
    for cfg in norm.TABLES.values():
        assert not any("c8" in c or "withheld" in c for c in norm._columns(cfg))
    assert "canonical_name" not in norm.NAME_PART_COLS + norm.ADDRESS_COLS




class FakeCursor:
    def __init__(self, script=None):
        self.executed: list[tuple[str, tuple]] = []
        self.script = list(script or [])

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), tuple(params) if params else ()))

    def fetchall(self):
        return self.script.pop(0)

    def fetchone(self):
        return self.script.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, cursor_factory=None):
        return self._cursor


def test_every_changed_column_is_logged_with_old_and_new_before_the_update():
    cur = FakeCursor()
    row = _party(display_name="Amy Ashtest", address_text="1 High St, AB1 2CD, UK")
    updates = {"address_text": "1 High St, AB1 2CD"}

    norm._log_and_update(FakeConn(cur), "matter_parties", PARTIES, row, updates, "run-1")

    (log_sql, log_params), (upd_sql, upd_params) = cur.executed
    assert log_sql.startswith("INSERT INTO clientdb_normalise_log")
    assert log_params == ("run-1", "matter_parties", "matter_party_id", "1",
                          "address_text", "1 High St, AB1 2CD, UK", "1 High St, AB1 2CD")
    assert upd_sql == "UPDATE matter_parties SET address_text = %s WHERE matter_party_id = %s"
    assert upd_params == ("1 High St, AB1 2CD", 1)


def _entry(**over):
    e = {"log_id": 10, "table_name": "matter_parties", "pk_column": "matter_party_id", "pk_value": "1",
         "column_name": "address_text", "old_value": "1 High St, UK", "new_value": "1 High St"}
    e.update(over)
    return e


def test_revert_restores_a_column_that_still_holds_what_the_run_wrote():
    cur = FakeCursor([[_entry()], {"v": "1 High St"}])
    result = norm.revert_run(FakeConn(cur), "run-1", apply=True)
    assert (result["restored"], result["changed_since"]) == (1, 0)
    sqls = [s for s, _ in cur.executed]
    assert "UPDATE matter_parties SET address_text = %s WHERE matter_party_id::text = %s" in sqls
    assert any(s.startswith("UPDATE clientdb_normalise_log SET reverted_utc") for s in sqls)
    restore = next(p for s, p in cur.executed if s.startswith("UPDATE matter_parties"))
    assert restore == ("1 High St, UK", "1")


def test_revert_leaves_a_column_someone_edited_since():
    cur = FakeCursor([[_entry()], {"v": "9 Other Road"}])
    result = norm.revert_run(FakeConn(cur), "run-1", apply=True)
    assert (result["restored"], result["changed_since"]) == (0, 1)
    assert not any(s.startswith("UPDATE") for s, _ in cur.executed)


def test_revert_dry_run_counts_but_writes_nothing():
    cur = FakeCursor([[_entry()], {"v": "1 High St"}])
    result = norm.revert_run(FakeConn(cur), "run-1", apply=False)
    assert result["restored"] == 1
    assert not any(s.startswith("UPDATE") for s, _ in cur.executed)


@pytest.mark.parametrize(
    "bad",
    [{"table_name": "matters"}, {"column_name": "c8_address"}, {"pk_column": "1=1; --"}],
)
def test_revert_refuses_a_log_row_pointing_outside_the_normalised_columns(bad):
    cur = FakeCursor([[_entry(**bad)]])
    with pytest.raises(ValueError):
        norm.revert_run(FakeConn(cur), "run-1", apply=True)


def test_the_log_migration_defines_the_table_the_code_writes():
    sql = norm.LOG_MIGRATION.read_text(encoding="utf-8")
    for col in ("run_tag", "table_name", "pk_column", "pk_value", "column_name",
                "old_value", "new_value", "reverted_utc"):
        assert col in sql


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1 Example Road, Testville, UK AB1 2CD", "1 Example Road, Testville, AB1 2CD"),
        ("1 Example Road, Testville UK AB1 2CD", "1 Example Road, Testville, AB1 2CD"),
        ("1 Example Road, Testville, United Kingdom AB1 2CD", "1 Example Road, Testville, AB1 2CD"),
        ("1 Example Road, Testville, AB1 2CD, UK", "1 Example Road, Testville, AB1 2CD"),
        ("Flat 3, UK House, AB1 2CD", "Flat 3, UK House, AB1 2CD"),
        ("1 Example Road, Testville, AB1 2CD", "1 Example Road, Testville, AB1 2CD"),
    ],
)
def test_strip_uk_label_handles_a_label_before_the_postcode(text, expected):
    assert norm.strip_uk_label(text) == expected


def test_plan_row_strips_a_label_before_the_postcode_and_splits_the_address():
    cfg = norm.TABLES["matter_parties"]
    row = {"display_name": "Sam Example", "address_text": "1 Example Road, Testville, UK AB1 2CD"}
    updates, findings, rules = norm.plan_row(cfg, row)
    assert updates["address_text"] == "1 Example Road, Testville, AB1 2CD"
    assert updates["address_postcode"] == "AB1 2CD"
    assert "UK" not in " ".join(str(v) for k, v in updates.items() if k.startswith("address_line"))
    assert "uk_text" in rules and "addr_split" in rules
    assert findings == []



def test_the_production_address_split_is_lossless_and_joins_a_house_number_to_its_street():
    from sql.split_name_address_fields import classify_address

    got = classify_address("113, Test Road, Testville, Leeds TE1 1ST")
    assert (got["address_line1"], got["address_line2"], got["address_line3"], got["address_postcode"]) == ("113 Test Road", "Testville", "Leeds", "TE1 1ST")
    many = classify_address("The Old Mill, 5 Test Lane, Testville, Wakefield, Leeds, West Yorkshire TE1 1ST")
    assert many["address_line4"] == "Wakefield, Leeds, West Yorkshire"
    assert "Mill" in many["address_line1"] and many["address_line3"] == "Testville"
