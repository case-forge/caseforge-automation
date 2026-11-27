#!/usr/bin/env python3

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:(?:\+|00)\d[\d\s-]{8,}\d|\b0\d{9,}\b)")


def looks_unsafe(text: str) -> bool:
    return bool(_EMAIL_RE.search(text) or _PHONE_RE.search(text))


def redact_token(text: str, token: str) -> str:
    if not token:
        return text
    return str(text or "").replace(token, "<redacted>")
