from __future__ import annotations

import os
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def feedback_path() -> Path:
    root = os.getenv("CASEFORGE_TELEMETRY_ROOT", "").strip()
    return (Path(root) if root else (REPO_ROOT / "telemetry")) / "intern-qa-feedback.jsonl"


def record_feedback(
    *,
    verdict: str,
    answer_id: str | None = None,
    ts_of_answer: str | None = None,
    comment: str | None = None,
    remote_user: str | None = None,
    path: Path | None = None,
) -> dict:
    if not (answer_id or ts_of_answer):
        raise ValueError("answer_id or ts_of_answer is required")

    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "id": answer_id,
        "ts_of_answer": ts_of_answer,
        "verdict": verdict,
        "comment": comment,
        "remote_user": remote_user or None,
    }
    from graph_mail_safe_ops import _append_jsonl_locked

    _append_jsonl_locked(path if path is not None else feedback_path(), row)
    return row
