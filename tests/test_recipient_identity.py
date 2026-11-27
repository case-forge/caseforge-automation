from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import recipient_identity as ri

CLIENT = "Jane Doe"


@pytest.mark.parametrize(
    "address",
    [
        "jane.doe@example.com",
        "jdoe@example.com",
        "doejane@example.com",
        "janedoe85@example.com",
        "jane_doe@example.com",
        "doe.j@example.com",
        "jane.d@example.com",
        "Jane.Doe+court@example.com",
        "jane.deo@example.com",
    ],
)
def test_common_forms_of_the_name_match(address):
    assert ri.score_address_against_name(address, CLIENT).verdict == ri.MATCH


def test_a_short_form_of_the_given_name_with_the_surname_matches():
    assert ri.score_address_against_name("jen.ashtest@example.com", "Jennifer Ashtest").verdict == ri.MATCH


def test_a_middle_name_counts_as_a_given_name():
    assert ri.score_address_against_name("elspeth.doe@example.com", "Jane Elspeth Doe").verdict == ri.MATCH


@pytest.mark.parametrize("address", ["jane85@example.com", "doe@example.com", "john.doe@example.com"])
def test_half_the_name_is_weak(address):
    assert ri.score_address_against_name(address, CLIENT).verdict == ri.WEAK


@pytest.mark.parametrize("address", ["bob.ashtest@example.com", "sunshine77@example.com"])
def test_someone_elses_address_does_not_match(address):
    assert ri.score_address_against_name(address, CLIENT).verdict == ri.NO_MATCH


@pytest.mark.parametrize("address", ["info@example.com", "admin@example.com", "enquiries@example.com", "x1@example.com"])
def test_role_mailboxes_are_unknown(address):
    assert ri.score_address_against_name(address, CLIENT).verdict == ri.UNKNOWN


def test_no_name_is_unknown():
    assert ri.score_address_against_name("jane.doe@example.com", "").verdict == ri.UNKNOWN


def test_titles_comma_order_and_matter_suffixes_are_read_through():
    assert ri.name_tokens("Mrs Jane Doe (2)") == ["jane", "doe"]
    assert ri.name_tokens("DOE, Jane") == ["jane", "doe"]


@pytest.mark.parametrize(
    ("body", "names"),
    [
        ("Dear Jane,<br>text", ["jane"]),
        ("<p>Dear Ms. Doe,</p>", ["doe"]),
        ("Hi Jane and Bob,\ntext", ["jane", "bob"]),
        ("Dear Sirs,", []),
        ("Dear Sir/Madam,", []),
        ("Dear All,", []),
        ("Dear {{CLIENT_NAME}},", []),
        ("No greeting at all.", []),
    ],
)
def test_salutation_names(body, names):
    assert ri.salutation_names(body)[1] == names


def test_salutation_verdict_against_the_client():
    assert ri.salutation_verdict("Dear Jane,", [CLIENT]) == ri.MATCH
    assert ri.salutation_verdict("Dear Mrs Doe,", [CLIENT]) == ri.MATCH
    assert ri.salutation_verdict("Dear Bob,", [CLIENT]) == ri.NO_MATCH
    assert ri.salutation_verdict("Dear Sirs,", [CLIENT]) == ri.UNKNOWN
    assert ri.salutation_verdict("Dear Jane,", []) == ri.UNKNOWN


def test_names_refer_to_same_person_is_loose_but_not_blind():
    assert ri.names_refer_to_same_person("Jane Doe", "Jane Elspeth Doe")
    assert ri.names_refer_to_same_person("jane doe", "DOE, Jane")
    assert not ri.names_refer_to_same_person("Jane Doe", "Jane Ashtest")
    assert not ri.names_refer_to_same_person("Robert Example", "Jane Doe")


def test_institutional_domains():
    assert ri.is_institutional_address("family@justice.gov.uk")
    assert ri.is_institutional_address("officer@met.police.uk")
    assert ri.is_institutional_address("someone@nhs.net")
    assert not ri.is_institutional_address("jane.doe@gmail.com")




def test_a_matching_address_with_the_clients_greeting_is_allowed():
    check = ri.check_client_recipient(expected_names=[CLIENT], addresses=["jane.doe@example.com"], body="Dear Jane,")
    assert check.decision == ri.ALLOW


def test_a_greeting_naming_someone_else_is_refused_outright():
    check = ri.check_client_recipient(expected_names=[CLIENT], addresses=["bob.ashtest@example.com"], body="Dear Bob,")
    assert check.decision == ri.REFUSE
    check = ri.check_client_recipient(expected_names=[CLIENT], addresses=["jane.doe@example.com"], body="Dear Bob,")
    assert check.decision == ri.REFUSE


def test_an_address_is_not_judged_against_the_clients_own_name():
    for address in ("bob.ashtest@example.com", "john.doe@example.com", "chaz55@example.com", "nikki22@example.com"):
        check = ri.check_client_recipient(expected_names=[CLIENT], addresses=[address], body="Dear Jane,")
        assert check.decision == ri.ALLOW, address


def test_a_role_mailbox_is_allowed_and_says_so():
    check = ri.check_client_recipient(expected_names=[CLIENT], addresses=["info@example.com"], body="Dear Jane,")
    assert check.decision == ri.ALLOW_UNKNOWN


def test_with_no_recorded_name_the_greeting_does_not_doubt_the_address():
    for address in ("jane1990@example.com", "bob.ashtest@example.com"):
        assert ri.check_client_recipient(expected_names=[], addresses=[address], body="Dear Jane,").decision in (ri.ALLOW, ri.ALLOW_UNKNOWN)


def test_nothing_to_compare_is_allowed_unknown():
    check = ri.check_client_recipient(expected_names=[], addresses=["bob.ashtest@example.com"], body="Thanks.")
    assert check.decision == ri.ALLOW_UNKNOWN



RECORDED = "jane.doe@example.com"


@pytest.mark.parametrize(
    "address",
    [
        "jane.dot@example.com",
        "jane.doe@examp1e.com",
        "jane.doe@exarnple.com",
        "jane.doe@example.co",
        "jane.d0e@example.com",
        "janedoe@example.com",
    ],
)
def test_a_typo_or_lookalike_of_the_recorded_address_is_a_near_miss(address):
    assert "address on record" in ri.address_near_miss(address, RECORDED)


@pytest.mark.parametrize("address", [RECORDED, "JANE.DOE@example.com", "bob.ashtest@example.com", "jane.doe@gmail.com"])
def test_the_address_itself_and_genuinely_different_addresses_are_not_near_misses(address):
    assert ri.address_near_miss(address, RECORDED) == ""


@pytest.mark.parametrize("address", ["jane.dot@example.com", "jane.doe@examp1e.com"])
def test_a_near_miss_of_the_recorded_address_is_refused_even_with_the_clients_greeting(address):
    check = ri.check_client_recipient(
        expected_names=[CLIENT], addresses=[address], body="Dear Jane,", recorded_addresses=[RECORDED]
    )
    assert check.decision == ri.REFUSE
    assert "address on record" in check.reason


def test_with_a_recorded_address_name_similarity_no_longer_excuses_a_misspelling():
    assert ri.score_address_against_name("jane.dot@other.example", CLIENT).verdict == ri.MATCH
    assert ri.score_address_against_name("jane.dot@other.example", CLIENT, fuzzy=False).verdict == ri.WEAK
    check = ri.check_client_recipient(
        expected_names=[CLIENT], addresses=["jane.dot@other.example"], body="Dear Jane,", recorded_addresses=[RECORDED]
    )
    assert check.decision == ri.NEEDS_CONFIRMATION


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("janedoe@gmail.com", "jane.doe@gmail.com"),
        ("jane.doe+tag@gmail.com", "jane.doe@gmail.com"),
        ("Jane.Doe@googlemail.com", "janedoe@gmail.com"),
        ("jane.doe+court@example.com", "jane.doe@example.com"),
    ],
)
def test_addresses_are_compared_as_mailboxes(a, b):
    assert ri.same_address(a, b)
    assert ri.address_near_miss(a, b) == ""


def test_dots_only_fold_for_gmail():
    assert ri.canonical_address("Jane.Doe+x@Example.com") == "jane.doe@example.com"
    assert not ri.same_address("janedoe@example.com", "jane.doe@example.com")


@pytest.mark.parametrize(
    ("address", "recorded"),
    [
        ("janedoe@gmail.com", "jane.doe@gmail.com"),
        ("jane.doe+tag@gmail.com", "jane.doe@gmail.com"),
        ("jane.doe@googlemail.com", "jane.doe@gmail.com"),
        ("jane.doe+tag@example.com", "jane.doe@example.com"),
    ],
)
def test_the_recorded_mailbox_under_another_spelling_is_allowed_by_design(address, recorded):
    check = ri.check_client_recipient(expected_names=[CLIENT], addresses=[address], body="Dear Jane,", recorded_addresses=[recorded])
    assert check.decision == ri.ALLOW


def test_a_transposition_counts_as_one_edit():
    assert "address on record" in ri.address_near_miss("jane.doe@exampel.co", RECORDED)
    check = ri.check_client_recipient(
        expected_names=[CLIENT], addresses=["jane.doe@exampel.co"], body="Dear Jane,", recorded_addresses=[RECORDED]
    )
    assert check.decision == ri.REFUSE


def test_the_near_miss_refusal_says_how_to_go_ahead():
    check = ri.check_client_recipient(
        expected_names=[CLIENT], addresses=["jane.dot@example.com"], body="Dear Jane,", recorded_addresses=[RECORDED]
    )
    assert "If this is the client's correct address, update the email on their record first." in check.reason


@pytest.mark.parametrize("address", ["doe.jane@example.com", "jane.doe@gmail.com"])
def test_another_address_for_the_client_needs_confirmation_when_one_is_recorded(address):
    check = ri.check_client_recipient(
        expected_names=[CLIENT], addresses=[address], body="Dear Jane,", recorded_addresses=[RECORDED]
    )
    assert check.decision == ri.NEEDS_CONFIRMATION
    assert "not the address on record" in check.reason


def test_an_address_off_the_record_with_no_name_to_compare_still_needs_confirmation():
    check = ri.check_client_recipient(expected_names=[], addresses=["someone@example.org"], recorded_addresses=[RECORDED])
    assert check.decision == ri.NEEDS_CONFIRMATION


def test_the_recorded_address_itself_is_allowed():
    check = ri.check_client_recipient(
        expected_names=[CLIENT], addresses=[RECORDED], body="Dear Jane,", recorded_addresses=[RECORDED]
    )
    assert check.decision == ri.ALLOW



def _check(address: str, **kw):
    return ri.check_client_recipient(expected_names=["Eleanor Fenner"], addresses=[address], **kw)


@pytest.mark.parametrize("address", ["eleanor@example.test", "eleanor85@example.test", "fenner@example.test", "fenner99@example.test"])
def test_the_clients_first_or_last_name_alone_is_accepted(address):
    assert _check(address).decision == ri.ALLOW


@pytest.mark.parametrize("address", ["eleanor.smith@example.test", "mark.fenner@example.test", "fenner.family@example.test", "sam@example.test"])
def test_another_name_beside_the_clients_is_not_doubted_when_it_is_not_the_respondents(address):
    assert _check(address).decision == ri.ALLOW


def test_the_respondents_first_name_in_the_address_is_doubtful_even_with_the_clients_surname():
    out = _check("mark.fenner@example.test", respondent_names=["Mark Fenner"])
    assert out.decision == ri.NEEDS_CONFIRMATION and "looks like the respondent's" in out.reason
    assert _check("mark85@example.test", respondent_names=["Mark Fenner"]).decision == ri.NEEDS_CONFIRMATION


def test_a_first_name_the_respondent_shares_with_the_client_is_not_counted_against_the_address():
    assert _check("eleanor@example.test", respondent_names=["Eleanor Fenner"]).decision == ri.ALLOW




@pytest.mark.parametrize(
    "address, name",
    [
        ("caaliasample31@example.com", "Chalia Sample"),
        ("chalia.sample@example.com", "Caalia Sample"),
        ("caliasample@example.com", "Caalia Sample"),
        ("jane.deo@example.com", "Jane Doe"),
        ("sample.caalia@example.com", "Chalia Sample"),
        ("c.sample@example.com", "Chalia Sample"),
        ("jane.elizabeth@example.com", "Jane Elizabeth Doe"),
        ("jedoe@example.com", "Jane Elizabeth Doe"),
    ],
)
def test_near_spellings_and_middle_names_match(address, name):
    assert ri.score_address_against_name(address, name).verdict == ri.MATCH


def test_the_near_spelling_case_is_allowed_by_the_full_check():
    check = ri.check_client_recipient(expected_names=["Chalia Sample"], addresses=["caaliasample31@example.com"])
    assert check.decision == ri.ALLOW


@pytest.mark.parametrize(
    "address, name",
    [
        ("june.doe@example.com", "Jane Doe"),
        ("jo.doe@example.com", "Jane Doe"),
        ("sarah.sample@example.com", "Chalia Sample"),
    ],
)
def test_near_spelling_does_not_match_a_different_name(address, name):
    assert ri.score_address_against_name(address, name).verdict != ri.MATCH


def test_a_near_miss_of_the_recorded_address_is_still_refused():
    check = ri.check_client_recipient(
        expected_names=["Jane Doe"], addresses=["jane.dot@example.com"], recorded_addresses=["jane.doe@example.com"]
    )
    assert check.decision == ri.REFUSE



_OK_CASES = [
    ("mark.marlow@example.com", "Mark Marlow"),
    ("mmarlow@example.com", "Mark Marlow"),
    ("marlowmark@example.com", "Mark Marlow"),
    ("marlow1985@example.com", "Mark Marlow"),
    ("mark.james.marlow@example.com", "Mark James Marlow"),
    ("mjmarlow@example.com", "Mark James Marlow"),
    ("james.marlow88@example.com", "Mark James Marlow"),
    ("mark.marlow.uk@example.com", "Mark Marlow"),
    ("officialmarkmarlow@example.com", "Mark Marlow"),
    ("caaliasample31@example.com", "Chalia Sample"),
    ("markmarlw@example.com", "Mark Marlow"),
    ("info@example.com", "Mark Marlow"),
    ("whatever@example.com", ""),
]
_REVIEW_CASES = [
    ("sarah.jones@example.com", "Mark Marlow", "no_name_found"),
    ("bigdaddy99@example.com", "Mark Marlow", "no_name_found"),
    ("marymarlow@example.com", "Mark Marlow", "unexplained_letters"),
    ("sarahmarlow@example.com", "Mark Marlow", "unexplained_letters"),
    ("markmarlowbuilder@example.com", "Mark Marlow", "unexplained_letters"),
    ("xkqzjwvt@example.com", "Mark Marlow", "random_looking"),
    ("qwrtpsdfgh@example.com", "Mark Marlow", "random_looking"),
]


@pytest.mark.parametrize("address, name", _OK_CASES)
def test_oddness_ok(address, name):
    out = ri.email_oddness(address, [name])
    assert out.verdict == ri.OK, out


@pytest.mark.parametrize("address, name, code", _REVIEW_CASES)
def test_oddness_review(address, name, code):
    out = ri.email_oddness(address, [name])
    assert (out.verdict, out.code) == (ri.REVIEW, code)
    assert "gender" not in out.reason.lower() and "woman" not in out.reason.lower() and "man's" not in out.reason.lower()


def test_oddness_accepts_given_middle_and_last_as_separate_names():
    assert ri.email_oddness("james.marlow@example.com", ["Mark", "James", "Marlow"]).verdict == ri.OK


@pytest.mark.parametrize(
    "address",
    ["peter.marlow@example.com", "pmarlow@example.com", "marlowp@example.com", "peterjones@example.com"],
)
def test_oddness_respondent_name(address):
    out = ri.email_oddness(address, ["Mark Marlow"], ["Peter Marlow"] if "jones" not in address else ["Peter Jones"])
    assert (out.verdict, out.code) == (ri.REVIEW, "respondent_name")


def test_oddness_a_name_shared_with_the_respondent_is_not_counted():
    assert ri.email_oddness("mark.marlow@example.com", ["Mark Marlow"], ["Mark Marlow"]).verdict == ri.OK


def test_entropy_is_zero_for_one_letter_and_high_for_many():
    assert ri.shannon_entropy("aaaa") == 0
    assert ri.shannon_entropy("abcdefghij") > 3




def test_a_confirmed_address_reads_as_allow():
    kw = dict(expected_names=["Mark Marlow"], addresses=["dorian.vale@example.com"], respondent_names=["Dorian Vale"])
    assert ri.check_client_recipient(**kw).decision == ri.NEEDS_CONFIRMATION
    assert ri.check_client_recipient(**kw, confirmed_addresses=["Dorian.Vale@example.com"]).decision == ri.ALLOW


def test_a_confirmation_for_another_address_does_not_carry_over():
    check = ri.check_client_recipient(
        expected_names=["Mark Marlow"], addresses=["dorian.vale@example.com"], respondent_names=["Dorian Vale"],
        confirmed_addresses=["bigdaddy99@example.com"],
    )
    assert check.decision == ri.NEEDS_CONFIRMATION



VICTIM = "Chalia Sample"


def _resp(address, *, respondent="Dorian Vale", client=VICTIM, **kw):
    return ri.check_client_recipient(expected_names=[client], addresses=[address], respondent_names=[respondent], **kw)


@pytest.mark.parametrize("address", ["dorian.vale@example.com", "dorianvale82@example.com", "vale.dorian@example.com", "dvale@example.com", "dorian85@example.com"])
def test_an_address_that_reads_as_the_respondents_name_needs_confirmation(address):
    out = _resp(address)
    assert out.decision == ri.NEEDS_CONFIRMATION and "looks like the respondent's" in out.reason


def test_the_warning_names_neither_person():
    out = _resp("dorian.vale@example.com")
    assert "dorian" not in out.reason.lower().replace("dorian.vale@example.com", "") and "vale" not in out.reason.lower().replace("dorian.vale@example.com", "")


def test_an_address_recorded_for_the_respondent_needs_confirmation_whatever_it_looks_like():
    out = _resp("xyz123@gmail.com", respondent_addresses=["x.y.z123+tag@googlemail.com"])
    assert out.decision == ri.NEEDS_CONFIRMATION and "recorded for the respondent" in out.reason


@pytest.mark.parametrize("address", ["chalia.sample@example.com", "csample@example.com", "sample.family@example.com", "chaz55@example.com", "chalia1@example.com"])
def test_a_respondent_sharing_the_clients_surname_does_not_raise_it_on_the_surname(address):
    assert _resp(address, respondent="Dorian Sample").decision == ri.ALLOW


def test_the_shared_surname_with_the_respondents_initial_or_name_still_does():
    assert _resp("dsample@example.com", respondent="Dorian Sample").decision == ri.NEEDS_CONFIRMATION
    assert _resp("dorian.sample@example.com", respondent="Dorian Sample").decision == ri.NEEDS_CONFIRMATION


def _lookalike(address, *, respondent="Ian Marlow", client="Annabel Marlow", respondent_addresses=()):
    return ri.respondent_lookalike(address, [respondent], [client], respondent_addresses)


@pytest.mark.parametrize("address", ["marlow2608@example.com", "marlow.1994@example.com", "marlow@example.com", "marlow24@example.com"])
def test_a_surname_both_people_carry_plus_digits_is_never_the_respondents(address):
    assert _lookalike(address) == ""
    assert _resp(address, respondent="Ian Marlow", client="Annabel Marlow").decision == ri.ALLOW


@pytest.mark.parametrize("address", ["annabel.marlow@example.com", "annabelmarlow1@example.com", "amarlow@example.com"])
def test_a_shared_surname_with_the_clients_own_given_name_or_initial_is_not_the_respondents(address):
    assert _lookalike(address) == ""


def test_a_shared_surname_with_the_respondents_given_name_initial_or_recorded_address_still_is():
    assert "looks like the respondent's" in _lookalike("ianmarlow30@example.com")
    assert "looks like the respondent's" in _lookalike("ian85@example.com")
    assert "looks like the respondent's" in _lookalike("imarlow@example.com")
    assert "recorded for the respondent" in _lookalike("sample2608@gmail.com", respondent_addresses=["sample2608@gmail.com"])


def test_the_respondents_given_name_and_surname_with_digits_is_flagged_when_the_surnames_differ():
    assert "looks like the respondent's" in _lookalike("dorianvale30@example.com", respondent="Dorian Vale", client="Chalia Sample")


def test_an_address_that_is_only_the_respondents_own_surname_is_unchanged():
    assert _lookalike("vale2608@example.com", respondent="Dorian Vale", client="Chalia Sample") == ""


def test_an_address_that_clearly_matches_the_client_is_not_read_as_the_respondents():
    out = _resp("chalia.sample@example.com", respondent="Chalia Sample-Vale")
    assert out.decision == ri.ALLOW


def test_a_confirmed_respondent_lookalike_reads_as_allow():
    assert _resp("dorian.vale@example.com", confirmed_addresses=["dorian.vale@example.com"]).decision == ri.ALLOW


def test_confirmation_never_lifts_a_refuse():
    near = ri.check_client_recipient(
        expected_names=["Mark Marlow"], addresses=["bigdaddy98@example.com"], recorded_addresses=["bigdaddy99@example.com"],
        confirmed_addresses=["bigdaddy98@example.com"],
    )
    assert near.decision == ri.REFUSE
    greeting = ri.check_client_recipient(
        expected_names=["Mark Marlow"], addresses=["bigdaddy99@example.com"], body="Dear Sarah,", confirmed_addresses=["bigdaddy99@example.com"]
    )
    assert greeting.decision == ri.REFUSE
