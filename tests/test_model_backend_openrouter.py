
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import model_backend as mb


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")


def test_openrouter_in_registry():
    assert "openrouter" in mb.BACKENDS
    registry = mb.model_registry.load_registry()
    assert mb.model_for_role(mb.ROLE_CHAT_HELPERS, backend="openrouter") == registry["CASEFORGE_MODEL_CHAT_HELPERS"]
    assert mb.model_for_role(mb.ROLE_CASE_SUMMARY, backend="openrouter") == registry["CASEFORGE_MODEL_CASE_SUMMARY"]


def test_openrouter_is_not_a_default_or_auto_fallback():
    assert mb.DEFAULT_BACKEND == "openrouter"
    assert "openrouter" not in mb.fallback_chain()


def test_openrouter_opt_in_only_when_named(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_BACKEND", "openrouter")
    monkeypatch.delenv("CASEFORGE_MODEL_FALLBACKS", raising=False)
    assert mb.backend_order(mb.ROLE_CHAT_HELPERS) == ["openrouter"]


def test_openrouter_build_command_refuses():
    with pytest.raises(ValueError):
        mb.build_command("openrouter", "google/gemini-2.5-flash-lite", "prompt", "")


def _fake_response(content: str, usage: dict | None = None, finish_reason: str = "stop") -> dict:
    body = {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}
    if usage is not None:
        body["usage"] = usage
    return body


def test_openrouter_request_enforces_zdr_every_call(monkeypatch):
    seen = {}

    def fake_post(payload, api_key, timeout):
        seen.update(payload)
        return _fake_response("done")

    monkeypatch.setattr(mb, "_openrouter_post", fake_post)
    mb._run_openrouter("google/gemini-2.5-flash-lite", "classify this", timeout=30)
    assert seen["provider"] == {"data_collection": "deny", "zdr": True}
    assert seen["usage"] == {"include": True}
    assert seen["temperature"] == 0
    assert "tools" not in seen


def test_openrouter_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(mb.ModelBackendError, match="OPENROUTER_API_KEY"):
        mb._run_openrouter("m", "p", timeout=5)


def test_openrouter_strips_whitespace_and_think_blocks(monkeypatch):
    monkeypatch.setattr(
        mb, "_openrouter_post", lambda p, k, t: _fake_response("<think>hmm</think>  hello  ")
    )
    assert mb._run_openrouter("m", "p", timeout=5) == "hello"


def test_openrouter_empty_output_raises(monkeypatch):
    monkeypatch.setattr(mb, "_openrouter_post", lambda p, k, t: _fake_response(""))
    with pytest.raises(mb.ModelBackendError, match="empty output"):
        mb._run_openrouter("m", "p", timeout=5)


def test_openrouter_malformed_response_raises(monkeypatch):
    monkeypatch.setattr(mb, "_openrouter_post", lambda p, k, t: {"choices": []})
    with pytest.raises(mb.ModelBackendError):
        mb._run_openrouter("m", "p", timeout=5)


def test_openrouter_api_error_body_surfaces_clearly(monkeypatch):
    monkeypatch.setattr(
        mb, "_openrouter_post",
        lambda p, k, t: {"error": {"message": "No endpoints found matching your data policy", "code": 404}},
    )
    with pytest.raises(mb.ModelBackendError, match="data policy"):
        mb._run_openrouter("m", "p", timeout=5)


def test_openrouter_usage_maps_to_common_shape(monkeypatch):
    raw_usage = {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "cost": 0.0000045,
        "prompt_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 0},
    }
    monkeypatch.setattr(mb, "_openrouter_post", lambda p, k, t: _fake_response("ok", raw_usage))
    usage: dict = {}
    mb._run_openrouter("m", "p", timeout=5, usage=usage)
    assert usage == {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_tokens": 10,
        "cache_creation_tokens": 0,
        "estimated_cost_usd": 0.0000045,
    }


def test_openrouter_usage_absent_defaults_to_zero(monkeypatch):
    monkeypatch.setattr(mb, "_openrouter_post", lambda p, k, t: _fake_response("ok"))
    usage: dict = {}
    mb._run_openrouter("m", "p", timeout=5, usage=usage)
    assert usage["estimated_cost_usd"] == 0.0


def test_run_backend_routes_openrouter(monkeypatch):
    monkeypatch.setattr(mb, "_openrouter_post", lambda p, k, t: _fake_response("ok"))
    assert mb.run_backend("openrouter", "google/gemini-2.5-flash-lite", "p", timeout=5) == "ok"




def test_no_system_prompt_sends_a_single_user_message(monkeypatch):
    seen = {}

    def fake_post(payload, api_key, timeout):
        seen.update(payload)
        return _fake_response("ok")

    monkeypatch.setattr(mb, "_openrouter_post", fake_post)
    mb._run_openrouter("m", "classify this", timeout=5)
    assert seen["messages"] == [{"role": "user", "content": "classify this"}]


def test_system_prompt_is_sent_as_a_real_system_message_ahead_of_the_prompt(monkeypatch):
    seen = {}

    def fake_post(payload, api_key, timeout):
        seen.update(payload)
        return _fake_response("ok")

    monkeypatch.setattr(mb, "_openrouter_post", fake_post)
    mb._run_openrouter("m", "classify this", timeout=5, system_prompt="# Policy\n...")
    assert seen["messages"] == [
        {"role": "system", "content": "# Policy\n..."},
        {"role": "user", "content": "classify this"},
    ]


def test_empty_system_prompt_behaves_like_none(monkeypatch):
    seen = {}

    def fake_post(payload, api_key, timeout):
        seen.update(payload)
        return _fake_response("ok")

    monkeypatch.setattr(mb, "_openrouter_post", fake_post)
    mb._run_openrouter("m", "classify this", timeout=5, system_prompt="")
    assert seen["messages"] == [{"role": "user", "content": "classify this"}]


def test_run_backend_threads_system_prompt_to_openrouter_only(monkeypatch):
    seen = {}

    def fake_post(payload, api_key, timeout):
        seen.update(payload)
        return _fake_response("ok")

    monkeypatch.setattr(mb, "_openrouter_post", fake_post)
    mb.run_backend("openrouter", "m", "p", timeout=5, system_prompt="policy text")
    assert seen["messages"][0] == {"role": "system", "content": "policy text"}


def test_run_model_threads_system_prompt_through_to_the_runner(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    seen = {}

    def fake_post(payload, api_key, timeout):
        seen.update(payload)
        return _fake_response("ok")

    monkeypatch.setattr(mb, "_openrouter_post", fake_post)
    mb.run_model(
        mb.ROLE_SAFETY_GUARD, "classify this",
        model="openai/gpt-oss-safeguard-20b", backend="openrouter",
        system_prompt="policy text", telemetry=False,
    )
    assert seen["messages"][0] == {"role": "system", "content": "policy text"}


def test_run_model_omits_system_prompt_for_a_runner_stand_in_without_it(monkeypatch):
    calls = []

    def fake_runner(backend, model, prompt, *, timeout, reasoning=""):
        calls.append((backend, model, prompt))
        return "ok"

    result = mb.run_model(
        mb.ROLE_SAFETY_GUARD, "classify this", model="m", backend="openrouter",
        system_prompt="policy text", telemetry=False, _runner=fake_runner,
    )
    assert result.ok is True
    assert calls == [("openrouter", "m", "classify this")]


def test_openrouter_http_error_includes_response_body(monkeypatch):
    import io
    import urllib.error

    def fake_post(payload, api_key, timeout):
        raise urllib.error.HTTPError(
            "https://openrouter.ai/api/v1/chat/completions", 404, "Not Found", {},
            io.BytesIO(b'{"error": {"message": "No endpoints found matching your data policy"}}'),
        )

    monkeypatch.setattr(mb, "_openrouter_post", fake_post)
    with pytest.raises(mb.ModelBackendError, match="data policy"):
        mb._run_openrouter("m", "p", timeout=5)



def test_openrouter_request_sets_a_default_max_tokens(monkeypatch):
    seen = {}

    def fake_post(payload, api_key, timeout):
        seen.update(payload)
        return _fake_response("done")

    monkeypatch.setattr(mb, "_openrouter_post", fake_post)
    mb._run_openrouter("m", "p", timeout=5)
    assert seen["max_tokens"] == mb.DEFAULT_TEXT_MAX_TOKENS


def test_openrouter_request_honours_an_explicit_max_tokens_override(monkeypatch):
    seen = {}

    def fake_post(payload, api_key, timeout):
        seen.update(payload)
        return _fake_response("done")

    monkeypatch.setattr(mb, "_openrouter_post", fake_post)
    mb._run_openrouter("m", "p", timeout=5, max_tokens=1500)
    assert seen["max_tokens"] == 1500


def test_openrouter_short_completion_is_not_truncated_by_the_new_ceiling(monkeypatch):
    long_ish_text = "A" * 500
    monkeypatch.setattr(mb, "_openrouter_post", lambda p, k, t: _fake_response(long_ish_text))
    result = mb._run_openrouter("m", "p", timeout=5)
    assert result == long_ish_text
    assert len(result) == 500


def test_openrouter_402_raises_a_distinguishable_refusal_error(monkeypatch):
    import io
    import urllib.error

    def fake_post(payload, api_key, timeout):
        raise urllib.error.HTTPError(
            "https://openrouter.ai/api/v1/chat/completions", 402, "Payment Required", {},
            io.BytesIO(
                b'{"error":{"message":"This request requires more credits, or fewer '
                b'max_tokens. You requested up to 65535 tokens, but can only afford '
                b'13476.","code":402}}'
            ),
        )

    monkeypatch.setattr(mb, "_openrouter_post", fake_post)
    with pytest.raises(mb.ModelBackendRefusalError):
        mb._run_openrouter("m", "p", timeout=5)


def test_openrouter_in_body_402_also_raises_a_refusal_error(monkeypatch):
    monkeypatch.setattr(
        mb, "_openrouter_post",
        lambda p, k, t: {"error": {"message": "insufficient credit", "code": 402}},
    )
    with pytest.raises(mb.ModelBackendRefusalError):
        mb._run_openrouter("m", "p", timeout=5)


def test_run_model_stops_the_chain_on_a_refusal_instead_of_trying_the_next_backend(monkeypatch):
    calls = []

    def fake_runner(backend, model, prompt, **kwargs):
        calls.append(backend)
        raise mb.ModelBackendRefusalError(f"{backend}:{model} HTTP 402 (insufficient credit)")

    result = mb.run_model(mb.ROLE_CHAT_HELPERS, "p", backend="openrouter", fallbacks=["llamacpp"], _runner=fake_runner)
    assert calls == ["openrouter"]
    assert result.ok is False
    assert result.refused is True



def test_openrouter_truncated_completion_raises_instead_of_returning_partial_text(monkeypatch):
    monkeypatch.setattr(
        mb, "_openrouter_post",
        lambda p, k, t: _fake_response("this looks like a complete answer but isn'", finish_reason="length"),
    )
    with pytest.raises(mb.ModelBackendTruncatedError):
        mb._run_openrouter("m", "p", timeout=5)


def test_openrouter_truncated_completion_error_names_the_ceiling_used(monkeypatch):
    monkeypatch.setattr(
        mb, "_openrouter_post", lambda p, k, t: _fake_response("cut off", finish_reason="length")
    )
    with pytest.raises(mb.ModelBackendTruncatedError, match="max_tokens=500"):
        mb._run_openrouter("m", "p", timeout=5, max_tokens=500)


def test_openrouter_normal_stop_reason_is_not_treated_as_truncation(monkeypatch):
    monkeypatch.setattr(
        mb, "_openrouter_post", lambda p, k, t: _fake_response("a complete answer", finish_reason="stop")
    )
    assert mb._run_openrouter("m", "p", timeout=5) == "a complete answer"


def test_openrouter_a_caller_needing_more_room_must_override_or_fail_loudly(monkeypatch):

    def fake_post(payload, api_key, timeout):
        return _fake_response("A" * payload["max_tokens"], finish_reason="length")

    monkeypatch.setattr(mb, "_openrouter_post", fake_post)

    with pytest.raises(mb.ModelBackendTruncatedError):
        mb._run_openrouter("m", "long-form drafting prompt", timeout=5)

    seen = {}

    def fake_post_large(payload, api_key, timeout):
        seen.update(payload)
        return _fake_response("a shorter real answer", finish_reason="stop")

    monkeypatch.setattr(mb, "_openrouter_post", fake_post_large)
    result = mb._run_openrouter("m", "long-form drafting prompt", timeout=5, max_tokens=8000)
    assert result == "a shorter real answer"
    assert seen["max_tokens"] == 8000


def test_openrouter_captures_upstream_provider_and_generation_id(monkeypatch):
    body = _fake_response("ok", {"prompt_tokens": 1, "completion_tokens": 1})
    body["provider"] = "DeepInfra"
    body["id"] = "gen-abc123"
    monkeypatch.setattr(mb, "_openrouter_post", lambda p, k, t: body)
    usage: dict = {}
    mb._run_openrouter("m", "p", timeout=5, usage=usage)
    assert usage["upstream_provider"] == "DeepInfra"
    assert usage["generation_id"] == "gen-abc123"


def test_openrouter_response_meta_absent_fields_add_nothing():
    assert mb._openrouter_response_meta({"choices": []}) == {}
    assert mb._openrouter_response_meta(None) == {}
