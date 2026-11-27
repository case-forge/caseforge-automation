
from __future__ import annotations

import hmac
import logging
import urllib.parse
from typing import Any

SECRET_KEYS = frozenset({"clientState"})

SECRET_URL_KEYS = frozenset({"notificationUrl"})

REDACTED = "<redacted>"


def redact_secret_url(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    try:
        parts = urllib.parse.urlsplit(value)
    except ValueError:
        return REDACTED
    if not parts.scheme or not parts.netloc:
        return REDACTED
    return f"{parts.scheme}://{parts.netloc}/{REDACTED}"


def redact_webhook_secrets(payload: Any) -> Any:
    if isinstance(payload, dict):
        result: dict[Any, Any] = {}
        for key, value in payload.items():
            if key in SECRET_KEYS:
                result[key] = REDACTED
            elif key in SECRET_URL_KEYS:
                result[key] = redact_secret_url(value)
            else:
                result[key] = redact_webhook_secrets(value)
        return result
    if isinstance(payload, list):
        return [redact_webhook_secrets(item) for item in payload]
    return payload


redact_client_state = redact_webhook_secrets


def client_state_matches(received: Any, expected: Any, *, where: str = "webhook") -> bool:
    wanted = str(expected or "").strip()
    if not wanted:
        logging.getLogger(__name__).error("%s: client state not configured; refusing the notification", where)
        return False
    return hmac.compare_digest(str(received or "").strip().encode("utf-8"), wanted.encode("utf-8"))
