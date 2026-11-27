#!/usr/bin/env python3
from __future__ import annotations

import urllib.error
import urllib.request


def probe(host: str, timeout: float) -> tuple[bool, str]:
    url = host.rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            ok = 200 <= resp.status < 300
            return ok, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, type(exc).__name__
