from __future__ import annotations

import os
from typing import Any

TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}
REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}


def small_model_label() -> str:
    override = os.getenv("CASEFORGE_CHAT_SMALL_MODEL") or os.getenv("CASEFORGE_CHAT_NANO_MODEL") or os.getenv("CASEFORGE_CHAT_SMALL_ROUTER_MODEL")
    if override:
        return override
    try:
        import model_backend

        return model_backend.model_for_role(model_backend.ROLE_CHAT_HELPERS)
    except Exception:
        return ""



def _flag_enabled(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in TRUTHY:
        return True
    if value in FALSY:
        return False
    return default


def _small_model_enabled() -> bool:
    if "CASEFORGE_CHAT_ENABLE_SMALL_MODEL" in os.environ:
        return _flag_enabled("CASEFORGE_CHAT_ENABLE_SMALL_MODEL", True)
    return _flag_enabled("CASEFORGE_CHAT_ENABLE_NANO", True)


def _small_model_timeout(timeout: float | None) -> float:
    if timeout and timeout > 0:
        return float(timeout)
    raw = os.getenv("CASEFORGE_CHAT_SMALL_MODEL_TIMEOUT", "30").strip()
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 30.0


def _normalise_reasoning(value: str | None, default: str = "medium") -> str:
    reasoning = str(value or "").strip().lower()
    if reasoning in REASONING_EFFORTS:
        return reasoning
    return default if default in REASONING_EFFORTS else "medium"


def _small_model_reasoning(reasoning: str | None = None, default: str = "medium") -> str:
    global_override = os.getenv("CASEFORGE_CHAT_SMALL_MODEL_REASONING", "").strip().lower()
    if global_override in REASONING_EFFORTS:
        return global_override
    return _normalise_reasoning(reasoning, default)


def _task_reasoning(env_name: str, default: str) -> str:
    return _small_model_reasoning(os.getenv(env_name, default), default)


def _unified_backend_text(prompt: str, *, timeout: float, reasoning: str) -> str | None:
    try:
        import model_backend
    except Exception:
        return None
    result = model_backend.run_text(
        model_backend.ROLE_CHAT_HELPERS,
        prompt,
        timeout=timeout,
        reasoning=reasoning,
        route_reason="caseforge-chat:small",
    )
    return result or ""


def _small_model_text(
    prompt: str,
    *,
    max_output_tokens: int,
    timeout: float | None = None,
    model: str | None = None,
    reasoning: str | None = None,
) -> str:
    if not _small_model_enabled():
        return ""
    actual_timeout = _small_model_timeout(timeout)
    actual_reasoning = _small_model_reasoning(reasoning)
    del max_output_tokens, model
    unified = _unified_backend_text(prompt, timeout=actual_timeout, reasoning=actual_reasoning)
    return unified or ""


def _extract_response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return " ".join(chunks)
