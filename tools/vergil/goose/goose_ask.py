from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any

from starlette.concurrency import iterate_in_threadpool

from vergil.goose import goose_client, vergil_identity


def _digest(value: object) -> str:
    try:
        text = json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        text = str(value)
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


_FREE_TEXT_ARGS = frozenset({"body", "text", "content", "message", "prompt", "prompt_summary", "question", "html"})
_SUMMARY_MAX_CHARS = 80


def _input_summary(arguments: object) -> dict:
    from documents import c8_protection

    if not isinstance(arguments, dict):
        return {}

    def clean(text: str) -> str:
        text = c8_protection.EMAIL_RE.sub(c8_protection.WITHHELD, text)
        text = c8_protection.PHONE_RE.sub(c8_protection.WITHHELD, text)
        text = c8_protection.POSTCODE_RE.sub(c8_protection.WITHHELD, text)
        return text if len(text) <= _SUMMARY_MAX_CHARS else text[:_SUMMARY_MAX_CHARS] + "..."

    out: dict = {}
    for key, value in arguments.items():
        name = str(key)
        if name.lower().startswith("c8_"):
            continue
        if isinstance(value, str):
            out[name] = f"[{len(value)} characters]" if name.lower() in _FREE_TEXT_ARGS else clean(value)
        elif isinstance(value, (bool, int, float)) or value is None:
            out[name] = value
        elif isinstance(value, (list, tuple)):
            out[name] = f"[{len(value)} item(s)]"
        else:
            out[name] = "[object]"
    return out


def _count_list(value: object) -> list:
    return [{} for _ in value] if isinstance(value, list) else []


def _result_summary(tool_name: str, content: object) -> list:
    if str(tool_name).split("__")[-1] != "retrieve_matter_context" or not isinstance(content, list):
        return []
    for block in content:
        if not (isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)):
            continue
        try:
            parsed = json.loads(block["text"])
        except ValueError:
            return []
        if not isinstance(parsed, dict) or not isinstance(parsed.get("sources_checked"), list):
            return []
        listing = parsed.get("graph_listing")
        safe = {
            "matter_id": parsed.get("matter_id") if isinstance(parsed.get("matter_id"), (str, int)) else None,
            "carried_over": parsed.get("carried_over") is True,
            "sources_checked": [str(x) for x in parsed["sources_checked"]],
            "gaps": [str(x) for x in parsed.get("gaps") or []],
            "sql_hits": _count_list(parsed.get("sql_hits")),
            "rag_hits": _count_list(parsed.get("rag_hits")),
            "graph_listing": {"value": _count_list(listing.get("value"))} if isinstance(listing, dict) else None,
        }
        return [{"type": "text", "text": json.dumps(safe)}]
    return []


def translate_goose_event(raw: dict) -> tuple[str, dict] | None:
    kind = raw.get("kind", "")
    tool_name = raw.get("tool_name", "")
    call_id = raw.get("call_id", "")

    if kind == "action":
        return ("tool_call", {"tool": tool_name, "input": _input_summary(raw.get("action", {})), "input_digest": _digest(raw.get("action", {})), "call_id": call_id})

    if kind == "observation":
        observation = raw.get("observation", {})
        if observation.get("is_error"):
            return ("tool_error", {"tool": tool_name, "call_id": call_id})
        return ("tool_result", {"tool": tool_name, "content": _result_summary(tool_name, observation.get("content", [])), "call_id": call_id})

    if kind == "message":
        return ("delta", {"text": vergil_identity.strip_em_dashes(raw.get("text", ""))})

    if kind == "run.done":
        return ("done", {})

    if kind == "run.error":
        return ("error", {"message": "Vergil backend unavailable"})

    return None


def stream_vergil_answer_goose(session_id: str) -> Iterator[tuple[str, dict]]:
    for raw_event in goose_client.stream_session_events(session_id):
        translated = translate_goose_event(raw_event)
        if translated is None:
            continue
        yield translated
        if translated[0] in ("done", "error"):
            return




def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


class TurnLimiter:

    def __init__(self, total: int | None = None, per_user: int | None = None) -> None:
        self._total = threading.BoundedSemaphore(total or _env_int("VERGIL_MAX_CONCURRENT_TURNS", 8))
        self._per_user_max = per_user or _env_int("VERGIL_MAX_TURNS_PER_USER", 2)
        self._lock = threading.Lock()
        self._per_user: dict[str, int] = {}

    def acquire(self, user: str) -> bool:
        key = user or ""
        with self._lock:
            if self._per_user.get(key, 0) >= self._per_user_max:
                return False
            if not self._total.acquire(blocking=False):
                return False
            self._per_user[key] = self._per_user.get(key, 0) + 1
        return True

    def release(self, user: str) -> None:
        key = user or ""
        with self._lock:
            count = self._per_user.get(key, 0)
            if count <= 0:
                return
            if count == 1:
                del self._per_user[key]
            else:
                self._per_user[key] = count - 1
            self._total.release()


TURN_LIMITER = TurnLimiter()




class TurnCanceller:

    def __init__(self, cancel: Callable[[str], Any] | None = None) -> None:
        self._cancel = cancel or goose_client.cancel_session
        self._lock = threading.Lock()
        self._session_id: str | None = None
        self._requested = False
        self._finished = False
        self._fired = False

    def bind(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._session_id = session_id
            fire = self._requested and not self._finished and not self._fired
            self._fired = self._fired or fire
        if fire:
            self._cancel(session_id)

    def cancel(self) -> None:
        with self._lock:
            self._requested = True
            fire = self._session_id is not None and not self._finished and not self._fired
            self._fired = self._fired or fire
            session_id = self._session_id
        if fire and session_id:
            self._cancel(session_id)

    def finish(self) -> None:
        with self._lock:
            self._finished = True

    @property
    def fired(self) -> bool:
        return self._fired


async def _watch_for_disconnect(receive: Callable[[], Awaitable[dict]], on_disconnect: Callable[[], None]) -> None:
    while True:
        message = await receive()
        if message.get("type") == "http.disconnect":
            on_disconnect()
            return


async def cancellable_stream(
    body: Iterator[Any],
    receive: Callable[[], Awaitable[dict]],
    canceller: TurnCanceller,
) -> AsyncIterator[Any]:
    watcher = asyncio.ensure_future(_watch_for_disconnect(receive, canceller.cancel))
    completed = False
    try:
        async for chunk in iterate_in_threadpool(body):
            yield chunk
        completed = True
        canceller.finish()
    finally:
        watcher.cancel()
        if not completed:
            canceller.cancel()
