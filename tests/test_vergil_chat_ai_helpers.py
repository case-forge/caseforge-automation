import pytest
import csv
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vergil_chat.vergil_chat_ai_helpers import (
    small_model_label,
    _small_model_reasoning,
    audit_document_rename,
    nano_label,
    route_intent,
    suggest_chat_title,
    suggest_document_label,
    suggest_legal_aid_client_queries,
    validate_chat_title,
    validate_label,
)


def test_deterministic_route_wins_over_nano():
    result = route_intent("Make an attendance note for Jane Ashtest", nano_func=lambda _prompt: "drafting")

    assert result["intent"] == "attendance_note"
    assert result["source"] == "deterministic"


def test_tell_me_about_is_deterministic_case_snapshot():
    result = route_intent("tell me about shnnon briartest", nano_func=lambda _prompt: "default")

    assert result["intent"] == "case_snapshot"
    assert result["source"] == "deterministic"


def test_small_model_label_is_the_chat_helpers_role_model(monkeypatch):
    import model_backend

    for name in ("CASEFORGE_CHAT_SMALL_MODEL", "CASEFORGE_CHAT_NANO_MODEL", "CASEFORGE_CHAT_SMALL_ROUTER_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert small_model_label() == model_backend.model_for_role(model_backend.ROLE_CHAT_HELPERS)
    monkeypatch.setenv("CASEFORGE_CHAT_SMALL_MODEL", "label/override")
    assert small_model_label() == "label/override"


def test_nano_unavailable_falls_back_default():
    result = route_intent("Please handle this", nano_func=lambda _prompt: "")

    assert result == {"intent": "default", "source": "fallback", "model": ""}


def test_label_validation_rejects_address_like_label():
    ok, reason = validate_label("Sealed order ZZ99 9ZZ")

    assert not ok
    assert reason == "postcode/address-like content"


def test_suggest_label_uses_valid_small_model_label_and_keeps_fallback():
    result = suggest_document_label("misc scan", nano_func=lambda _title: "Sealed order")

    assert result["label"] == "Sealed order"
    assert result["source"] == "model"
    assert result["model"] == small_model_label()
    assert result["fallback_label"] == "Misc Scan"


def test_chat_title_uses_valid_small_model_title():
    result = suggest_chat_title(
        [
            {"role": "user", "content": "Use tasks/startup-monitor/AGENT.md. Run startup"},
            {"role": "assistant", "content": "Startup completed."},
        ],
        nano_func=lambda _transcript: "Startup Review",
    )

    assert result["title"] == "Startup Review"
    assert result["source"] == "model"
    assert result["model"] == small_model_label()


def test_chat_title_rejects_contact_details():
    ok, reason = validate_chat_title("Ashtest 07700 900123")

    assert not ok
    assert reason == "phone-like content"


def test_audit_document_rename_writes_csv(tmp_path: Path):
    path = audit_document_rename(
        {
            "source": "nano",
            "old_label": "scan 1",
            "suggested_label": "Sealed order",
            "accepted": True,
            "matter_id": "123",
            "graph_item_id": "abc",
        },
        tmp_path,
    )

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["suggested_label"] == "Sealed order"
    assert rows[0]["accepted"] == "1"
    assert rows[0]["old_label_hash"]
    assert rows[0]["graph_item_id_hash"]


def test_small_model_routes_through_model_backend(monkeypatch):
    from vergil_chat import vergil_chat_ai_helpers
    import model_backend

    monkeypatch.setenv("CASEFORGE_CHAT_ENABLE_SMALL_MODEL", "1")

    seen = {}

    def fake_run_text(role, prompt, **kwargs):
        seen["role"] = role
        seen["route_reason"] = kwargs.get("route_reason")
        return "client_search"

    monkeypatch.setattr(model_backend, "run_text", fake_run_text)
    assert not hasattr(vergil_chat_ai_helpers, "_codex_cli_text")
    assert not hasattr(vergil_chat_ai_helpers, "_openai_api_text")

    out = vergil_chat_ai_helpers._small_model_text("classify me", max_output_tokens=12, reasoning="low")
    assert out == "client_search"
    assert seen["role"] == model_backend.ROLE_CHAT_HELPERS
    assert seen["route_reason"] == "caseforge-chat:small"


def test_small_model_reasoning_global_override_wins(monkeypatch):
    monkeypatch.setenv("CASEFORGE_CHAT_SMALL_MODEL_REASONING", "high")
    monkeypatch.setenv("CASEFORGE_CHAT_ROUTER_REASONING", "low")

    assert _small_model_reasoning("low") == "high"


def test_task_reasoning_defaults_are_passed(monkeypatch):
    from vergil_chat import vergil_chat_ai_helpers

    calls = []

    def fake_unified(prompt, *, timeout, reasoning):
        calls.append({"prompt": prompt, "reasoning": reasoning})
        if "Classify this CaseForge" in prompt:
            return "default"
        if "history title" in prompt:
            return "Startup Review"
        if "short neutral file label" in prompt:
            return "Sealed order"
        return ""

    monkeypatch.setenv("CASEFORGE_CHAT_ENABLE_SMALL_MODEL", "1")
    monkeypatch.delenv("CASEFORGE_CHAT_SMALL_MODEL_REASONING", raising=False)
    import small_model_text

    monkeypatch.setattr(small_model_text, "_unified_backend_text", fake_unified)

    assert vergil_chat_ai_helpers.nano_route_intent("Please handle this") == "default"
    assert vergil_chat_ai_helpers.nano_chat_title("user: run startup") == "Startup Review"
    assert vergil_chat_ai_helpers.nano_label("misc scan") == "Sealed order"

    assert [call["reasoning"] for call in calls] == ["low", "low", "low"]


def test_legal_aid_client_query_helper_forces_codex_spark(monkeypatch):
    from vergil_chat import vergil_chat_ai_helpers

    calls = []

    def fake_small_model_text(prompt, *, max_output_tokens, timeout=None, model=None, reasoning=None):
        calls.append(
            {
                "prompt": prompt,
                "model": model,
                "max_output_tokens": max_output_tokens,
                "timeout": timeout,
                "reasoning": reasoning,
            }
        )
        return '["Anna Ashtest", "Beth Jackdawtest"]'

    monkeypatch.setattr(vergil_chat_ai_helpers, "_small_model_text", fake_small_model_text)

    assert suggest_legal_aid_client_queries("anna ashtest and beth jackdawtest") == ["Anna Ashtest", "Beth Jackdawtest"]
    assert calls[0]["model"] == small_model_label()
    assert calls[0]["reasoning"] == "medium"


def test_legal_aid_client_query_helper_keeps_more_than_nine_names(monkeypatch):
    import json

    from vergil_chat import vergil_chat_ai_helpers

    names = [f"Client {idx}" for idx in range(11)]
    monkeypatch.setattr(vergil_chat_ai_helpers, "_small_model_text", lambda *_args, **_kwargs: json.dumps(names))

    assert suggest_legal_aid_client_queries("eleven clients") == names


def test_legal_aid_client_query_helper_never_slices_a_long_request(monkeypatch):
    pytest.importorskip("graph_files")
    from vergil_chat import vergil_chat_ai_helpers, vergil_chat_legal_aid

    def no_model(*_args, **_kwargs):
        raise AssertionError("a request over the limit must not reach the model sliced")

    monkeypatch.setattr(vergil_chat_ai_helpers, "_small_model_text", no_model)
    names = [f"Client{idx} Testperson" for idx in range(80)]
    text = ", ".join(names)
    assert len(text) > vergil_chat_ai_helpers.CLIENT_QUERY_INPUT_LIMIT
    assert suggest_legal_aid_client_queries(text) == []
    queries = vergil_chat_legal_aid.ai_client_queries(text)
    assert queries == vergil_chat_legal_aid.deterministic_client_queries(text)
    assert any("Client79" in query for query in queries)


def test_document_labelling_lives_in_documents_and_chat_keeps_an_alias():
    from documents import document_labels
    from vergil_chat import vergil_chat_ai_helpers as chat

    assert chat.deterministic_document_label is document_labels.deterministic_document_label
    assert document_labels.deterministic_document_label("Re: Notice of hearing") == "NOH from Court"
    assert document_labels.validate_label("Sealed order") == (True, "Sealed order")
    assert document_labels.validate_label("../x")[0] is False
