from __future__ import annotations

from vergil.primitives import REPO_ROOT, utc_now_iso

ROUTER_LOG = REPO_ROOT / "telemetry" / "caseforge-chat-router.jsonl"
SUBMIT_EVENTS_LOG = REPO_ROOT / "telemetry" / "caseforge-chat-submit-events.jsonl"


def append_router_log(payload: dict) -> None:
    try:
        from graph_mail_safe_ops import _append_jsonl_locked

        _append_jsonl_locked(ROUTER_LOG, dict(payload))
    except Exception:
        pass


def append_submit_event(event_type: str, payload: dict | None = None) -> None:
    try:
        from graph_mail_safe_ops import _append_jsonl_locked

        clean = dict(payload or {})
        clean.pop("prompt", None)
        clean.pop("content", None)
        event = {
            "timestamp": utc_now_iso(),
            "event": str(event_type or "").strip(),
            **clean,
        }
        _append_jsonl_locked(SUBMIT_EVENTS_LOG, event)
    except Exception:
        pass
