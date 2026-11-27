#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import contextvars
import os
import threading
from typing import Any, Iterator

import jwt

CF_ACCESS_JWT_HEADER = "Cf-Access-Jwt-Assertion"
TEAM_DOMAIN_ENV = "CASEFORGE_CF_ACCESS_TEAM_DOMAIN"
AUD_ENV = "CASEFORGE_CF_ACCESS_CLIENT_VIEWER_AUD"
LEEWAY_SECONDS = 30

_LOCK = threading.Lock()
_CLIENTS: dict[str, jwt.PyJWKClient] = {}
_REQUEST_ASSERTION: contextvars.ContextVar[str] = contextvars.ContextVar("vergil_access_assertion", default="")


@contextlib.contextmanager
def request_assertion(assertion: str | None) -> Iterator[None]:
    token = _REQUEST_ASSERTION.set(str(assertion or "").strip())
    try:
        yield
    finally:
        _REQUEST_ASSERTION.reset(token)


def current_assertion() -> str:
    return _REQUEST_ASSERTION.get()


class AccessIdentityError(PermissionError):
    pass


def _config() -> tuple[str, str]:
    team = os.environ.get(TEAM_DOMAIN_ENV, "").strip()
    aud = os.environ.get(AUD_ENV, "").strip()
    if not team or not aud:
        raise AccessIdentityError("Cloudflare Access is not configured on the hub, so no person can be verified.")
    return team, aud


def _jwks_client(team: str) -> jwt.PyJWKClient:
    with _LOCK:
        client = _CLIENTS.get(team)
        if client is None:
            client = jwt.PyJWKClient(f"https://{team}/cdn-cgi/access/certs", cache_keys=True, lifespan=300, timeout=5)
            _CLIENTS[team] = client
        return client


def signing_key(assertion: str, team: str) -> Any:
    return _jwks_client(team).get_signing_key_from_jwt(assertion).key


def verify(assertion: str | None) -> str:
    token = str(assertion or "").strip()
    if not token:
        raise AccessIdentityError("No Cloudflare Access identity came with the request.")
    team, aud = _config()
    try:
        key = signing_key(token, team)
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=aud,
            issuer=f"https://{team}",
            leeway=LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise AccessIdentityError(f"The Cloudflare Access identity did not verify ({type(exc).__name__}).") from exc
    except Exception as exc:
        raise AccessIdentityError(f"The Cloudflare Access identity could not be checked ({type(exc).__name__}).") from exc
    email = str(claims.get("email") or "").strip()
    if "@" not in email:
        raise AccessIdentityError("The Cloudflare Access identity carries no email.")
    return email.lower()
