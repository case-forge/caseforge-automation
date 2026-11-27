#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import datetime as _dt
import functools
import hashlib
import inspect
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Sequence

try:
    import firm_profile
except ImportError:
    from tools import firm_profile

_log = logging.getLogger(__name__)


try:
    import model_registry
except ImportError:
    from tools import model_registry

ROLE_TIERS = model_registry.ROLE_TIERS
ROLES = model_registry.ROLES
ModelRoleError = model_registry.ModelRoleError
globals().update({n: getattr(model_registry, n) for n in dir(model_registry) if n.startswith("ROLE_") and n != "ROLE_TIERS"})

BACKENDS: tuple[str, ...] = ("llamacpp", "openrouter")

RETIRED_BACKENDS: dict[str, str] = {
    "claude": (
        "the 'claude' backend does not exist: casework model calls run on OpenRouter under ZDR, or on "
        "Anthropic's own API for anthropic/ roles, and never through the Claude Code CLI"
    ),
}


def _refuse_retired(name: str, where: str) -> None:
    reason = RETIRED_BACKENDS.get((name or "").strip().lower())
    if reason:
        raise ModelBackendError(f"{where}={name.strip()!r}: {reason}")

DEFAULT_BACKEND = "openrouter"
DEFAULT_TIMEOUT = 45.0
DEFAULT_LLAMACPP_HOST = firm_profile.load_profile().local_model_url
DEFAULT_LLAMACPP_CONNECT_TIMEOUT = 3.0

TRUTHY = {"1", "true", "yes", "on"}
REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}


class ModelBackendError(RuntimeError):
    pass


class ModelBackendRefusalError(ModelBackendError):
    pass


_COST_REFUSAL_RE = re.compile(
    r"\b(?:http|status|code|error)\W{0,3}402\b|\b402\W{0,3}payment required|requires more credits"
    r"|insufficient credit|add more credits|key limit exceeded|credit limit|credit balance is too low",
    re.IGNORECASE,
)


COST_REFUSAL_BLOCK_REASON = "cost_cap"


def is_cost_refusal_text(text: str) -> bool:
    return bool(_COST_REFUSAL_RE.search(str(text or "")))


class ModelBackendTruncatedError(ModelBackendError):
    pass


class ModelCallCancelled(Exception):

    def __init__(self, message: str = "model call cancelled", usage: Optional[dict] = None) -> None:
        super().__init__(message)
        self.usage: dict = dict(usage or {})


CancelToken = object


def _cancel_requested(cancel: Optional[CancelToken]) -> bool:
    if cancel is None:
        return False
    try:
        if hasattr(cancel, "is_set"):
            return bool(cancel.is_set())
        return bool(cancel())
    except Exception:
        return False


@dataclasses.dataclass
class ModelAttempt:
    backend: str
    model: str
    ok: bool
    elapsed_seconds: float
    error: str = ""
    refusal: bool = False
    cancelled: bool = False


@dataclasses.dataclass
class ModelResult:
    text: str
    ok: bool
    served_by: str = ""
    model: str = ""
    role: str = ""
    elapsed_seconds: float = 0.0
    attempts: list[ModelAttempt] = dataclasses.field(default_factory=list)
    usage: dict = dataclasses.field(default_factory=dict)
    cancelled: bool = False

    @property
    def refused(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].refusal


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def primary_backend() -> str:
    backend = _env("CASEFORGE_MODEL_BACKEND").lower() or DEFAULT_BACKEND
    _refuse_retired(backend, "CASEFORGE_MODEL_BACKEND")
    return backend if backend in BACKENDS else DEFAULT_BACKEND


def _role_backend(role: str) -> str:
    for suffix in (role, ROLE_TIERS.get(role, "")):
        if not suffix:
            continue
        override = _env(f"CASEFORGE_MODEL_BACKEND_{suffix.upper()}").lower()
        _refuse_retired(override, f"CASEFORGE_MODEL_BACKEND_{suffix.upper()}")
        if override in BACKENDS:
            return override
    return primary_backend()


def fallback_chain() -> list[str]:
    raw = _env("CASEFORGE_MODEL_FALLBACKS")
    if not raw:
        return []
    out: list[str] = []
    for part in raw.split(","):
        name = part.strip().lower()
        _refuse_retired(name, "CASEFORGE_MODEL_FALLBACKS")
        if name in BACKENDS and name not in out:
            out.append(name)
    return out


def backend_order(role: str, backend: Optional[str] = None, fallbacks: Optional[Sequence[str]] = None) -> list[str]:
    primary = (backend or _role_backend(role)).lower()
    _refuse_retired(primary, "backend")
    if primary not in BACKENDS:
        primary = DEFAULT_BACKEND
    for name in fallbacks or ():
        _refuse_retired(name, "fallbacks")
    chain = fallback_chain() if fallbacks is None else [b.lower() for b in fallbacks if b.lower() in BACKENDS]
    order = [primary]
    for name in chain:
        if name not in order:
            order.append(name)
    return order


def model_for_role(role: str, backend: Optional[str] = None) -> str:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; expected one of {ROLES}")
    active = _role_backend(role)
    backend = (backend or active).lower()
    _refuse_retired(backend, "backend")
    if backend not in BACKENDS:
        backend = DEFAULT_BACKEND
    return model_registry.resolve(role, backend, active=backend == active)[0]


def model_for(role: str) -> str:
    return model_for_role(role)


def _reasoning_for(role: str, reasoning: Optional[str]) -> str:
    value = (reasoning or "").strip().lower()
    if value in REASONING_EFFORTS:
        return value
    tier = ROLE_TIERS.get(role, model_registry.TIER_LARGE)
    for suffix in (role, tier):
        env_val = _env(f"CASEFORGE_MODEL_{suffix.upper()}_REASONING").lower()
        if env_val in REASONING_EFFORTS:
            return env_val
    return "high" if tier == model_registry.TIER_LARGE else "low"


def build_command(backend: str, model: str, prompt: str, reasoning: str) -> tuple[list[str], Optional[str]]:
    _refuse_retired(backend, "backend")
    if backend in BACKENDS or backend == "anthropic":
        raise ValueError(f"{backend} backend is HTTP-only; call run_backend, not build_command")
    raise ValueError(f"unknown backend {backend!r}")


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", text).strip()


def _llamacpp_connect_timeout() -> float:
    raw = _env("CASEFORGE_LLAMACPP_CONNECT_TIMEOUT")
    if not raw:
        return DEFAULT_LLAMACPP_CONNECT_TIMEOUT
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_LLAMACPP_CONNECT_TIMEOUT


def _llamacpp_host() -> str:
    return _env("CASEFORGE_LLAMACPP_HOST") or DEFAULT_LLAMACPP_HOST


def _llamacpp_probe(host: str, timeout: float) -> None:
    url = host.rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            resp.read(1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ModelBackendError(f"llamacpp host {host} unreachable (probe {timeout}s): {exc}") from exc


def probe_llamacpp_backend(timeout: float = 4.0) -> dict:
    host = _llamacpp_host()
    try:
        _llamacpp_probe(host, timeout)
        return {"reachable": True, "host": host}
    except ModelBackendError as exc:
        return {"reachable": False, "host": host, "error": str(exc)}


def _llamacpp_post(host: str, payload: dict, timeout: float) -> dict:
    url = host.rstrip("/") + "/v1/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _run_llamacpp(model: str, prompt: str, *, timeout: float, reasoning: str = "") -> str:
    think = reasoning in {"high", "xhigh"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": think},
    }
    host = _llamacpp_host()
    _llamacpp_probe(host, min(_llamacpp_connect_timeout(), timeout))
    try:
        body = _llamacpp_post(host, payload, timeout)
    except urllib.error.URLError as exc:
        raise ModelBackendError(f"llamacpp:{model} unreachable at {host}: {exc}") from exc
    except (TimeoutError, OSError) as exc:
        raise ModelBackendError(f"llamacpp:{model} request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ModelBackendError(f"llamacpp:{model} bad JSON response: {exc}") from exc
    try:
        content = body["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelBackendError(f"llamacpp:{model} malformed response: {exc}") from exc
    text = _strip_thinking(content)
    if not text:
        raise ModelBackendError(f"llamacpp:{model} returned empty output")
    return text


def _openrouter_base() -> str:
    return _env("CASEFORGE_OPENROUTER_BASE") or "https://openrouter.ai/api/v1"


def _openrouter_response_meta(body: dict) -> dict:
    if not isinstance(body, dict):
        return {}
    meta = {}
    if body.get("provider"):
        meta["upstream_provider"] = str(body["provider"])[:100]
    if body.get("id"):
        meta["generation_id"] = str(body["id"])[:100]
    return meta


def _openrouter_post(payload: dict, api_key: str, timeout: float) -> dict:
    url = _openrouter_base().rstrip("/") + "/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _openrouter_usage_dict(raw_usage: dict) -> dict:
    prompt_details = raw_usage.get("prompt_tokens_details") or {}
    return {
        "input_tokens": int(raw_usage.get("prompt_tokens") or 0),
        "output_tokens": int(raw_usage.get("completion_tokens") or 0),
        "cache_read_tokens": int(prompt_details.get("cached_tokens") or 0),
        "cache_creation_tokens": int(prompt_details.get("cache_write_tokens") or 0),
        "estimated_cost_usd": float(raw_usage.get("cost") or 0.0),
    }


def _openrouter_post_cancellable(payload: dict, api_key: str, timeout: float,
                                 cancel: CancelToken, observed: dict) -> dict:
    if _cancel_requested(cancel):
        raise ModelCallCancelled("cancelled before the request was sent")
    url = _openrouter_base().rstrip("/") + "/chat/completions"
    body = dict(payload)
    body["stream"] = True
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    done = threading.Event()

    def _watch() -> None:
        while not done.wait(0.1):
            if _cancel_requested(cancel):
                try:
                    resp.close()
                except Exception:
                    pass
                return

    watcher = threading.Thread(target=_watch, name="model-cancel-watch", daemon=True)
    watcher.start()
    parts: list[str] = []
    finish_reason = None
    meta: dict = {}
    try:
        while True:
            if _cancel_requested(cancel):
                raise ModelCallCancelled("cancelled mid-stream")
            try:
                raw = resp.readline()
            except (OSError, ValueError):
                if _cancel_requested(cancel):
                    raise ModelCallCancelled("cancelled mid-stream") from None
                raise
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else str(raw).strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(chunk, dict):
                continue
            if "error" in chunk:
                return {"error": chunk["error"]}
            meta.update(_openrouter_response_meta(chunk))
            observed.update(meta)
            if isinstance(chunk.get("usage"), dict):
                observed.update(_openrouter_usage_dict(chunk["usage"]))
            for choice in chunk.get("choices") or []:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    parts.append(str(delta["content"]))
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
    finally:
        done.set()
        try:
            resp.close()
        except Exception:
            pass
    result: dict = {
        "choices": [{"message": {"content": "".join(parts)}, "finish_reason": finish_reason}],
        "usage": {},
    }
    if "input_tokens" in observed:
        result["usage"] = {
            "prompt_tokens": observed.get("input_tokens", 0),
            "completion_tokens": observed.get("output_tokens", 0),
            "cost": observed.get("estimated_cost_usd", 0.0),
            "prompt_tokens_details": {
                "cached_tokens": observed.get("cache_read_tokens", 0),
                "cache_write_tokens": observed.get("cache_creation_tokens", 0),
            },
        }
    if meta.get("generation_id"):
        result["id"] = meta["generation_id"]
    if meta.get("upstream_provider"):
        result["provider"] = meta["upstream_provider"]
    return result


def vision_model() -> str:
    return model_registry.resolve(ROLE_VISION, "openrouter")[0]



DEFAULT_VISION_MAX_TOKENS = int(os.environ.get("CASEFORGE_VISION_MAX_TOKENS", "16000"))
VISION_TOKENS_PER_PAGE = int(os.environ.get("CASEFORGE_VISION_TOKENS_PER_PAGE", "1500"))

DEFAULT_TEXT_MAX_TOKENS = int(os.environ.get("CASEFORGE_TEXT_MAX_TOKENS", "2000"))


def vision_max_tokens_for_pages(pages: int) -> int:
    return max(2000, min(int(pages or 1) * VISION_TOKENS_PER_PAGE, DEFAULT_VISION_MAX_TOKENS))


def looks_degenerate(text: str, *, pages: int = 1, max_chars_per_page: int = 12000) -> tuple[bool, str]:
    body = str(text or "")
    if not body.strip():
        return False, ""
    per_page = len(body) / max(1, int(pages or 1))
    if per_page > max_chars_per_page:
        return True, f"{per_page:.0f} chars/page over {max_chars_per_page} limit"
    windows = [body[i : i + 60] for i in range(0, max(1, len(body) - 60), 60)]
    if len(windows) >= 20:
        distinct_ratio = len(set(windows)) / len(windows)
        if distinct_ratio < 0.35:
            return True, f"repetition: only {distinct_ratio:.0%} of 60-char windows distinct"
    return False, ""


def _sniff_image_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "image/gif"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def run_vision(image_bytes: bytes, prompt: str, *, model: str = "",
               timeout: float = 120.0, usage: Optional[dict] = None,
               max_tokens: Optional[int] = None) -> str:
    import base64

    api_key = _env("OPENROUTER_OCR_API_KEY")
    if not api_key:
        raise ModelBackendError("openrouter: OPENROUTER_OCR_API_KEY not set")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model or vision_model(),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:{_sniff_image_mime(image_bytes)};base64," + b64}},
        ]}],
        "temperature": 0,
        "max_tokens": int(max_tokens or DEFAULT_VISION_MAX_TOKENS),
        "provider": {"data_collection": "deny", "zdr": True},
        "usage": {"include": True},
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise ModelBackendError(f"openrouter vision call failed: {exc}") from exc

    if "error" in data:
        raise ModelBackendError(f"openrouter vision call refused: {str(data['error'])[:300]}")
    if usage is not None and isinstance(data.get("usage"), dict):
        usage.update(data["usage"])
    if usage is not None:
        usage.update(_openrouter_response_meta(data))
    return (data["choices"][0]["message"]["content"] or "").strip()


def _run_openrouter(model: str, prompt: str, *, timeout: float, reasoning: str = "",
                    usage: Optional[dict] = None, max_tokens: Optional[int] = None,
                    system_prompt: Optional[str] = None,
                    cancel: Optional[CancelToken] = None) -> str:
    api_key = _env("OPENROUTER_API_KEY")
    if not api_key:
        raise ModelBackendError("openrouter: OPENROUTER_API_KEY not set")
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "provider": {"data_collection": "deny", "zdr": True},
        "usage": {"include": True},
        "max_tokens": int(max_tokens or DEFAULT_TEXT_MAX_TOKENS),
    }
    observed: dict = {}
    try:
        if cancel is None:
            body = _openrouter_post(payload, api_key, timeout)
        else:
            body = _openrouter_post_cancellable(payload, api_key, timeout, cancel, observed)
    except ModelCallCancelled as exc:
        exc.usage = {**observed, **exc.usage}
        if usage is not None:
            usage.update(exc.usage)
        raise
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300] if hasattr(exc, "read") else str(exc)
        if exc.code == 402:
            raise ModelBackendRefusalError(f"openrouter:{model} HTTP 402 (insufficient credit): {detail}") from exc
        raise ModelBackendError(f"openrouter:{model} HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ModelBackendError(f"openrouter:{model} unreachable: {exc}") from exc
    except (TimeoutError, OSError) as exc:
        raise ModelBackendError(f"openrouter:{model} request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ModelBackendError(f"openrouter:{model} bad JSON response: {exc}") from exc
    if "error" in body:
        error_body = body["error"] if isinstance(body["error"], dict) else {}
        if error_body.get("code") == 402:
            raise ModelBackendRefusalError(f"openrouter:{model} refused (insufficient credit): {str(body['error'])[:300]}")
        raise ModelBackendError(f"openrouter:{model} refused: {str(body['error'])[:300]}")
    try:
        choice = body["choices"][0]
        content = choice["message"].get("content") or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelBackendError(f"openrouter:{model} malformed response: {exc}") from exc
    if choice.get("finish_reason") == "length":
        raise ModelBackendTruncatedError(
            f"openrouter:{model} truncated at max_tokens={payload['max_tokens']} "
            "(finish_reason=length) -- incomplete output, not returned to the caller"
        )
    if usage is not None:
        raw_usage = body.get("usage") or {}
        prompt_details = raw_usage.get("prompt_tokens_details") or {}
        usage.update({
            "input_tokens": int(raw_usage.get("prompt_tokens") or 0),
            "output_tokens": int(raw_usage.get("completion_tokens") or 0),
            "cache_read_tokens": int(prompt_details.get("cached_tokens") or 0),
            "cache_creation_tokens": int(prompt_details.get("cache_write_tokens") or 0),
            "estimated_cost_usd": float(raw_usage.get("cost") or 0.0),
            **_openrouter_response_meta(body),
        })
    text = _strip_thinking(content)
    if not text:
        raise ModelBackendError(f"openrouter:{model} returned empty output")
    return text


ANTHROPIC_KEY_ENV = "ANTHROPIC_API_KEY"
ANTHROPIC_DIRECT_ENV = "CASEFORGE_ANTHROPIC_DIRECT"

_ANTHROPIC_MODELS_PATH = Path(__file__).resolve().parent.parent / "runtime-data" / "anthropic-models.json"


@functools.lru_cache(maxsize=1)
def _anthropic_models() -> dict[str, dict]:
    try:
        models = json.loads(_ANTHROPIC_MODELS_PATH.read_text(encoding="utf-8")).get("models")
    except (OSError, ValueError):
        return {}
    return {str(name): dict(row) for name, row in models.items() if isinstance(row, dict)} if isinstance(models, dict) else {}


def anthropic_model_id(openrouter_id: str) -> str:
    text = str(openrouter_id or "").strip()
    if not text.lower().startswith("anthropic/"):
        return ""
    return text.split("/", 1)[1].strip().lower().replace(".", "-")


def anthropic_direct_enabled() -> bool:
    return bool(_env(ANTHROPIC_KEY_ENV)) and _env(ANTHROPIC_DIRECT_ENV).lower() in {"1", "true", "yes", "on"}


def anthropic_direct_model(openrouter_id: str) -> str:
    if not anthropic_direct_enabled():
        return ""
    model = anthropic_model_id(openrouter_id)
    return model if model in _anthropic_models() else ""


def anthropic_cost_usd(model: str, usage: dict) -> float:
    row = _anthropic_models().get(model)
    if row is None:
        return 0.0
    fresh = int(usage.get("input_tokens") or 0)
    cache_read = int(usage.get("cache_read_tokens") or 0)
    cache_write = int(usage.get("cache_creation_tokens") or 0)
    output = int(usage.get("output_tokens") or 0)
    rates = row
    long_prompt = row.get("long_prompt")
    if isinstance(long_prompt, dict) and fresh + cache_read + cache_write > int(long_prompt.get("over_tokens") or 0):
        rates = long_prompt
    price_in = float(rates.get("input") or 0.0)
    total = (fresh * price_in + cache_write * price_in * 1.25 + cache_read * float(rates.get("cache_read") or 0.0)
             + output * float(rates.get("output") or 0.0))
    return total / 1_000_000


@functools.lru_cache(maxsize=8)
def _anthropic_client(api_key: str, timeout: float):
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=1)


def _anthropic_call(request: dict, api_key: str, timeout: float):
    import anthropic

    client = _anthropic_client(api_key, timeout)
    model = request.get("model", "")
    try:
        with client.messages.stream(**request) as stream:
            return stream.get_final_message()
    except anthropic.BadRequestError as exc:
        detail = str(exc)[:300]
        if is_cost_refusal_text(detail):
            raise ModelBackendRefusalError(f"anthropic:{model} refused (insufficient credit): {detail}") from exc
        raise ModelBackendError(f"anthropic:{model} HTTP 400: {detail}") from exc
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
        raise ModelBackendError(f"anthropic:{model} HTTP {exc.status_code}: the key was refused") from exc
    except anthropic.RateLimitError as exc:
        raise ModelBackendError(f"anthropic:{model} HTTP 429 (rate limited): {str(exc)[:200]}") from exc
    except anthropic.APIStatusError as exc:
        raise ModelBackendError(f"anthropic:{model} HTTP {exc.status_code}: {str(exc)[:300]}") from exc
    except anthropic.APIConnectionError as exc:
        raise ModelBackendError(f"anthropic:{model} unreachable or timed out: {exc}") from exc


def _run_anthropic(model: str, prompt: str, *, timeout: float, reasoning: str = "",
                   usage: Optional[dict] = None, max_tokens: Optional[int] = None,
                   system_prompt: Optional[str] = None) -> str:
    api_key = _env(ANTHROPIC_KEY_ENV)
    if not api_key:
        raise ModelBackendError(f"anthropic: {ANTHROPIC_KEY_ENV} not set")
    row = _anthropic_models().get(model)
    if row is None:
        raise ModelBackendError(f"anthropic:{model} has no entry in anthropic-models.json, so it is not run direct")
    request: dict = {
        "model": model,
        "max_tokens": int(max_tokens or DEFAULT_TEXT_MAX_TOKENS),
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        request["system"] = system_prompt
    if reasoning in REASONING_EFFORTS and row.get("effort"):
        request["output_config"] = {"effort": reasoning}
    if reasoning == "low" and row.get("thinking_off"):
        request["thinking"] = {"type": "disabled"}
    message = _anthropic_call(request, api_key, timeout)
    stop_reason = str(getattr(message, "stop_reason", "") or "")
    if usage is not None:
        raw = getattr(message, "usage", None)
        counts = {
            "input_tokens": int(getattr(raw, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(raw, "output_tokens", 0) or 0),
            "cache_read_tokens": int(getattr(raw, "cache_read_input_tokens", 0) or 0),
            "cache_creation_tokens": int(getattr(raw, "cache_creation_input_tokens", 0) or 0),
        }
        usage.update(counts)
        usage["estimated_cost_usd"] = anthropic_cost_usd(model, counts)
        usage["upstream_provider"] = "anthropic"
        if getattr(message, "id", ""):
            usage["generation_id"] = str(message.id)[:100]
    if stop_reason == "max_tokens":
        raise ModelBackendTruncatedError(
            f"anthropic:{model} truncated at max_tokens={request['max_tokens']} -- incomplete output, "
            "not returned to the caller (thinking counts toward max_tokens: pass a larger value)"
        )
    if stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None) or "unspecified"
        raise ModelBackendError(f"anthropic:{model} declined the request (category: {category})")
    text = _strip_thinking(
        "".join(str(getattr(block, "text", "") or "") for block in (getattr(message, "content", None) or [])
                if getattr(block, "type", "") == "text")
    )
    if not text:
        raise ModelBackendError(f"anthropic:{model} returned empty output")
    return text


def run_backend(
    backend: str,
    model: str,
    prompt: str,
    *,
    timeout: float,
    reasoning: str = "",
    usage: Optional[dict] = None,
    max_tokens: Optional[int] = None,
    system_prompt: Optional[str] = None,
    cancel: Optional[CancelToken] = None,
) -> str:
    if cancel is not None and _cancel_requested(cancel):
        raise ModelCallCancelled("cancelled before the call started")
    if backend == "llamacpp":
        return _run_llamacpp(model, prompt, timeout=timeout, reasoning=reasoning)
    if backend == "openrouter":
        extra = {"cancel": cancel} if cancel is not None else {}
        return _run_openrouter(model, prompt, timeout=timeout, reasoning=reasoning, usage=usage,
                               max_tokens=max_tokens, system_prompt=system_prompt, **extra)
    if backend == "anthropic":
        return _run_anthropic(model, prompt, timeout=timeout, reasoning=reasoning, usage=usage,
                              max_tokens=max_tokens, system_prompt=system_prompt)
    _refuse_retired(backend, "backend")
    raise ModelBackendError(f"unknown backend {backend!r}")


def _accepts_usage_kwarg(runner: Callable[..., str]) -> bool:
    try:
        return "usage" in inspect.signature(runner).parameters
    except (TypeError, ValueError):
        return False


def _accepts_max_tokens_kwarg(runner: Callable[..., str]) -> bool:
    try:
        return "max_tokens" in inspect.signature(runner).parameters
    except (TypeError, ValueError):
        return False


def _accepts_system_prompt_kwarg(runner: Callable[..., str]) -> bool:
    try:
        return "system_prompt" in inspect.signature(runner).parameters
    except (TypeError, ValueError):
        return False


def _accepts_cancel_kwarg(runner: Callable[..., str]) -> bool:
    try:
        return "cancel" in inspect.signature(runner).parameters
    except (TypeError, ValueError):
        return False


DAILY_SPEND_CAP_ENV = "CASEFORGE_MODEL_DAILY_SPEND_CAP_USD"
DEFAULT_DAILY_SPEND_CAP_USD = 4.00
METERED_BACKENDS = frozenset({"openrouter", "anthropic"})
DAILY_SPEND_CAP_ERROR = "daily_spend_cap"
_MICRO = 1_000_000

ANTHROPIC_DAILY_CAP_ENV = "CASEFORGE_ANTHROPIC_DAILY_SPEND_CAP_USD"
DEFAULT_ANTHROPIC_DAILY_CAP_USD = 10.00
ANTHROPIC_TOTAL_CAP_ENV = "CASEFORGE_ANTHROPIC_TOTAL_SPEND_CAP_USD"
DEFAULT_ANTHROPIC_TOTAL_CAP_USD = 90.00
ANTHROPIC_TOTAL_SPEND_KEY = "model_spend_micro_usd:anthropic:total"


def _cap_from_env(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value != value or value == float("inf"):
        return default
    return value


def daily_spend_cap_usd(backend: str = "openrouter") -> float:
    if backend == "anthropic":
        return _cap_from_env(ANTHROPIC_DAILY_CAP_ENV, DEFAULT_ANTHROPIC_DAILY_CAP_USD)
    return _cap_from_env(DAILY_SPEND_CAP_ENV, DEFAULT_DAILY_SPEND_CAP_USD)


def anthropic_total_cap_usd() -> float:
    return _cap_from_env(ANTHROPIC_TOTAL_CAP_ENV, DEFAULT_ANTHROPIC_TOTAL_CAP_USD)


def _utc_day() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def _daily_spend_key(backend: str = "openrouter") -> str:
    prefix = "model_spend_micro_usd:" if backend == "openrouter" else f"model_spend_micro_usd:{backend}:"
    return prefix + _utc_day()


def _ops_db():
    try:
        import ops_db
    except ImportError:
        from tools import ops_db
    return ops_db


def _daily_spend_allowed(backend: str) -> bool:
    if backend not in METERED_BACKENDS:
        return True
    if backend == "anthropic" and not _anthropic_total_allowed():
        return False
    cap = daily_spend_cap_usd(backend)
    if cap <= 0:
        return True
    try:
        ops_db = _ops_db()
        spent_micro = ops_db.bump_counter(_daily_spend_key(backend), amount=0)
    except Exception:
        return True
    if spent_micro < round(cap * _MICRO):
        return True
    alert_key = "model_spend_cap_alerted:" + ("" if backend == "openrouter" else f"{backend}:") + _utc_day()
    try:
        first_refusal = ops_db.bump_counter(alert_key) == 1
    except Exception:
        first_refusal = False
    if first_refusal:
        spent = spent_micro / _MICRO
        _log.error(
            "%s spend cap of $%.2f reached for today ($%.4f spent); its model calls are refused until tomorrow",
            backend, cap, spent,
        )
        if backend == "openrouter":
            _alert_daily_cap(cap, spent)
        else:
            _alert_daily_cap(cap, spent, backend)
    return False


def _anthropic_total_allowed() -> bool:
    cap = anthropic_total_cap_usd()
    if cap <= 0:
        return True
    try:
        ops_db = _ops_db()
        spent_micro = ops_db.bump_counter(ANTHROPIC_TOTAL_SPEND_KEY, amount=0)
    except Exception:
        return True
    if spent_micro < round(cap * _MICRO):
        return True
    try:
        first_refusal = ops_db.bump_counter("model_spend_cap_alerted:anthropic:total") == 1
    except Exception:
        first_refusal = False
    if first_refusal:
        spent = spent_micro / _MICRO
        _log.error("anthropic total spend cap of $%.2f reached ($%.4f spent); direct Claude calls are refused", cap, spent)
        _alert_total_cap(cap, spent)
    return False


def _record_spend(backend: str, usage: dict) -> None:
    if backend not in METERED_BACKENDS:
        return
    try:
        micro = round(float((usage or {}).get("estimated_cost_usd") or 0.0) * _MICRO)
    except (TypeError, ValueError, OverflowError):
        return
    if micro <= 0:
        return
    try:
        _ops_db().bump_counter(_daily_spend_key(backend), amount=micro)
        if backend == "anthropic":
            _ops_db().bump_counter(ANTHROPIC_TOTAL_SPEND_KEY, amount=micro)
    except Exception:
        pass


def _send_alert(text: str) -> None:
    try:
        try:
            from monitoring import telegram_secretary_alert
        except ImportError:
            from tools.monitoring import telegram_secretary_alert
        telegram_secretary_alert.send_secretary_alert(text)
    except Exception:
        pass


def _alert_daily_cap(cap: float, spent: float, backend: str = "openrouter") -> None:
    env = ANTHROPIC_DAILY_CAP_ENV if backend == "anthropic" else DAILY_SPEND_CAP_ENV
    label = "direct Anthropic" if backend == "anthropic" else "metered"
    _send_alert(
        f"Model spend cap reached: ${spent:.2f} spent on {label} model calls today (cap ${cap:.2f}). "
        f"Further {label} calls are refused until tomorrow UTC (or raise {env}). "
        "Check for a loop or a backlog."
    )


def _alert_total_cap(cap: float, spent: float) -> None:
    _send_alert(
        f"Anthropic API credit nearly spent: ${spent:.2f} used against a ${cap:.2f} cap. Direct Claude calls "
        f"are now refused. Top up the account, then raise {ANTHROPIC_TOTAL_CAP_ENV}."
    )


def _evidence_digest(evidence: str) -> str:
    day = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    return hashlib.sha256(f"{day}\n{evidence}".encode("utf-8")).hexdigest()


def review_is_unchanged(state_path: str, evidence: str) -> bool:
    try:
        with open(state_path, encoding="utf-8") as handle:
            return handle.read().strip() == _evidence_digest(evidence)
    except OSError:
        return False


def remember_review(state_path: str, evidence: str) -> None:
    try:
        with open(state_path, "w", encoding="utf-8") as handle:
            handle.write(_evidence_digest(evidence) + "\n")
    except OSError:
        pass


def run_model(
    role: str,
    prompt: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    reasoning: Optional[str] = None,
    model: Optional[str] = None,
    backend: Optional[str] = None,
    fallbacks: Optional[Sequence[str]] = None,
    telemetry: bool = True,
    request_id: str = "",
    route_reason: str = "",
    max_tokens: Optional[int] = None,
    system_prompt: Optional[str] = None,
    cancel: Optional[CancelToken] = None,
    _runner: Optional[Callable[..., str]] = None,
) -> ModelResult:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; expected one of {ROLES}")
    runner = _runner or run_backend
    started = time.monotonic()
    attempts: list[ModelAttempt] = []

    if model:
        chain = [(backend or _role_backend(role)).lower()]
        _refuse_retired(chain[0], "backend")
        if chain[0] not in BACKENDS:
            chain = [DEFAULT_BACKEND]
    else:
        chain = backend_order(role, backend=backend, fallbacks=fallbacks)

    if reasoning is None:
        reasoning_effort = _reasoning_for(role, None)
    else:
        cleaned = reasoning.strip().lower()
        reasoning_effort = cleaned if cleaned in REASONING_EFFORTS else ""

    result = ModelResult(text="", ok=False, role=role)
    was_cancelled = False
    cancelled_usage: dict = {}
    for chain_backend in chain:
        be = chain_backend
        model_id = model or model_for_role(role, backend=be)
        if be == "openrouter":
            direct_model = anthropic_direct_model(model_id)
            if direct_model:
                be, model_id = "anthropic", direct_model
        attempt_started = time.monotonic()
        if not _daily_spend_allowed(be):
            attempts.append(
                ModelAttempt(
                    backend=be, model=model_id, ok=False, elapsed_seconds=0.0,
                    error=DAILY_SPEND_CAP_ERROR, refusal=True,
                )
            )
            continue
        attempt_usage: dict = {}
        runner_kwargs: dict = {"timeout": timeout, "reasoning": reasoning_effort}
        if _accepts_usage_kwarg(runner):
            runner_kwargs["usage"] = attempt_usage
        if max_tokens is not None and _accepts_max_tokens_kwarg(runner):
            runner_kwargs["max_tokens"] = max_tokens
        if system_prompt is not None and _accepts_system_prompt_kwarg(runner):
            runner_kwargs["system_prompt"] = system_prompt
        if cancel is not None and _accepts_cancel_kwarg(runner):
            runner_kwargs["cancel"] = cancel
        try:
            text = runner(be, model_id, prompt, **runner_kwargs)
            _record_spend(be, attempt_usage)
            elapsed = time.monotonic() - attempt_started
            attempts.append(ModelAttempt(backend=be, model=model_id, ok=True, elapsed_seconds=elapsed))
            result = ModelResult(
                text=text,
                ok=True,
                served_by=be,
                model=model_id,
                role=role,
                elapsed_seconds=time.monotonic() - started,
                attempts=attempts,
                usage=attempt_usage,
            )
            break
        except ModelCallCancelled as exc:
            elapsed = time.monotonic() - attempt_started
            attempt_usage.update(exc.usage)
            _record_spend(be, attempt_usage)
            attempts.append(
                ModelAttempt(backend=be, model=model_id, ok=False, elapsed_seconds=elapsed,
                             error="cancelled", cancelled=True)
            )
            cancelled_usage = attempt_usage
            was_cancelled = True
            break
        except ModelBackendError as exc:
            elapsed = time.monotonic() - attempt_started
            refusal = isinstance(exc, ModelBackendRefusalError)
            attempts.append(
                ModelAttempt(backend=be, model=model_id, ok=False, elapsed_seconds=elapsed, error=str(exc)[:300], refusal=refusal)
            )
            if refusal:
                break

    if not result.ok:
        result = ModelResult(
            text="",
            ok=False,
            served_by="",
            model="",
            role=role,
            elapsed_seconds=time.monotonic() - started,
            attempts=attempts,
            usage=cancelled_usage if was_cancelled else {},
            cancelled=was_cancelled,
        )

    if telemetry:
        _emit_telemetry(result, prompt=prompt, request_id=request_id, route_reason=route_reason)
    return result


def run_text(role: str, prompt: str, **kwargs) -> str:
    return run_model(role, prompt, **kwargs).text


def run_single_shot(
    role: str,
    prompt: str,
    *,
    reasoning: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
    route_reason: str = "",
) -> str:
    return run_text(role, prompt, reasoning=reasoning, timeout=timeout, route_reason=route_reason)


def _emit_telemetry(result: ModelResult, *, prompt: str, request_id: str, route_reason: str) -> None:
    try:
        import telemetry_sqlite
    except Exception:
        try:
            from tools import telemetry_sqlite
        except Exception:
            return
    final_state = "completed" if result.ok else ("cancelled" if result.cancelled else "failed")
    usage = result.usage if isinstance(result.usage, dict) else {}
    payload = {
        "request_id": request_id,
        "selected_model": result.model,
        "provider": result.served_by or "none",
        "route_label": f"deterministic:{ROLE_TIERS.get(result.role, '')}:{result.role}",
        "route_reason": route_reason or f"served_by={result.served_by or 'none'}; attempts={len(result.attempts)}",
        "final_state": final_state,
        "prompt_chars": len(prompt or ""),
        "prompt_preview": prompt or "",
        "response_chars": len(result.text or ""),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "cache_read_tokens": int(usage.get("cache_read_tokens") or 0),
        "cache_creation_tokens": int(usage.get("cache_creation_tokens") or 0),
        "estimated_cost_usd": float(usage.get("estimated_cost_usd") or 0.0),
        "upstream_provider": str(usage.get("upstream_provider") or ""),
        "generation_id": str(usage.get("generation_id") or ""),
        "elapsed_seconds": round(result.elapsed_seconds, 4),
        "served_by": result.served_by,
        "attempts": [dataclasses.asdict(a) for a in result.attempts],
    }
    try:
        telemetry_sqlite.record_model_context_event(payload)
    except Exception:
        pass


__all__ = [
    "ROLES",
    "ROLE_TIERS",
    "ModelRoleError",
    "model_for",
    "vision_model",
    "BACKENDS",
    "ModelBackendError",
    "ModelCallCancelled",
    "ModelAttempt",
    "ModelResult",
    "primary_backend",
    "fallback_chain",
    "backend_order",
    "model_for_role",
    "build_command",
    "probe_llamacpp_backend",
    "run_backend",
    "run_model",
    "run_text",
    "run_single_shot",
]
