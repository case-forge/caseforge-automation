import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "agwu"))
import duplicate_check as dc


def rec(mid, name, email=None, phone=None):
    return {"matter_id": mid, "name": name, "email": email, "phone": phone}


def test_a_shorter_name_inside_a_longer_one_is_flagged_ignoring_the_role_suffix():
    a = rec("304", "Ada Grace Oattest (R)")
    b = rec("305", "Ada Oattest")
    assert dc.why_duplicate(a, b) == "one name contains the other"


def test_a_lone_shared_surname_is_not_a_duplicate():
    assert dc.why_duplicate(rec("1", "Ada Oattest"), rec("2", "Oattest")) is None
    assert dc.why_duplicate(rec("1", "Ada Oattest"), rec("2", "Tunde Oattest")) is None


def test_same_email_or_phone_flags_different_names_but_placeholders_do_not():
    assert dc.why_duplicate(rec("1", "A Bee", email="x@y.example"), rec("2", "C Dee", email="X@y.example")) == "same email"
    assert dc.why_duplicate(rec("1", "A Bee", phone="07700 900123"), rec("2", "C Dee", phone="+447700900123")) == "same phone"
    ph = "[unknown - check correspondence]"
    assert dc.why_duplicate(rec("1", "A Bee", email=ph), rec("2", "C Dee", email=ph)) is None


def test_a_record_is_never_its_own_duplicate():
    a = rec("304", "Ada Oattest")
    assert dc.possible_duplicates(a, [a, rec("9", "Someone Else")]) == []


def test_flagging_puts_the_record_on_the_to_check_list_naming_the_other_matter(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from vergil import client_edits

    calls = []
    monkeypatch.setattr(client_edits, "flag_field_for_review", lambda **kw: calls.append(kw))
    dc.flag_for_check(rec("304", "Ada Grace Oattest"), rec("305", "Ada Oattest"), "one name contains the other")
    assert len(calls) == 1
    call = calls[0]
    assert call["matter_id"] == "304"
    assert call["field_name"] == "possible_duplicate"
    assert "305" in call["value_snapshot"]
    assert call["flagged_by"]


def test_pairs_lists_each_pair_once_with_its_reason():
    rows = [rec("1", "Ada Oattest"), rec("2", "Ada Oattest"), rec("3", "Tunde Other", email="t@o.example"), rec("4", "Bola Else", email="T@o.example")]
    found = dc.pairs(rows)
    assert [(p["a"]["matter_id"], p["b"]["matter_id"], p["reason"]) for p in found] == [("1", "2", "same name"), ("3", "4", "same email")]
    assert dc.pairs([rec("1", "Ada Oattest")]) == []
