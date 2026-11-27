import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import model_backend as mb


@pytest.fixture(autouse=True)
def _clean_model_env(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("CASEFORGE_MODEL"):
            monkeypatch.delenv(key, raising=False)


def test_primary_backend_defaults_to_openrouter(monkeypatch):
    assert mb.primary_backend() == "openrouter"
    assert mb.DEFAULT_BACKEND == "openrouter"


def test_primary_backend_honours_env(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_BACKEND", "llamacpp")
    assert mb.primary_backend() == "llamacpp"


def test_removed_backends_degrade_to_default(monkeypatch):
    for gone in ("codex", "copilot", "cursor", "agy"):
        monkeypatch.setenv("CASEFORGE_MODEL_BACKEND", gone)
        assert mb.primary_backend() == "openrouter"
        assert gone not in mb.BACKENDS


def test_unknown_backend_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_BACKEND", "nonsense")
    assert mb.primary_backend() == "openrouter"


def test_there_is_no_claude_backend():
    assert "claude" not in mb.BACKENDS
    assert "claude" in mb.RETIRED_BACKENDS


def test_naming_the_claude_backend_raises_a_clear_error(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_BACKEND", "claude")
    with pytest.raises(mb.ModelBackendError, match="claude"):
        mb.primary_backend()
    with pytest.raises(mb.ModelBackendError, match="claude"):
        mb.run_model(mb.ROLE_CHAT_HELPERS, "p", telemetry=False, _runner=lambda *a, **k: "x")


@pytest.mark.parametrize("name", ["CASEFORGE_MODEL_BACKEND_MAIL_TRIAGE", "CASEFORGE_MODEL_BACKEND_SMALL"])
def test_a_role_or_tier_backend_override_naming_claude_raises(monkeypatch, name):
    monkeypatch.setenv(name, "claude")
    with pytest.raises(mb.ModelBackendError, match="claude"):
        mb.backend_order(mb.ROLE_MAIL_TRIAGE)


def test_a_fallback_chain_naming_claude_raises(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_FALLBACKS", "llamacpp,claude")
    with pytest.raises(mb.ModelBackendError, match="claude"):
        mb.backend_order(mb.ROLE_CHAT_HELPERS)


def test_an_explicit_claude_backend_argument_raises(monkeypatch):
    with pytest.raises(mb.ModelBackendError, match="claude"):
        mb.run_model(mb.ROLE_CHAT_HELPERS, "p", backend="claude", telemetry=False, _runner=lambda *a, **k: "x")
    with pytest.raises(mb.ModelBackendError, match="claude"):
        mb.run_model(mb.ROLE_CHAT_HELPERS, "p", backend="openrouter", fallbacks=["claude"], telemetry=False, _runner=lambda *a, **k: "x")
    with pytest.raises(mb.ModelBackendError, match="claude"):
        mb.model_for_role(mb.ROLE_CHAT_HELPERS, backend="claude")
    with pytest.raises(mb.ModelBackendError, match="claude"):
        mb.run_backend("claude", "m", "p", timeout=5)
    with pytest.raises(mb.ModelBackendError, match="claude"):
        mb.build_command("claude", "m", "p", "")


def test_backend_order_dedups_primary_out_of_chain(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_FALLBACKS", "copilot,openrouter,llamacpp")
    assert mb.backend_order(mb.ROLE_CHAT_HELPERS) == ["openrouter", "llamacpp"]


def test_backend_order_no_fallbacks(monkeypatch):
    assert mb.backend_order(mb.ROLE_CASE_SUMMARY) == ["openrouter"]


def test_per_role_backend_override(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_BACKEND_SMALL", "llamacpp")
    assert mb.backend_order(mb.ROLE_CHAT_HELPERS)[0] == "llamacpp"
    assert mb.backend_order(mb.ROLE_CASE_SUMMARY)[0] == "openrouter"


def test_model_for_role_registry_defaults():
    registry = mb.model_registry.load_registry()
    assert mb.model_for_role(mb.ROLE_CHAT_HELPERS) == registry["CASEFORGE_MODEL_CHAT_HELPERS"]
    assert mb.model_for_role(mb.ROLE_CASE_SUMMARY, backend="llamacpp") == registry["CASEFORGE_MODEL_LLAMACPP_LARGE"]


def test_generic_role_override_applies_only_to_active_backend(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_CASE_SUMMARY", "some/override-id")
    assert mb.model_for_role(mb.ROLE_CASE_SUMMARY, backend="openrouter") == "some/override-id"
    assert mb.model_for_role(mb.ROLE_CASE_SUMMARY, backend="llamacpp") == mb.model_registry.load_registry()["CASEFORGE_MODEL_LLAMACPP_LARGE"]


def test_per_backend_role_override(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_LLAMACPP_SMALL", "local-small")
    assert mb.model_for_role(mb.ROLE_CHAT_HELPERS, backend="llamacpp") == "local-small"


def test_unknown_role_raises():
    with pytest.raises(ValueError):
        mb.model_for_role("medium")


def test_build_command_unknown_backend_raises():
    with pytest.raises(ValueError):
        mb.build_command("bedrock", "x", "y", "")


def test_run_model_success_on_primary(monkeypatch):
    calls = []

    def fake(backend, model, prompt, *, timeout, reasoning):
        calls.append((backend, model))
        return "OK"

    res = mb.run_model(mb.ROLE_CHAT_HELPERS, "p", telemetry=False, _runner=fake)
    assert res.ok and res.text == "OK"
    assert res.served_by == "openrouter"
    assert res.model == mb.model_for_role(mb.ROLE_CHAT_HELPERS, backend="openrouter")
    assert len(calls) == 1


def test_run_model_walks_fallback_chain(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_FALLBACKS", "copilot,llamacpp")
    seen = []

    def fake(backend, model, prompt, *, timeout, reasoning):
        seen.append(backend)
        if backend == "openrouter":
            raise mb.ModelBackendError("429 rate limited")
        return "FROM_LLAMACPP"

    res = mb.run_model(mb.ROLE_CASE_SUMMARY, "p", telemetry=False, _runner=fake)
    assert res.ok and res.text == "FROM_LLAMACPP"
    assert res.served_by == "llamacpp"
    assert seen == ["openrouter", "llamacpp"]
    assert [a.ok for a in res.attempts] == [False, True]


def test_run_model_all_fail_returns_not_ok(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_FALLBACKS", "llamacpp")

    def fake(*a, **k):
        raise mb.ModelBackendError("down")

    res = mb.run_model(mb.ROLE_CHAT_HELPERS, "p", telemetry=False, _runner=fake)
    assert not res.ok
    assert res.text == ""
    assert res.served_by == ""
    assert len(res.attempts) == 2


def test_explicit_model_pins_and_disables_fallback(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_FALLBACKS", "llamacpp")
    seen = []

    def fake(backend, model, prompt, *, timeout, reasoning):
        seen.append((backend, model))
        raise mb.ModelBackendError("nope")

    res = mb.run_model(mb.ROLE_CASE_SUMMARY, "p", model="some/pinned-id", telemetry=False, _runner=fake)
    assert not res.ok
    assert seen == [("openrouter", "some/pinned-id")]


def test_run_text_returns_empty_on_failure(monkeypatch):
    def fake(*a, **k):
        raise mb.ModelBackendError("x")

    assert mb.run_text(mb.ROLE_CHAT_HELPERS, "p", telemetry=False, _runner=fake) == ""


def test_run_model_explicit_empty_reasoning_passes_no_effort(monkeypatch):
    seen = {}

    def fake(backend, model, prompt, *, timeout, reasoning):
        seen["reasoning"] = reasoning
        return "OK"

    mb.run_model(mb.ROLE_CASE_SUMMARY, "p", reasoning="", telemetry=False, _runner=fake)
    assert seen["reasoning"] == ""


def test_run_model_explicit_reasoning_wins(monkeypatch):
    seen = {}

    def fake(backend, model, prompt, *, timeout, reasoning):
        seen["reasoning"] = reasoning
        return "OK"

    mb.run_model(mb.ROLE_CHAT_HELPERS, "p", reasoning="high", telemetry=False, _runner=fake)
    assert seen["reasoning"] == "high"


def test_run_model_none_reasoning_uses_role_default(monkeypatch):
    seen = {}

    def fake(backend, model, prompt, *, timeout, reasoning):
        seen["reasoning"] = reasoning
        return "OK"

    mb.run_model(mb.ROLE_CASE_SUMMARY, "p", telemetry=False, _runner=fake)
    assert seen["reasoning"] == "high"


def test_run_single_shot_resolves_the_role_model_on_the_active_backend(monkeypatch):
    seen = {}

    def fake_run_backend(backend, model, prompt, *, timeout, reasoning=""):
        seen.update(backend=backend, model=model, reasoning=reasoning)
        return "ok"

    monkeypatch.setattr(mb, "run_backend", fake_run_backend)
    monkeypatch.setattr(mb, "_emit_telemetry", lambda *a, **k: None)

    out = mb.run_single_shot(mb.ROLE_CHAT_HELPERS, "p", reasoning="medium")
    assert out == "ok"
    assert seen["backend"] == "openrouter"
    assert seen["model"] == mb.model_registry.load_registry()["CASEFORGE_MODEL_CHAT_HELPERS"]
    assert seen["reasoning"] == "medium"


def test_run_single_shot_respects_a_backend_override(monkeypatch):
    seen = {}

    def fake_run_backend(backend, model, prompt, *, timeout, reasoning=""):
        seen.update(backend=backend, model=model)
        return "ok"

    monkeypatch.setenv("CASEFORGE_MODEL_BACKEND", "llamacpp")
    monkeypatch.delenv("CASEFORGE_MODEL_FALLBACKS", raising=False)
    monkeypatch.setattr(mb, "run_backend", fake_run_backend)
    monkeypatch.setattr(mb, "_emit_telemetry", lambda *a, **k: None)

    out = mb.run_single_shot(mb.ROLE_CASE_SUMMARY, "p", reasoning="medium")
    assert out == "ok"
    assert seen["backend"] == "llamacpp"
    assert seen["model"] == mb.model_registry.load_registry()["CASEFORGE_MODEL_LLAMACPP_LARGE"]


def test_telemetry_records_real_fields(monkeypatch):
    captured = {}

    import telemetry_sqlite

    monkeypatch.setattr(telemetry_sqlite, "record_model_context_event", lambda payload: captured.update(payload) or "evt")

    def fake(backend, model, prompt, *, timeout, reasoning):
        return "answer"

    mb.run_model(mb.ROLE_CASE_SUMMARY, "the prompt", _runner=fake, request_id="req1")
    assert captured["provider"] == "openrouter"
    assert captured["selected_model"] == mb.model_registry.load_registry()["CASEFORGE_MODEL_CASE_SUMMARY"]
    assert captured["final_state"] == "completed"
    assert captured["route_label"] == "deterministic:large:case_summary"
    assert captured["prompt_chars"] == len("the prompt")
    assert captured["response_chars"] == len("answer")
    assert captured["served_by"] == "openrouter"
    assert "prompt" not in captured or captured.get("prompt") != "the prompt"
    assert captured["request_id"] == "req1"


def test_telemetry_records_real_tokens_and_cost(monkeypatch):
    captured: dict = {}
    import telemetry_sqlite

    monkeypatch.setattr(telemetry_sqlite, "record_model_context_event",
                        lambda payload: captured.update(payload) or "evt")

    def fake(backend, model, prompt, *, timeout, reasoning, usage=None):
        usage.update(input_tokens=10, output_tokens=40, cache_read_tokens=11609,
                     cache_creation_tokens=3815, estimated_cost_usd=0.0090009)
        return "the answer"

    result = mb.run_model(mb.ROLE_CHAT_HELPERS, "the prompt", route_reason="test", _runner=fake)

    assert result.ok
    assert result.text == "the answer"
    assert captured["input_tokens"] == 10
    assert captured["output_tokens"] == 40
    assert captured["cache_read_tokens"] == 11609
    assert captured["cache_creation_tokens"] == 3815
    assert captured["estimated_cost_usd"] == pytest.approx(0.0090009)


def test_injected_runner_without_usage_kwarg_still_works(monkeypatch):
    def fake(backend, model, prompt, *, timeout, reasoning):
        return "answer"

    result = mb.run_model(mb.ROLE_CHAT_HELPERS, "p", _runner=fake)
    assert result.ok
    assert result.text == "answer"
    assert result.usage == {}
