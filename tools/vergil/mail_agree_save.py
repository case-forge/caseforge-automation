#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from vergil.primitives import REPO_ROOT

TIMEOUT_SECONDS = 150
SAVE_ROUTES = frozenset({"Client", "Court", "Counsel", "Complaints"})


def _run(job_id: str) -> dict[str, Any]:
    try:
        done = subprocess.run(
            [sys.executable, "-m", "tools.mail_intake.agree_save", "--job-id", job_id],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False,
        )
        line = next((ln for ln in reversed((done.stdout or "").splitlines()) if ln.startswith("{")), "")
        return json.loads(line) if line else {"filed": False, "status": "not_filed", "why": "the saver gave no answer"}
    except subprocess.TimeoutExpired:
        return {"filed": False, "status": "not_filed", "why": "saving took too long; nothing was queued"}
    except Exception as exc:
        return {"filed": False, "status": "not_filed", "why": f"the saver failed ({type(exc).__name__})"}


def _event(job_id: str, outcome: dict[str, Any], by: str, note: str = "") -> None:
    try:
        from vergil.background_jobs import agent_queue_module

        summary = f"Agree in the CRM: {outcome.get('status')}" + (f" ({outcome.get('why')})" if outcome.get("why") else "")
        details = {k: outcome.get(k) for k in ("filed", "status", "archive_job", "forced", "route") if k in outcome}
        if by:
            details["by"] = by
        if note:
            details["note"] = " ".join(str(note).split())[:300]
        agent_queue_module().record_event(job_id, "agree_save", summary[:300], details)
    except Exception:
        pass


def save(job_id: str, applied_route: str, *, by: str = "", note: str = "") -> dict[str, Any]:
    job_id = str(job_id or "").strip()
    if not job_id or not all(ch.isalnum() or ch in "-_" for ch in job_id):
        return {"filed": False, "status": "not_filed", "why": "no valid email to save"}
    if applied_route not in SAVE_ROUTES:
        return {"filed": False, "status": "not_filed", "why": f"{applied_route or 'that route'} is not filed to a client folder"}
    outcome = _run(job_id)
    _event(job_id, outcome, by, note)
    return outcome
