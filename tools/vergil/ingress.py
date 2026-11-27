from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from typing import Any

from fastapi.responses import JSONResponse

DEFAULT_MAX_BODY_BYTES = 1024 * 1024

PATH_BODY_CAPS: dict[str, int] = {}

PATH_TOKEN_ENV: dict[str, str] = {
    "/monitor/box-stats": "CASEFORGE_BOX_STATS_TOKEN",
    "/monitor/box-extras": "CASEFORGE_BOX_STATS_TOKEN",
}


class BodyTooLarge(Exception):
    pass


def _header(scope: dict, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return ""


def bearer_from_scope(scope: dict) -> str | None:
    scheme, _, credential = _header(scope, b"authorization").partition(" ")
    if scheme.lower() != "bearer" or not credential.strip():
        return None
    return credential.strip()


class IngressGuard:
    def __init__(
        self,
        app: Any,
        expected_token: Callable[[], str],
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        path_caps: dict[str, int] | None = None,
    ) -> None:
        self.app = app
        self.expected_token = expected_token
        self.max_body_bytes = max_body_bytes
        self.path_caps = PATH_BODY_CAPS if path_caps is None else path_caps

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token_env = PATH_TOKEN_ENV.get(scope.get("path", ""))
        expected = os.getenv(token_env, "").strip() if token_env else self.expected_token()
        if not expected:
            await JSONResponse({"detail": "API token not configured"}, status_code=503)(scope, receive, send)
            return
        presented = bearer_from_scope(scope)
        if presented is None:
            await JSONResponse(
                {"detail": "Not authenticated"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )(scope, receive, send)
            return
        if not secrets.compare_digest(presented.encode(), expected.encode()):
            await JSONResponse({"detail": "Invalid token"}, status_code=401)(scope, receive, send)
            return

        limit = self.path_caps.get(scope.get("path", ""), self.max_body_bytes)
        declared = _header(scope, b"content-length")
        if declared.isdigit() and int(declared) > limit:
            await JSONResponse({"detail": "body too large"}, status_code=413)(scope, receive, send)
            return

        seen = 0
        started = False

        async def capped() -> dict:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise BodyTooLarge
            return message

        async def tracking_send(message: dict) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, capped, tracking_send)
        except BodyTooLarge:
            if not started:
                await JSONResponse({"detail": "body too large"}, status_code=413)(scope, receive, send)
        except BaseException as exc:
            if seen > limit and not started and _is_body_too_large(exc):
                await JSONResponse({"detail": "body too large"}, status_code=413)(scope, receive, send)
                return
            raise


def _is_body_too_large(exc: BaseException) -> bool:
    if isinstance(exc, BodyTooLarge):
        return True
    return any(_is_body_too_large(inner) for inner in getattr(exc, "exceptions", ()))
