from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from documents import model_proofread as mp

CLIENT = "Testa Fakename"
RESPONDENT = "Rory Fakename"


def _paragraph_of(prompt: str) -> str:
    return prompt.split("Paragraph:\n", 1)[1]


def _model(replace: dict[str, str]):

    def run(system: str, prompt: str) -> str:
        text = _paragraph_of(prompt)
        for old, new in replace.items():
            text = text.replace(old, new)
        return json.dumps({"corrected": text})

    return run


def _run(paragraphs, replace, protected=(CLIENT, RESPONDENT)):
    return mp.proofread(paragraphs, protected=protected, runner=_model(replace))


def _applied(result):
    return [(e.original, e.replacement) for e in result.edits if e.applied]


def _left(result):
    return [e for e in result.edits if not e.applied]


def _apply(text: str, result, para: int = 0) -> str:
    for e in sorted((e for e in result.edits if e.applied and e.para == para), key=lambda e: e.start, reverse=True):
        text = text[: e.start] + e.replacement + text[e.end :]
    return text


def test_a_typo_is_fixed_and_listed_with_its_paragraph_and_context():
    text = "3. I recieved a letter from the court last month and I was frightened."
    result = _run([text], {"recieved": "received"})
    assert result.checked and result.failures == 0
    assert _apply(text, result) == "3. I received a letter from the court last month and I was frightened."
    edit = [e for e in result.edits if e.applied][0]
    assert edit.label == "3" and "recieved" in edit.before and "received" in edit.after


def test_a_missing_small_word_is_put_back_when_the_pronoun_is_already_in_the_paragraph():
    text = "On the day he came home when became very angry with me. He shouted for an hour and left."
    result = _run([text], {"when became": "when he became"})
    assert _apply(text, result) == "On the day he came home when he became very angry with me. He shouted for an hour and left."


def test_a_pronoun_that_is_nowhere_in_the_paragraph_is_not_guessed():
    text = "Later the visitor arrived when became very angry with me and shouted for an hour."
    result = _run([text], {"when became": "when she became"})
    assert _applied(result) == []
    assert any("pronoun" in e.reason for e in _left(result))


def test_a_word_split_and_a_plural_typo_are_fixed():
    text = "He would embarrass me Infront of friends and the Respondents behaviour was cruel to me."
    result = _run([text], {"Infront": "in front", "Respondents behaviour": "Respondent's behaviour"})
    assert _apply(text, result) == "He would embarrass me in front of friends and the Respondent's behaviour was cruel to me."


def test_numbers_dates_and_names_are_hidden_from_the_model_and_a_changed_placeholder_is_rejected():
    text = "On 14 October Rory Fakename shouted at me for 3 hours and I was afraid of him."
    seen = []

    def spy(system, prompt):
        seen.append(prompt)
        return json.dumps({"corrected": _paragraph_of(prompt)})

    mp.proofread([text], protected=[CLIENT, RESPONDENT], runner=spy)
    assert "14" not in seen[0] and "Rory" not in seen[0] and "3 hours" not in seen[0]
    for replace in ({"DATE_A": "DATE_B"}, {"NUMBER_A": "NUMBER_B"}, {"PERSON_A": "PERSON_B"}):
        result = _run([text], replace)
        assert _applied(result) == [], replace
        assert _left(result), replace


def test_the_guard_itself_refuses_a_changed_digit_or_protected_name():
    corpus = "x"
    assert mp._allowed("for 3 hours", "for 2 hours", "for 3 hours", [], corpus, False) == "changes a number"
    assert mp._allowed("Rory Fakename shouted", "Rory Fakeman shouted", "Rory Fakename shouted", [RESPONDENT], corpus, False) == "touches a name or place"


def test_words_in_quotation_marks_are_never_touched():
    text = "He said “you will never find anybody” and I was very upset about it that night."
    result = _run([text], {"never find anybody": "never find anyone"})
    assert _applied(result) == []


def test_a_moved_word_is_left_for_a_person_not_applied():
    text = "He became verbally aggressive towards whilst we were out. me. He was angry."
    result = _run([text], {"towards whilst we were out. me.": "towards me whilst we were out."})
    assert _applied(result) == []
    assert _left(result), "the garbled sentence is listed for a person"


def test_a_new_proper_noun_is_never_added():
    text = "I went to the shop and he followed me home and shouted at me in the street."
    result = _run([text], {"to the shop": "to the Tesco shop"})
    assert _applied(result) == []


def test_a_swap_that_is_not_a_typo_is_left():
    text = "The Respondent was very controlling and he would shout at me every single evening."
    result = _run([text], {"controlling": "dominant"})
    assert _applied(result) == [] and _left(result)


def test_a_model_that_changes_a_placeholder_is_rejected_for_the_whole_paragraph():
    text = "On 14 October Rory Fakename shouted at me and I recieved no help from anybody there."

    def bad(system, prompt):
        return json.dumps({"corrected": _paragraph_of(prompt).replace("PERSON_A", "PERSON_B").replace("recieved", "received")})

    result = mp.proofread([text], protected=[CLIENT, RESPONDENT], runner=bad)
    assert _applied(result) == [] and _left(result)


def test_a_model_that_is_down_leaves_every_paragraph_as_written_and_says_not_checked():
    texts = ["1. I recieved a letter from the court last month and I was frightened.", "2. He shouted at me for an hour and then he left."]
    result = mp.proofread(texts, protected=[], runner=lambda system, prompt: None)
    assert result.checked is False and result.failures == 2 and result.edits == []


def test_an_unusable_reply_counts_as_a_failure():
    result = mp.proofread(["1. I recieved a letter from the court last month and I was frightened."], runner=lambda system, prompt: "sorry, I cannot")
    assert result.checked is False and result.failures == 1


def test_headings_and_fragments_are_not_sent_to_the_model():
    sent = []

    def run(system, prompt):
        sent.append(prompt)
        return json.dumps({"corrected": _paragraph_of(prompt)})

    mp.proofread(["BACKGROUND INFORMATION", "Signed:", "1. I recieved a letter from the court last month and I was frightened."], runner=run)
    assert len(sent) == 1


def test_the_prompt_asks_for_british_english_and_forbids_changing_facts():
    assert "British English" in mp.SYSTEM
    assert "NEVER add, remove or change a fact" in mp.SYSTEM


def test_the_number_of_fixes_in_one_paragraph_is_capped():
    text = "a1 teh b2 recieved c3 adn d4 wich e5 becuase f6 thier g7 definately h8 seperate i9 occured end of the long paragraph here."
    swaps = {"teh": "the", "recieved": "received", "adn": "and", "wich": "which", "becuase": "because", "thier": "their", "definately": "definitely", "seperate": "separate", "occured": "occurred"}
    result = _run([text], swaps)
    assert len([e for e in result.edits if e.applied]) <= mp.MAX_FIXES_PER_PARAGRAPH




def test_a_plural_possessive_is_never_produced_but_word_s_to_word_apostrophe_s_is():
    text = "This leaves me anxious about myself and my sons safety. I am extremely afraid of what he will do."
    result = _run([text], {"my sons safety": "my sons' safety"})
    assert _applied(result) == []
    assert any("plural possessive" in e.reason for e in _left(result))

    result = _run([text], {"my sons safety": "my son's safety"})
    assert _apply(text, result) == "This leaves me anxious about myself and my son's safety. I am extremely afraid of what he will do."

    text = "The Respondents behaviour was cruel and I was afraid of him all of the time at home."
    result = _run([text], {"Respondents behaviour": "Respondent's behaviour"})
    assert _apply(text, result) == "The Respondent's behaviour was cruel and I was afraid of him all of the time at home."


def test_an_s_apostrophe_already_in_the_text_is_untouched_and_an_apostrophe_is_never_removed():
    text = "The brothers' room was small and the Respondent's temper was bad whenever he came home late."
    assert _applied(_run([text], {})) == []
    assert _applied(_run([text], {"Respondent's": "Respondents"})) == []


def test_it_apostrophe_s_is_never_guessed():
    text = "The dog hurt its paw and I took it to the vet on the same day that he left."
    assert _applied(_run([text], {"its paw": "it's paw"})) == []


def test_two_edits_that_touch_or_sit_one_word_apart_are_both_left():
    text = "He was verbal and physically abusive towards me throughout the whole of our long relationship."
    result = _run([text], {"verbal and physically abusive": "verbally and physical abusive"})
    assert _applied(result) == []
    assert len(_left(result)) >= 2
    text = "On that day he recieved the leter from the court and he was very angry with me about it."
    result = _run([text], {"recieved": "received", "leter": "letter"})
    assert _applied(result) == []
    assert len(_left(result)) == 2
    assert all("next to another change" in e.reason for e in _left(result))


def test_edits_far_apart_are_both_applied():
    text = "I recieved a letter on that day, and after a long wait at the door I was afraid of the teh man outside."
    result = _run([text], {"recieved": "received", "teh man": "the man"})
    assert _apply(text, result) == "I received a letter on that day, and after a long wait at the door I was afraid of the the man outside."


def test_the_final_check_refuses_a_change_outside_every_approved_edit():
    text = "I went to the shop and bought some bread for the family."
    good = [mp.Edit(0, "1", 7, 9, "to", "at", True)]
    assert mp._changes_stay_inside_edits(text, mp._apply(text, good), good) is True
    assert mp._changes_stay_inside_edits(text, text.replace("bread", "milk"), good) is False


def test_the_heading_block_party_lines_and_all_capitals_are_never_sent_to_the_model():
    sent = []

    def spy(system, prompt):
        sent.append(_paragraph_of(prompt))
        return json.dumps({"corrected": _paragraph_of(prompt)})

    paragraphs = [
        "IN THE FAMILY COURT AT TOWNSVILLE\tCASE NO:",
        "\tTESTA FAKENAME\tApplicant",
        "\tand",
        "FIRST WITNESS STATEMENT OF TESTA FAKENAME",
        "I, Testa Fakename, live at 1 Test Road and will say as follows:",
        "1.\tI recieved a letter from the court last month and I was frightened.",
        "BACKGROUND INFORMATION IN CAPITALS",
        "\tA tabbed line that is long enough to be a paragraph but starts with a tab character here.",
    ]
    mp.proofread(paragraphs, protected=[CLIENT], runner=spy)
    assert len(sent) == 2 and sent[1].startswith("I recieved a letter")


def test_a_numbering_or_lettering_prefix_and_its_tab_are_never_touched():
    for prefix in ("13.\t", "c.\t", "3. ", "   "):
        text = f"{prefix}Throughout the relationship he would belittle me infront of my friends and family."
        result = _run([text], {"infront": "in front"})
        assert _apply(text, result) == f"{prefix}Throughout the relationship he would belittle me in front of my friends and family.", prefix
        assert all(e.start >= len(prefix) for e in result.edits), prefix


def test_an_edit_that_changes_a_tab_inside_the_text_is_left():
    text = "I said\tthat he was angry with me and I stayed at home with the children all night."
    result = _run([text], {"said\tthat": "said that"})
    assert _applied(result) == []
    assert "\t" in _apply(text, result)


def test_whitespace_edits_are_limited_to_doubled_spaces_and_trailing_spaces():
    text = "I went  home and then I recieved no help at all from anybody that I asked.  "
    result = _run([text], {"went  home": "went home", "recieved": "received", "asked.  ": "asked."})
    fixed = _apply(text, result)
    assert "  home" not in fixed and "received" in fixed and not fixed.endswith(" ")
    other = "I went home and stayed there all night long and then I left in the morning."
    assert _applied(_run([other], {"went home": "went\thome"})) == []


def test_the_command_line_helper_prints_the_change_list_for_a_docx(tmp_path, capsys):
    from docx import Document

    doc = Document()
    doc.add_paragraph("IN THE FAMILY COURT AT TOWNSVILLE")
    doc.add_paragraph("FIRST WITNESS STATEMENT OF TESTA FAKENAME")
    doc.add_paragraph("1.\tI recieved a letter from the court last month and I was frightened.")
    path = tmp_path / "s.docx"
    doc.save(str(path))
    assert mp.main([str(path), "--protect", CLIENT, "--fake", "recieved=>received"]) == 0
    out = capsys.readouterr().out
    assert "Corrections made (1)" in out and "Paragraph 1:" in out and "TOWNSVILLE" not in out
    assert mp.main([str(path)]) == 0
    assert "Corrections made (0)" in capsys.readouterr().out


def test_a_plural_or_tense_change_is_a_word_change_not_a_typo():
    text = "The court heard the case after the applicant made the applications without notice and I was told to wait."
    result = _run([text], {"applications": "application"})
    assert _applied(result) == []
    assert any("number or tense" in e.reason for e in _left(result))
    text = "I would tell him to stop but he kept on and I was afraid of what he might do to me at home."
    assert _applied(_run([text], {"tell": "telling"})) == []
    text = "He smiles at the children but he is cruel to me when they have gone to school each day."
    assert _applied(_run([text], {"smiles": "smile"})) == []
    text = "He was quick to anger and would shout loudly at me and the children in front of our neighbours."
    assert _applied(_run([text], {"loudly": "loud"})) == []


def test_real_typos_and_a_past_tense_joined_by_and_still_apply():
    text = "He would push and shoved me against the wall whenever I recieved a message from my sister."
    result = _run([text], {"push and": "pushed and", "recieved": "received"})
    assert _apply(text, result) == "He would pushed and shoved me against the wall whenever I received a message from my sister."
    text = "I was in receipt of a letter and I decided to tun up at the house that evening to see him."
    assert _apply(text, _run([text], {"tun up": "turn up"})).count("turn up") == 1


def test_protected_address_text_is_untouchable_even_for_a_comma():
    address = "12 Example Avenue, Sampletown TE10 1ST"
    text = "I live at 12 Example Avenue, Sampletown TE10 1ST, with my two children and I recieved the letter there."
    result = _run([text], {"TE10 1ST,": "TE10 1ST,", "Sampletown TE10": "Sampletown, TE10"}, protected=(CLIENT, address))
    assert not any(e.applied and "Sampletown" in (e.before + e.after) for e in result.edits)
    assert "Sampletown TE10 1ST," in _apply(text, result)
    result = _run([text], {"recieved": "received"}, protected=(CLIENT, address))
    assert "received" in _apply(text, result)


def test_an_edit_next_to_a_protected_name_is_left():
    assert mp._touches_protected("I told Rory Fakename that", 20, 20, ["Rory Fakename"]) is True
    assert mp._touches_protected("I told Rory Fakename that", 0, 1, ["Rory Fakename"]) is False


def test_a_paragraph_the_model_fails_to_answer_is_asked_again_before_it_counts_as_unchecked(monkeypatch):
    calls = []

    class Reply:
        def __init__(self, ok, text=""):
            self.ok, self.text = ok, text

    def fake_run_model(*args, **kwargs):
        calls.append(1)
        return Reply(False) if len(calls) < 3 else Reply(True, '{"corrected": "ok"}')

    monkeypatch.setattr(mp.model_backend, "run_model", fake_run_model)
    monkeypatch.setattr(mp.model_backend, "model_for_role", lambda *a, **k: "m")
    monkeypatch.setattr(mp, "RUNNER_PAUSE_S", 0)
    assert mp.default_runner("s", "p") == '{"corrected": "ok"}'
    assert len(calls) == 3


def test_a_paragraph_that_fails_every_try_still_returns_none(monkeypatch):
    class Reply:
        ok, text = False, ""

    monkeypatch.setattr(mp.model_backend, "run_model", lambda *a, **k: Reply())
    monkeypatch.setattr(mp.model_backend, "model_for_role", lambda *a, **k: "m")
    monkeypatch.setattr(mp, "RUNNER_PAUSE_S", 0)
    assert mp.default_runner("s", "p") is None


def test_the_proofread_call_asks_for_little_thinking_and_has_room_to_answer(monkeypatch):
    seen = {}

    class Reply:
        ok, text = True, '{"corrected": "ok"}'

    def fake_run_model(role, prompt, **kwargs):
        seen.update(kwargs)
        return Reply()

    monkeypatch.setattr(mp.model_backend, "run_model", fake_run_model)
    monkeypatch.setattr(mp.model_backend, "model_for_role", lambda *a, **k: "m")
    mp.default_runner("s", "p")
    assert seen["reasoning"] == "low" and seen["max_tokens"] >= 6000




def _two(first: dict[str, str] | None, second: dict[str, str] | None, protected=(CLIENT, RESPONDENT)):
    calls = {"first": 0, "second": 0}

    def make(name, replace):
        def run(system: str, prompt: str):
            calls[name] += 1
            if replace is None:
                return None
            return json.dumps({"corrected": _paragraph_of(prompt).split("\n\nNotes from the first proofreader:", 1)[0].replace(*next(iter(replace.items()))) if len(replace) == 1 else _paragraph_of(prompt)})
        return run

    def runner(paragraphs):
        return mp.proofread(paragraphs, protected=protected, runner=make("first", first), second=make("second", second))

    return runner, calls


def test_a_second_model_settles_what_the_guard_refused_the_first_time():
    text = "4. I recieved a letter from the court last month and I was frightened."
    run, calls = _two({"I recieved a letter": "A letter reached me"}, {"recieved": "received"})
    result = run([text])
    assert calls["second"] == 1
    assert result.checked
    assert _apply(text, result) == "4. I received a letter from the court last month and I was frightened."
    assert not any("for a person" in e.reason for e in result.edits)


def test_what_even_the_second_model_cannot_get_past_the_guard_is_kept_as_written_never_left_for_a_person():
    text = "5. I saw him at the house and he said “go away” to me in front of the children."
    run, calls = _two({"go away": "go home"}, {"go away": "get out"})
    result = run([text])
    assert result.checked and calls["second"] == 1
    assert _apply(text, result) == text
    kept = _left(result)
    assert kept and all(e.reason.startswith("kept as written") for e in kept)
    assert not any("for a person" in e.reason for e in result.edits)
    report = mp.format_change_list(result)
    assert "Left for a person" not in report and "Kept as the client wrote it" in report


def test_the_second_model_is_not_asked_when_the_first_had_nothing_refused():
    text = "6. I recieved a letter from the court last month and I was frightened."
    run, calls = _two({"recieved": "received"}, {"recieved": "received"})
    result = run([text])
    assert calls["second"] == 0 and _apply(text, result) == "6. I received a letter from the court last month and I was frightened."


def test_the_second_model_is_the_fallback_when_the_first_cannot_answer():
    text = "7. I recieved a letter from the court last month and I was frightened."
    run, calls = _two(None, {"recieved": "received"})
    result = run([text])
    assert result.checked and result.failures == 0 and calls["second"] == 1
    assert _apply(text, result) == "7. I received a letter from the court last month and I was frightened."


def test_both_models_down_is_spelling_not_checked_and_the_text_is_untouched():
    text = "8. I recieved a letter from the court last month and I was frightened."
    run, calls = _two(None, None)
    result = run([text])
    assert not result.checked and result.failures == 1
    assert _apply(text, result) == text
    assert "SPELLING NOT CHECKED" in mp.format_change_list(result)


def test_the_note_given_to_the_second_model_hides_names_like_the_text_does():
    seen: list[str] = []

    def first(system, prompt):
        return json.dumps({"corrected": _paragraph_of(prompt).replace("recieved a letter", "got a letter")})

    def second(system, prompt):
        seen.append(prompt)
        return json.dumps({"corrected": _paragraph_of(prompt).split("\n\nNotes", 1)[0]})

    text = f"9. {RESPONDENT} recieved a letter from the court and told {CLIENT} about it last month."
    mp.proofread([text], protected=(CLIENT, RESPONDENT), runner=first, second=second)
    assert seen and CLIENT not in seen[0] and RESPONDENT not in seen[0]



HEAD = ["FIRST WITNESS STATEMENT OF TESTA FAKENAME"]


def _after(text, replace):
    full = f"1. {text}"
    result = _run(HEAD + [full], replace)
    applied = [e for e in result.edits if e.applied]
    return mp._apply(full, applied)[3:], applied


def test_a_typo_next_to_a_time_or_an_ordinal_is_fixed():
    for text, replace, want in [
        ("I recieved a text at about 9pm saying he would be late.", {"recieved": "received"}, "I received a text at about 9pm saying he would be late."),
        ("The incident happend on the 12th of the month at 7.30pm.", {"happend": "happened"}, "The incident happened on the 12th of the month at 7.30pm."),
        ("She is settleing in since the 2nd of the month.", {"settleing": "settling"}, "She is settling in since the 2nd of the month."),
    ]:
        assert _after(text, replace)[0] == want, text


def test_a_number_the_model_swaps_is_refused_with_the_whole_paragraph():
    text = "I recieved a text at about 9pm saying he would be late."
    assert _after(text, {"recieved": "received", "NUMBER_A": "NUMBER_B"}) == (text, [])


def test_a_misplaced_apostrophe_is_moved_and_never_just_removed():
    assert _after("He did'nt tell me why he was late.", {"did'nt": "didn't"})[0] == "He didn't tell me why he was late."
    assert _after("I could'nt ring anyone from the house.", {"could'nt": "couldn't"})[0] == "I couldn't ring anyone from the house."
    text = "He told me that the dog's lead was lost somewhere."
    assert _after(text, {"dog's": "dogs"}) == (text, [])


def test_should_of_becomes_should_have_but_other_word_swaps_stay_refused():
    assert _after("He told me I should of known better than to go.", {"should of": "should have"})[0] == "He told me I should have known better than to go."
    text = "He told me I should go home before it got dark."
    assert _after(text, {"should go": "must go"}) == (text, [])


def test_a_doubled_word_is_dropped_whichever_copy_the_diff_deletes():
    assert _after("He took the the keys from the table and left.", {"the the": "the"})[0] == "He took the keys from the table and left."
    assert _after("I have not seen him since the the 12th of the month.", {"the the": "the"})[0] == "I have not seen him since the 12th of the month."
    text = "He took the keys from the table and left."
    assert _after(text, {"table": "keys"}) == (text, [])


def test_a_space_and_comma_moved_across_each_other_is_one_repair():
    text = "She was crying and I was scared that he would hurt her ,so I picked her up."
    after, applied = _after(text, {" ,so": ", so"})
    assert after == "She was crying and I was scared that he would hurt her, so I picked her up." and len(applied) == 1


def test_its_before_been_or_going_is_it_is_but_a_bare_its_is_never_guessed():
    assert _after("Its been very hard for the family since then.", {"Its been": "It's been"})[0] == "It's been very hard for the family since then."
    text = "The dog hurt its paw on the gate last week."
    assert _after(text, {"its paw": "it's paw"}) == (text, [])


def test_a_paragraph_opening_in_lowercase_gets_its_capital_without_a_model():
    for text, want in [("my mum helps me a lot with the children.", "My mum helps me a lot with the children."),
                       ("he came back at about midnight and left.", "He came back at about midnight and left.")]:
        assert _after(text, {})[0] == want
    keep = "iPhone messages were sent to me all night."
    assert _after(keep, {}) == (keep, [])




def test_an_is_never_made_a_before_a_vowel_and_a_is_made_an_only_where_it_is_clear():
    keep = "She asked for an order to protect the children from him."
    assert _after(keep, {"an order": "a order"}) == (keep, [])
    assert _after("She asked for a order to protect the children.", {"a order": "an order"})[0] == "She asked for an order to protect the children."
    assert _after("I bought a apple from the shop on the corner.", {"a apple": "an apple"})[0] == "I bought an apple from the shop on the corner."
    assert _after("It was an cold night and we stayed indoors.", {"an cold": "a cold"})[0] == "It was a cold night and we stayed indoors."
    unsure = "She waited for a hour outside the house that night."
    assert _after(unsure, {"a hour": "an hour"})[0] == "She waited for an hour outside the house that night."
    ambiguous = "It was an university course that she had joined."
    assert _after(ambiguous, {"an university": "a university"}) == (ambiguous, [])


def test_a_person_or_negative_word_is_never_swapped_for_another_as_a_typo():
    for text, swap in [
        ("She told me that she would not come to the house.", {"she would": "he would"}),
        ("I do not think he came to the house that day at all.", {"he came": "she came"}),
        ("There was no reason for him to be in the house.", {"no reason": "not reason"}),
        ("They said their dog was missing from the garden.", {"They said": "We said"}),
    ]:
        assert _after(text, swap) == (text, []), text
    assert _after("She said hte dog was missing from the garden.", {"hte": "the"})[0] == "She said the dog was missing from the garden."
