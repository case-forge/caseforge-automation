from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import name_extractor as ne


@pytest.mark.slow
def test_title_casing_catches_a_name_raw_text_misses():
    assert ne.extract_candidate_names("jane doe") == ["Jane Doe"]


@pytest.mark.slow
def test_baseline_name_caught_either_way():
    assert ne.extract_candidate_names("julie wagtailtest") == ["Julie Wagtailtest"]


@pytest.mark.slow
def test_title_casing_recovers_the_full_two_token_span():
    assert ne.extract_candidate_names("kimberley jadetest") == ["Kimberley Jadetest"]


@pytest.mark.slow
def test_a_real_known_gap_is_not_silently_forced_to_match():
    assert ne.extract_candidate_names("dilek gentiantest") == []


@pytest.mark.slow
def test_full_chat_shaped_sentence():
    assert ne.extract_candidate_names(
        "what documents are outstanding for julie wagtailtest"
    ) == ["Julie Wagtailtest"]


@pytest.mark.slow
def test_no_name_present_returns_empty_list():
    assert ne.extract_candidate_names("what is the status of my case") == []
    assert ne.extract_candidate_names("has the ccl been sent yet") == []


@pytest.mark.slow
def test_repeated_mention_can_over_extend_the_second_span():
    result = ne.extract_candidate_names("jane doe called about jane doe case again")
    assert result == ["Jane Doe", "Jane Doe Case Again"]


@pytest.mark.slow
def test_duplicate_exact_mentions_are_deduplicated():
    result = ne.extract_candidate_names("jane doe spoke to jane doe's solicitor")
    assert result.count("Jane Doe") <= 1


@pytest.mark.slow
def test_dash_merged_span_is_split_into_both_real_names():
    result = ne.extract_candidate_names(
        "Casey Eagletest  - jay millettest, counsel from 33 Bedford Row. wnted to "
        "update us on case. told him to send attendance note to us instead "
        "through email."
    )
    assert "Casey Eagletest" in result
    assert "Jay Millettest" in result


@pytest.mark.slow
def test_hyphenated_surname_is_not_split():
    assert ne.extract_candidate_names("sebastian pipittest-brambletest called") == [
        "Sebastian Pipittest-Brambletest"
    ]



@pytest.mark.slow
def test_extract_weak_candidate_names_catches_a_real_name_misread_as_org():
    assert ne.extract_candidate_names("Georgia Ferntest") == []
    assert "Georgia Ferntest" in ne.extract_weak_candidate_names("Georgia Ferntest")


@pytest.mark.slow
def test_extract_weak_candidate_names_still_finds_a_real_person():
    assert "Tegan Mapletest" in ne.extract_weak_candidate_names("Tegan Mapletest")


@pytest.mark.slow
def test_extract_weak_candidate_names_empty_for_ordinary_small_talk():
    assert ne.extract_weak_candidate_names("how are you") == []
    assert ne.extract_weak_candidate_names("what can you do") == []



def test_extract_candidate_names_via_model_parses_json_array(monkeypatch):
    import model_backend

    seen = {}

    def fake_run_text(role, prompt, **kwargs):
        seen["role"] = role
        seen["prompt"] = prompt
        seen["timeout"] = kwargs.get("timeout")
        return '["Kirsty Mallowtest"]'

    monkeypatch.setattr(model_backend, "run_text", fake_run_text)
    result = ne.extract_candidate_names_via_model(
        "kirsty mallowtest called, what does she want"
    )
    assert result == ["Kirsty Mallowtest"]
    assert seen["role"] == model_backend.ROLE_NAME_EXTRACTOR
    assert "kirsty mallowtest called" in seen["prompt"]


def test_extract_candidate_names_via_model_dedupes_case_insensitively(monkeypatch):
    import model_backend

    monkeypatch.setattr(
        model_backend, "run_text", lambda role, prompt, **kwargs: '["Jane Doe", "jane doe"]'
    )
    assert ne.extract_candidate_names_via_model("jane doe called twice") == ["Jane Doe"]


def test_extract_candidate_names_via_model_empty_text_never_calls_the_backend(monkeypatch):
    import model_backend

    def fail(*args, **kwargs):
        raise AssertionError("must not call the backend for empty input")

    monkeypatch.setattr(model_backend, "run_text", fail)
    assert ne.extract_candidate_names_via_model("") == []
    assert ne.extract_candidate_names_via_model("   ") == []


def test_extract_candidate_names_via_model_survives_malformed_json(monkeypatch):
    import model_backend

    monkeypatch.setattr(model_backend, "run_text", lambda role, prompt, **kwargs: "not json")
    assert ne.extract_candidate_names_via_model("tell me about heidi basalttest") == []


def test_extract_candidate_names_via_model_survives_backend_failure(monkeypatch):
    import model_backend

    def raising(*args, **kwargs):
        raise RuntimeError("backend unavailable")

    monkeypatch.setattr(model_backend, "run_text", raising)
    assert ne.extract_candidate_names_via_model("tell me about heidi basalttest") == []


def test_extract_candidate_names_via_model_empty_backend_reply(monkeypatch):
    import model_backend

    monkeypatch.setattr(model_backend, "run_text", lambda role, prompt, **kwargs: "")
    assert ne.extract_candidate_names_via_model("who called today") == []


def test_extract_candidate_names_via_model_ignores_non_string_items(monkeypatch):
    import model_backend

    monkeypatch.setattr(
        model_backend, "run_text", lambda role, prompt, **kwargs: '["Jane Doe", 42, null]'
    )
    assert ne.extract_candidate_names_via_model("jane doe called") == ["Jane Doe"]
