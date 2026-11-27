from __future__ import annotations

import copy
import datetime as dt
import functools
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SESSION_DIR = Path.home() / ".caseforge-chat-sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)


def normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()

def prompt_lower(prompt: str) -> str:
    return normalise_space(prompt).lower()

def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def latest_json(pattern: str) -> tuple[Path | None, dict | None]:
    files = sorted((REPO_ROOT / "telemetry").glob(pattern))
    if not files:
        return None, None
    path = files[-1]
    return path, read_json(path)

def env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

def int_env(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(str(os.getenv(name, str(default))).strip()))
    except (TypeError, ValueError):
        return max(minimum, default)

def csv_env_set(name: str) -> set[str]:
    return {
        item.strip().lower()
        for item in str(os.getenv(name, "") or "").split(",")
        if item.strip()
    }

def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

def safe_upload_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", name or "upload")
    cleaned = cleaned.strip(" .") or "upload"
    return cleaned[:120]

def normalise_client_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def attempt_success(result: dict) -> bool:
    return bool(result.get("ok") and result.get("text_emitted"))

def submission_fingerprint(prompt: str, attachments: list[dict] | None = None) -> str:
    attachment_bits = [
        f"{str(item.get('name', '')).strip()}:{int(item.get('size', 0) or 0)}"
        for item in (attachments or [])
        if isinstance(item, dict)
    ]
    payload = json.dumps(
        {
            "prompt": str(prompt or "").strip(),
            "attachments": attachment_bits,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def latest_user_index(messages: list[dict]) -> int | None:
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].get("role") == "user":
            return idx
    return None


_F = TypeVar("_F", bound=Callable[..., Any])


def ttl_cache(seconds: float) -> Callable[[_F], _F]:

    def decorate(fn: _F) -> _F:
        store: dict[Any, tuple[float, Any]] = {}
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            with lock:
                hit = store.get(key)
            if hit is not None and (now - hit[0]) < seconds:
                return copy.deepcopy(hit[1])
            value = fn(*args, **kwargs)
            with lock:
                store[key] = (time.monotonic(), value)
            return copy.deepcopy(value)

        wrapper.cache_clear = store.clear
        return wrapper

    return decorate
