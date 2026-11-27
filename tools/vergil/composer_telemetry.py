from __future__ import annotations

import os
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

LARGE_PASTE_CHAR_THRESHOLD = 20_000


def large_paste_log_path() -> Path:
    root = os.getenv("CASEFORGE_TELEMETRY_ROOT", "").strip()
    return (Path(root) if root else (REPO_ROOT / "telemetry")) / "vergil-large-paste.jsonl"


def record_large_paste(*, char_count: int, remote_user: str | None, path: Path | None = None) -> dict | None:
    if char_count < LARGE_PASTE_CHAR_THRESHOLD:
        return None

    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "char_count": char_count,
        "remote_user": remote_user or None,
    }
    from graph_mail_safe_ops import _append_jsonl_locked

    _append_jsonl_locked(path if path is not None else large_paste_log_path(), row)
    return row
