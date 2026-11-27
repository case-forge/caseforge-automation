
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import model_backend as mb


@pytest.fixture(autouse=True)
def _no_probe(monkeypatch):
    monkeypatch.setattr(mb, "_llamacpp_probe", lambda host, timeout: None)


def test_llamacpp_in_registry():
    assert "llamacpp" in mb.BACKENDS
    registry = mb.model_registry.load_registry()
    assert mb.model_for_role(mb.ROLE_CHAT_HELPERS, backend="llamacpp") == registry["CASEFORGE_MODEL_LLAMACPP_SMALL"]
    assert mb.model_for_role(mb.ROLE_CASE_SUMMARY, backend="llamacpp") == registry["CASEFORGE_MODEL_LLAMACPP_LARGE"]


def test_llamacpp_is_not_a_default_or_auto_fallback():
    assert mb.DEFAULT_BACKEND != "llamacpp"
    assert "llamacpp" not in mb.fallback_chain()


def test_llamacpp_opt_in_only_when_named(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MODEL_BACKEND", "llamacpp")
    monkeypatch.delenv("CASEFORGE_MODEL_FALLBACKS", raising=False)
    assert mb.backend_order(mb.ROLE_CHAT_HELPERS) == ["llamacpp"]


def test_llamacpp_host_default_and_override(monkeypatch):
    monkeypatch.delenv("CASEFORGE_LLAMACPP_HOST", raising=False)
    assert mb._llamacpp_host() == mb.DEFAULT_LLAMACPP_HOST
    monkeypatch.setenv("CASEFORGE_LLAMACPP_HOST", "http://127.0.0.1:8080")
    assert mb._llamacpp_host() == "http://127.0.0.1:8080"


def test_llamacpp_build_command_refuses():
    with pytest.raises(ValueError):
        mb.build_command("llamacpp", "qwen3.6-35b-a3b", "prompt", "")


def _fake_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def test_llamacpp_thinking_off_for_low_reasoning(monkeypatch):
    seen = {}

    def fake_post(host, payload, timeout):
        seen.update(payload)
        return _fake_response("SERVICE")

    monkeypatch.setattr(mb, "_llamacpp_post", fake_post)
    out = mb._run_llamacpp("qwen3.6-35b-a3b", "classify this", timeout=30, reasoning="low")
    assert out == "SERVICE"
    assert seen["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["temperature"] == 0
    assert "tools" not in seen


def test_llamacpp_thinking_on_for_high_reasoning(monkeypatch):
    seen = {}

    def fake_post(host, payload, timeout):
        seen.update(payload)
        return _fake_response("done")

    monkeypatch.setattr(mb, "_llamacpp_post", fake_post)
    mb._run_llamacpp("qwen3.6-35b-a3b", "reason hard", timeout=30, reasoning="high")
    assert seen["chat_template_kwargs"] == {"enable_thinking": True}


def test_llamacpp_strips_whitespace_and_think_blocks(monkeypatch):
    monkeypatch.setattr(
        mb, "_llamacpp_post", lambda h, p, t: _fake_response("<think>hmm</think>  hello  ")
    )
    assert mb._run_llamacpp("m", "p", timeout=5) == "hello"


def test_llamacpp_empty_output_raises(monkeypatch):
    monkeypatch.setattr(mb, "_llamacpp_post", lambda h, p, t: _fake_response(""))
    with pytest.raises(mb.ModelBackendError):
        mb._run_llamacpp("m", "p", timeout=5)


def test_llamacpp_malformed_response_raises(monkeypatch):
    monkeypatch.setattr(mb, "_llamacpp_post", lambda h, p, t: {"choices": []})
    with pytest.raises(mb.ModelBackendError):
        mb._run_llamacpp("m", "p", timeout=5)


def test_llamacpp_probe_failure_raises(monkeypatch):
    def failing_probe(host, timeout):
        raise mb.ModelBackendError("unreachable")

    monkeypatch.setattr(mb, "_llamacpp_probe", failing_probe)
    with pytest.raises(mb.ModelBackendError):
        mb._run_llamacpp("m", "p", timeout=5)


def test_run_backend_routes_llamacpp(monkeypatch):
    monkeypatch.setattr(mb, "_llamacpp_post", lambda h, p, t: _fake_response("ok"))
    assert mb.run_backend("llamacpp", "qwen3.6-35b-a3b", "p", timeout=5) == "ok"
