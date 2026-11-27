from __future__ import annotations

import re

_UNSAFE = re.compile(r'[\x00-\x1f\x7f"\\;/<>|:*?\u2028\u2029]|[^\x20-\x7e]')


def content_disposition(disposition: str, filename: str, fallback: str = "download") -> str:
    cleaned = _UNSAFE.sub("", str(filename or "")).strip().strip(".")
    return f'{disposition}; filename="{cleaned or fallback}"'
