import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from maintenance import client_as_party_scan as scan


def test_a_party_row_holding_nothing_new_is_removable():
    row = (7, 0, 70, "1 A St", "0700", None, None, "1 A St", "0700", "a@b.example", None)
    assert scan.classify(row) == {"matter_id": 7, "party_id": 70, "c8": False, "only_on_party_row": [], "safe_to_remove": True}


def test_a_detail_only_on_the_party_row_is_reported_and_kept():
    row = (8, 1, 80, "9 B Rd", None, "x@y.example", None, None, None, "x@y.example", None)
    out = scan.classify(row)
    assert out["only_on_party_row"] == ["address_text"] and out["safe_to_remove"] is False and out["c8"] is True
