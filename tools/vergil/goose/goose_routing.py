from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

DEESCALATION_CLEAN_TURNS = 3

_GUARD_EXCLUDED_CATEGORIES = frozenset({"S5", "S6"})

_CLARIFY_MESSAGES = (
    "That was flagged as an unsafe question by an automated check. Try rephrasing it.",
    "Still flagged as an unsafe question. Try different wording, or ask a colleague to check it if this keeps happening.",
)


@dataclass
class ConversationSafetyState:
    poisoned: bool = False
    consecutive_clean_turns: int = 0
    clarify_attempts: int = 0
    clarify_history: list[str] = field(default_factory=list)
    flagged_turns: list[str] = field(default_factory=list)


@dataclass
class RoutingDecision:
    action: str
    reason: str
    clarify_text: Optional[str] = None
    guard_category: Optional[str] = None


def classify_safety(text: str, *, prior_context: Optional[list[str]] = None):
    from vergil.goose.safety_classifier import classify_safety as _classify_safety

    return _classify_safety(text, prior_context=prior_context)


def decide_route(
    message: str,
    *,
    state: ConversationSafetyState,
    prior_messages: Optional[list[str]] = None,
) -> RoutingDecision:
    effective_prior_context = None
    if state.poisoned:
        effective_prior_context = (
            prior_messages if prior_messages is not None else list(state.flagged_turns)
        )

    try:
        guard_result = classify_safety(message, prior_context=effective_prior_context)
    except Exception:
        guard_result = None

    guard_unsafe = bool(
        guard_result is not None
        and guard_result.ok
        and guard_result.verdict == "unsafe"
        and guard_result.category not in _GUARD_EXCLUDED_CATEGORIES
    )

    guard_category = guard_result.category if guard_result is not None else None

    if guard_unsafe:
        state.poisoned = True
        state.consecutive_clean_turns = 0
        state.flagged_turns.append(message)
        state.clarify_attempts += 1
        clarify_text = generate_clarify_message(previous_texts=state.clarify_history)
        state.clarify_history.append(clarify_text)
        return RoutingDecision(
            action="clarify", reason="guard_unsafe", clarify_text=clarify_text,
            guard_category=guard_category,
        )

    if state.poisoned:
        state.consecutive_clean_turns += 1
        if state.consecutive_clean_turns >= DEESCALATION_CLEAN_TURNS:
            state.poisoned = False
            state.clarify_attempts = 0
            state.clarify_history = []

    guard_answered = guard_result is not None and guard_result.ok
    if not guard_answered:
        reason = "guard_unavailable"
    elif getattr(guard_result, "fell_back", False):
        reason = "safety_clear_fallback"
    else:
        reason = "safety_clear"
    return RoutingDecision(action="goose", reason=reason, guard_category=guard_category)


def generate_clarify_message(*, previous_texts: Optional[list[str]] = None) -> str:
    index = min(len(previous_texts or []), len(_CLARIFY_MESSAGES) - 1)
    return _CLARIFY_MESSAGES[index]



def routing_log_path() -> Path:
    root = os.getenv("CASEFORGE_TELEMETRY_ROOT", "").strip()
    return (Path(root) if root else (REPO_ROOT / "telemetry")) / "goose-routing-decisions.jsonl"


def log_routing_decision(
    *,
    action: str,
    reason: str,
    poisoned: bool,
    clarify_attempts: int,
    remote_user: Optional[str],
    consecutive_clean_turns: int = 0,
    guard_category: Optional[str] = None,
    path: Optional[Path] = None,
) -> dict:
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "action": action,
        "reason": reason,
        "poisoned": poisoned,
        "clarify_attempts": clarify_attempts,
        "remote_user": remote_user or None,
        "consecutive_clean_turns": consecutive_clean_turns,
        "guard_category": guard_category,
    }
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from graph_mail_safe_ops import _append_jsonl_locked

    _append_jsonl_locked(path if path is not None else routing_log_path(), row)
    return row


GUARD_BLOCK_TEXT_MAX_CHARS = 2000
GUARD_BLOCK_RETENTION_DAYS = 30


def _guard_block_retention_days() -> int:
    try:
        days = int(os.getenv("CASEFORGE_GUARD_BLOCK_RETENTION_DAYS", "").strip() or GUARD_BLOCK_RETENTION_DAYS)
    except ValueError:
        days = GUARD_BLOCK_RETENTION_DAYS
    return max(1, days)


def prune_guard_blocks(path: Optional[Path] = None, *, now: Optional[float] = None, retention_days: Optional[int] = None) -> int:
    target = path if path is not None else guard_block_log_path()
    if not target.exists():
        return 0
    days = retention_days if retention_days is not None else _guard_block_retention_days()
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime((now if now is not None else time.time()) - days * 86400))

    def _ts(line: str) -> str:
        try:
            return str(json.loads(line).get("ts") or "")
        except (ValueError, AttributeError):
            return ""

    with open(target, encoding="utf-8") as fh:
        first = fh.readline()
    if first and _ts(first) >= cutoff:
        return 0
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from graph_mail_safe_ops import _acquire_lock, _release_lock

    lock = _acquire_lock(target.with_suffix(target.suffix + ".lock"))
    try:
        with open(target, encoding="utf-8") as fh:
            lines = fh.readlines()
        kept = [line for line in lines if _ts(line) >= cutoff]
        if len(kept) == len(lines):
            return 0
        tmp = target.with_suffix(target.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.writelines(kept)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
        return len(lines) - len(kept)
    finally:
        _release_lock(lock)


def guard_block_log_path() -> Path:
    root = os.getenv("CASEFORGE_TELEMETRY_ROOT", "").strip()
    return (Path(root) if root else (REPO_ROOT / "telemetry")) / "goose-guard-blocks.jsonl"


def log_guard_block(
    *,
    message: str,
    action: str,
    remote_user: Optional[str],
    matter_id: Optional[str] = None,
    path: Optional[Path] = None,
) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import model_backend as mb
    from graph_mail_safe_ops import _append_jsonl_locked

    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "action": action,
        "guard_model": mb.model_for_role(mb.ROLE_SAFETY_GUARD, backend="openrouter"),
        "remote_user": remote_user or None,
        "matter_id": matter_id or None,
        "text": (message or "")[:GUARD_BLOCK_TEXT_MAX_CHARS],
    }
    target = path if path is not None else guard_block_log_path()
    _append_jsonl_locked(target, row)
    try:
        prune_guard_blocks(target)
    except OSError:
        pass
    return row


def probing_contradiction_log_path() -> Path:
    root = os.getenv("CASEFORGE_TELEMETRY_ROOT", "").strip()
    return (Path(root) if root else (REPO_ROOT / "telemetry")) / "goose-probing-contradictions.jsonl"


def log_probing_contradiction(
    *,
    contradiction: str,
    remote_user: Optional[str],
    guard_category: Optional[str] = None,
    path: Optional[Path] = None,
) -> dict:
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "contradiction": contradiction,
        "remote_user": remote_user or None,
        "guard_category": guard_category,
    }
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from graph_mail_safe_ops import _append_jsonl_locked

    _append_jsonl_locked(path if path is not None else probing_contradiction_log_path(), row)
    return row
