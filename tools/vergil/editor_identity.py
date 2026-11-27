#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

CLIENT_HEADER = "x-caseforge-client"
CLIENT_VIEWER = "client-viewer"
TAILNET_EDITOR = "tailnet"
ACTOR_FIELDS = ("by", "edited_by", "set_by", "created_by", "resolved_by")
MAX_EDITOR_LENGTH = 60


def _workers() -> tuple[str, ...]:
    try:
        import firm_profile

        return tuple(firm_profile.load_profile().workers)
    except Exception:
        return ()


def display_name(email: str, workers: Iterable[str] | None = None) -> str:
    email = " ".join(str(email or "").split())
    if not email:
        return ""
    first = re.split(r"[._+\-]", email.split("@", 1)[0], maxsplit=1)[0].lower()
    for worker in _workers() if workers is None else workers:
        if first and str(worker).strip().lower() == first:
            return str(worker).strip()
    return email[:MAX_EDITOR_LENGTH]


def resolve_editor(remote_user: str | None, *, via_client_viewer: bool, workers: Iterable[str] | None = None) -> str | None:
    email = str(remote_user or "").strip()
    if email:
        return display_name(email, workers)
    if via_client_viewer:
        return TAILNET_EDITOR
    return None


def _model_actor_fields(model: Any) -> tuple[str, ...]:
    fields = getattr(model, "model_fields", None)
    if not isinstance(fields, dict):
        return ()
    return tuple(name for name in ACTOR_FIELDS if name in fields)


def route_actor_fields(route: Any) -> tuple[str, ...]:
    dependant = getattr(route, "dependant", None)
    found: list[str] = []
    for param in getattr(dependant, "body_params", None) or []:
        annotation = getattr(param, "type_", None)
        if annotation is None:
            annotation = getattr(getattr(param, "field_info", None), "annotation", None)
        found.extend(f for f in _model_actor_fields(annotation) if f not in found)
    return tuple(found)


def rewrite_body(body: bytes, fields: Iterable[str], editor: str) -> bytes | None:
    try:
        payload = json.loads(body) if body else {}
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    for name in fields:
        payload[name] = editor
    return json.dumps(payload).encode("utf-8")


class EditorFromIdentity:

    def __init__(self, app: Any, routes: Callable[[], list[Any]]) -> None:
        self.app = app
        self._routes = routes
        self._fields: dict[int, tuple[str, ...]] = {}

    def _fields_for(self, scope: dict) -> tuple[str, ...]:
        from starlette.routing import Match

        for route in self._routes():
            matches = getattr(route, "matches", None)
            if matches is None:
                continue
            match, _ = matches(scope)
            if match == Match.FULL:
                key = id(route)
                if key not in self._fields:
                    self._fields[key] = route_actor_fields(route)
                return self._fields[key]
        return ()

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or scope.get("method") in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        editor = resolve_editor(
            headers.get("remote-user"),
            via_client_viewer=headers.get(CLIENT_HEADER, "").strip() == CLIENT_VIEWER,
        )
        if editor is None or "json" not in headers.get("content-type", ""):
            await self.app(scope, receive, send)
            return
        fields = self._fields_for(scope)
        if not fields:
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                await self.app(scope, _replay([message], receive), send)
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                break
        body = b"".join(chunks)
        rewritten = rewrite_body(body, fields, editor)
        if rewritten is not None:
            body = rewritten
            scope = dict(scope)
            scope["headers"] = [(k, v) for k, v in scope.get("headers") or [] if k.lower() != b"content-length"]
            scope["headers"].append((b"content-length", str(len(body)).encode("latin-1")))
        await self.app(scope, _replay([{"type": "http.request", "body": body, "more_body": False}], receive), send)


def _replay(messages: list[dict], receive: Callable) -> Callable:
    pending = list(messages)

    async def _receive() -> dict:
        if pending:
            return pending.pop(0)
        return await receive()

    return _receive
