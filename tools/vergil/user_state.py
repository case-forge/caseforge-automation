from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from pathlib import Path
from typing import Mapping

from atomic_json import StateFileError, atomic_write_json, file_lock, read_json_strict

from vergil.primitives import (
    REPO_ROOT,
    SESSION_DIR,
    int_env,
    normalise_client_key,
    normalise_space,
    safe_upload_name,
    utc_now_iso,
)
from vergil.formatting import parse_iso_dt
from vergil.prompt_routing import vergil_chat_hash_for_audit


CLIENT_EXPOSURE_SINGLE_REQUEST_LIMIT = int_env("CASEFORGE_CHAT_CLIENT_EXPOSURE_SINGLE_LIMIT", 9, 1)
CLIENT_EXPOSURE_ROLLING_LIMIT = int_env("CASEFORGE_CHAT_CLIENT_EXPOSURE_ROLLING_LIMIT", 20, 1)
CLIENT_EXPOSURE_WINDOW_HOURS = int_env("CASEFORGE_CHAT_CLIENT_EXPOSURE_WINDOW_HOURS", 24, 1)
RISK_EVENTS_LOG = REPO_ROOT / "telemetry" / "caseforge-chat-risk-events.jsonl"

ADMIN_ROLE = "admin"
WORKER_ROLE = "worker"
TAILNET_ROLE = "tailnet"
MACHINE_ROLE = "machine"
UNLIMITED_ROLES = frozenset({ADMIN_ROLE, TAILNET_ROLE, MACHINE_ROLE})
ADMIN_ACTION = "admin_not_limited"
UNLIMITED_ACTIONS = {
    ADMIN_ROLE: ADMIN_ACTION,
    TAILNET_ROLE: "tailnet_not_limited",
    MACHINE_ROLE: "machine_not_limited",
}

WORKER_MODE_ENV = "CASEFORGE_CLIENT_EXPOSURE_WORKER_MODE"
WORKER_MODES = ("block", "log", "none")
DEFAULT_WORKER_MODE = "log"

log = logging.getLogger(__name__)
_invalid_worker_modes_logged: set[str] = set()


def is_guest(username: str | None) -> bool:
    del username
    return False


def can_auto_run_tools(username: str | None) -> bool:
    return not is_guest(username)


def session_file(username: str) -> Path:
    return SESSION_DIR / f"{username}.session_id"


def load_session(username: str) -> str | None:
    f = session_file(username)
    return f.read_text().strip() if f.exists() else None


def save_session(username: str, sid: str) -> None:
    session_file(username).write_text(sid)


def history_file(username: str) -> Path:
    return SESSION_DIR / f"{username}.history.json"


def load_history(username: str) -> list:
    f = history_file(username)
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(username: str, messages: list) -> None:
    try:
        history_file(username).write_text(
            json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def preferences_file(username: str) -> Path:
    return SESSION_DIR / f"{safe_upload_name(username or 'user')}.preferences.json"


def preference_value(raw: object, key: str, default: object) -> object:
    getter = getattr(raw, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except Exception:
            return default
    return default


def normalise_preferences(raw: object, username: str) -> dict:
    theme = str(preference_value(raw, "theme", "system") or "system").strip().lower()
    if theme not in {"system", "dark", "light"}:
        theme = "system"
    return {
        "theme": theme,
        "auto_approve": bool(preference_value(raw, "auto_approve", can_auto_run_tools(username))),
        "enter_sends": bool(preference_value(raw, "enter_sends", True)),
        "show_debug_details": bool(preference_value(raw, "show_debug_details", False)),
    }


def load_user_preferences(username: str) -> dict:
    path = preferences_file(username)
    if not path.exists():
        return normalise_preferences({}, username)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return normalise_preferences(payload if isinstance(payload, Mapping) else {}, username)
    except Exception:
        return normalise_preferences({}, username)


def save_user_preferences(username: str, values: Mapping) -> None:
    try:
        prefs = normalise_preferences(values, username)
        preferences_file(username).write_text(
            json.dumps(prefs, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass


def archive_dir(username: str) -> Path:
    d = SESSION_DIR / f"{username}-sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_archived_session(username: str, session_id: str) -> dict | None:
    path = archive_dir(username) / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def client_exposure_budget_path(username: str) -> Path:
    return SESSION_DIR / f"{safe_upload_name(username or 'user')}.exposure-budget.json"


def _record_budget_file_fault(username: str, fault: str) -> None:
    try:
        record_vergil_chat_risk_event(
            username,
            {"risky": True, "severity": "review", "categories": [fault], "matched_rules": [fault], "source": "exposure_budget_file"},
            action="logged",
            source="exposure_budget_file",
        )
    except Exception:
        pass


def load_client_exposure_budget(username: str) -> dict:
    path = client_exposure_budget_path(username)
    try:
        payload = read_json_strict(path, default={})
    except (StateFileError, OSError):
        _record_budget_file_fault(username, "exposure_budget_file_unreadable")
        return {}
    return payload if isinstance(payload, dict) else {}


def record_vergil_chat_risk_event(
    username: str,
    assessment: dict,
    *,
    action: str,
    source: str,
    attachment_count: int = 0,
    extra: dict | None = None,
) -> None:
    if not assessment.get("risky"):
        return
    payload = {
        "recorded_utc": utc_now_iso(),
        "event": "caseforge_chat_prompt_risk",
        "action": str(action or "logged"),
        "source": str(source or assessment.get("source") or ""),
        "severity": str(assessment.get("severity") or "review"),
        "categories": list(assessment.get("categories") or []),
        "matched_rules": list(assessment.get("matched_rules") or []),
        "estimated_client_count": int(assessment.get("estimated_client_count") or 0),
        "text_hash": str(assessment.get("text_hash") or ""),
        "text_chars": int(assessment.get("text_chars") or 0),
        "attachment_count": int(attachment_count or 0),
        "actor_hash": vergil_chat_hash_for_audit(str(username or "").strip().lower()),
    }
    extra_payload = extra if isinstance(extra, dict) else {}
    for key in (
        "request_unique_count",
        "request_total_count",
        "new_unique_count",
        "rolling_unique_count",
        "rolling_limit",
        "single_request_limit",
    ):
        if key in extra_payload:
            try:
                payload[key] = int(extra_payload.get(key) or 0)
            except (TypeError, ValueError):
                payload[key] = 0
    for key in ("window_start_utc", "window_end_utc", "rule", "role", "caller_source", "tailnet_login", "tailnet_node", "tailnet_ip"):
        value = str(extra_payload.get(key) or "").strip()
        if value:
            payload[key] = value
    if isinstance(extra_payload.get("matter_key_hashes"), list):
        payload["matter_key_hashes"] = [
            str(item)
            for item in extra_payload.get("matter_key_hashes", [])
            if re.fullmatch(r"[a-f0-9]{64}", str(item))
        ][:50]
    try:
        RISK_EVENTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with RISK_EVENTS_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass
    try:
        from telemetry_sqlite import record_jsonl_event

        record_jsonl_event("caseforge_chat_prompt_risk", "telemetry\\caseforge-chat-risk-events.jsonl", payload)
    except Exception:
        pass


def client_exposure_key_material(row: Mapping) -> str:
    matter_id = normalise_space(str(row.get("matter_id") or ""))
    if matter_id:
        return f"matter_id:{matter_id.lower()}"
    company_reference = normalise_space(str(row.get("company_reference") or ""))
    if company_reference:
        return f"company_reference:{company_reference.lower()}"
    canonical_name = normalise_space(str(row.get("client_name") or row.get("matter_name") or "")).lower()
    return f"name:{canonical_name}" if canonical_name else ""


def client_exposure_key_hashes(rows: list[dict]) -> list[str]:
    hashes: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        material = client_exposure_key_material(row)
        if not material:
            continue
        key_hash = vergil_chat_hash_for_audit(material)
        if key_hash in seen:
            continue
        seen.add(key_hash)
        hashes.append(key_hash)
    return hashes


def write_client_exposure_budget(username: str, payload: dict) -> None:
    try:
        atomic_write_json(client_exposure_budget_path(username), payload)
    except Exception:
        _record_budget_file_fault(username, "exposure_budget_file_unwritable")


def _caller_fields(caller: Mapping | None) -> dict:
    if not isinstance(caller, Mapping):
        return {}
    fields = {"caller_source": str(caller.get("source") or "")}
    for key in ("login", "node", "ip"):
        if caller.get(key):
            fields[f"tailnet_{key}"] = str(caller[key])
    return {k: v for k, v in fields.items() if v}


def _source_class(source: str) -> str:
    return "non_model" if source in NON_MODEL_EXPOSURE_SOURCES else "model"


def assess_client_exposure_budget(
    username: str,
    rows: list[dict],
    *,
    source: str,
    commit: bool = True,
    enforce: bool = True,
    role: str = "worker",
    caller: Mapping | None = None,
) -> dict:
    kwargs = {"source": source, "commit": commit, "enforce": enforce, "role": role, "caller": caller}
    try:
        lock = file_lock(client_exposure_budget_path(username))
        lock.__enter__()
    except Exception:
        return _assess_client_exposure_budget(username, rows, **kwargs)
    try:
        return _assess_client_exposure_budget(username, rows, **kwargs)
    finally:
        lock.__exit__(None, None, None)


def _assess_client_exposure_budget(
    username: str,
    rows: list[dict],
    *,
    source: str,
    commit: bool = True,
    enforce: bool = True,
    role: str = "worker",
    caller: Mapping | None = None,
) -> dict:
    role = role if role in UNLIMITED_ROLES else WORKER_ROLE
    unlimited = role in UNLIMITED_ROLES
    enforce = enforce and not unlimited
    caller_fields = _caller_fields(caller)
    key_hashes = client_exposure_key_hashes(rows)
    source_class = _source_class(source)
    now = dt.datetime.now(dt.timezone.utc)
    window_start = now - dt.timedelta(hours=CLIENT_EXPOSURE_WINDOW_HOURS)
    window_start_utc = window_start.isoformat().replace("+00:00", "Z")
    window_end_utc = now.isoformat().replace("+00:00", "Z")

    payload = load_client_exposure_budget(username)
    raw_events = payload.get("events") if isinstance(payload, dict) else []
    window_events: list[dict] = []
    existing_keys: set[str] = set()
    existing_keys_same_class: set[str] = set()
    if isinstance(raw_events, list):
        for event in raw_events:
            if not isinstance(event, dict):
                continue
            key_hash = str(event.get("key_hash") or "").strip()
            if not re.fullmatch(r"[a-f0-9]{64}", key_hash):
                continue
            seen_at = parse_iso_dt(str(event.get("seen_utc") or ""))
            if seen_at is None:
                continue
            if seen_at.tzinfo is None:
                seen_at = seen_at.replace(tzinfo=dt.timezone.utc)
            if seen_at >= window_start:
                event_class = str(event.get("source_class") or "non_model")
                kept = {
                    "seen_utc": seen_at.isoformat().replace("+00:00", "Z"),
                    "key_hash": key_hash,
                    "source_class": event_class,
                }
                event_role = event.get("role") if event.get("role") in UNLIMITED_ROLES else WORKER_ROLE
                if event_role != WORKER_ROLE:
                    kept["role"] = event_role
                if event.get("tailnet_node"):
                    kept["tailnet_node"] = str(event["tailnet_node"])
                window_events.append(kept)
                existing_keys.add(key_hash)
                if event_class == source_class and event_role == role:
                    existing_keys_same_class.add(key_hash)

    incoming_keys = set(key_hashes)
    new_keys = [key for key in key_hashes if key not in existing_keys]
    rolling_keys = existing_keys_same_class | incoming_keys
    categories: list[str] = []
    matched_rules: list[str] = []
    if len(key_hashes) > CLIENT_EXPOSURE_SINGLE_REQUEST_LIMIT:
        categories.append("client_exposure_budget_exceeded")
        matched_rules.append("single_request_client_exposure_limit")
    if len(rolling_keys) > CLIENT_EXPOSURE_ROLLING_LIMIT:
        categories.append("rolling_client_exposure_limit")
        matched_rules.append("rolling_24h_client_exposure_limit")

    blocked = bool(categories) and enforce

    assessment = {
        "risky": bool(categories),
        "severity": "high" if categories else "low",
        "block": blocked,
        "categories": categories,
        "matched_rules": matched_rules,
        "estimated_client_count": len(key_hashes),
        "source": source,
        "request_unique_count": len(key_hashes),
        "request_total_count": len([row for row in rows if isinstance(row, dict)]),
        "new_unique_count": len(new_keys),
        "rolling_unique_count": len(rolling_keys),
        "rolling_limit": CLIENT_EXPOSURE_ROLLING_LIMIT,
        "single_request_limit": CLIENT_EXPOSURE_SINGLE_REQUEST_LIMIT,
        "window_start_utc": window_start_utc,
        "window_end_utc": window_end_utc,
        "matter_key_hashes": key_hashes,
    }
    if categories:
        record_vergil_chat_risk_event(
            username,
            assessment,
            action=UNLIMITED_ACTIONS[role] if unlimited else ("blocked" if blocked else "threshold_crossed_not_enforced"),
            source=source,
            extra={
                **({"role": role} if unlimited else {}),
                **caller_fields,
                "rule": categories[0],
                "request_unique_count": assessment["request_unique_count"],
                "request_total_count": assessment["request_total_count"],
                "new_unique_count": assessment["new_unique_count"],
                "rolling_unique_count": assessment["rolling_unique_count"],
                "rolling_limit": assessment["rolling_limit"],
                "single_request_limit": assessment["single_request_limit"],
                "window_start_utc": window_start_utc,
                "window_end_utc": window_end_utc,
                "matter_key_hashes": key_hashes,
            },
        )
        if blocked:
            return assessment

    if commit and new_keys:
        for key_hash in new_keys:
            event = {
                "seen_utc": window_end_utc,
                "key_hash": key_hash,
                "source_class": source_class,
            }
            if unlimited:
                event["role"] = role
            if caller_fields.get("tailnet_node"):
                event["tailnet_node"] = caller_fields["tailnet_node"]
            window_events.append(event)
        write_client_exposure_budget(
            username,
            {
                "version": 1,
                "updated_utc": window_end_utc,
                "window_hours": CLIENT_EXPOSURE_WINDOW_HOURS,
                "events": window_events,
            },
        )
    return assessment


UNATTRIBUTED_BUDGET_IDENTITY = "__unattributed__"


def budget_identity(remote_user: str | None) -> str:
    name = (remote_user or "").strip()
    if name:
        return name
    from vergil import tailnet_identity

    caller = tailnet_identity.current_caller()
    return tailnet_identity.budget_identity_for(caller) if caller else UNATTRIBUTED_BUDGET_IDENTITY


MCP_REMOTE_USER_ENV = "VERGIL_REMOTE_USER"


def mcp_budget_identity() -> str:
    name = os.getenv(MCP_REMOTE_USER_ENV, "").strip()
    return name or UNATTRIBUTED_BUDGET_IDENTITY


NON_MODEL_EXPOSURE_SOURCES = frozenset({"clients_search"})


def blocked_by_rolling_window_only(categories: list) -> bool:
    categories = categories or []
    return (
        "rolling_client_exposure_limit" in categories
        and "client_exposure_budget_exceeded" not in categories
    )


def client_exposure_worker_mode() -> str:
    raw = os.getenv(WORKER_MODE_ENV, "").strip().lower()
    if not raw:
        return DEFAULT_WORKER_MODE
    if raw in WORKER_MODES:
        return raw
    if raw not in _invalid_worker_modes_logged:
        _invalid_worker_modes_logged.add(raw)
        log.warning("%s is not one of %s; using %s", WORKER_MODE_ENV, "/".join(WORKER_MODES), DEFAULT_WORKER_MODE)
    return DEFAULT_WORKER_MODE


def _machine_caller_for(username: str) -> dict | None:
    from vergil import tailnet_identity

    caller = tailnet_identity.current_caller()
    if caller and str(username or "").strip() == tailnet_identity.budget_identity_for(caller):
        return caller
    return None


def client_exposure_role(username: str) -> str:
    from vergil.runtime_control import is_env_admin

    try:
        machine = _machine_caller_for(username)
    except Exception:
        machine = None
    if machine:
        return TAILNET_ROLE if machine.get("role") == TAILNET_ROLE else MACHINE_ROLE
    name = str(username or "").strip().lower()
    if not name or name == UNATTRIBUTED_BUDGET_IDENTITY or not is_env_admin(name):
        return WORKER_ROLE
    try:
        from vergil import access_identity

        assertion = access_identity.current_assertion()
        if not assertion:
            return WORKER_ROLE
        email = access_identity.verify(assertion)
    except Exception:
        return WORKER_ROLE
    return ADMIN_ROLE if email == name else WORKER_ROLE


def enforce_client_exposure_budget(username: str, rows: list[dict], *, source: str) -> dict:
    if is_guest(username) or not rows:
        return {"block": False, "categories": [], "request_unique_count": 0}
    role = client_exposure_role(username)
    if role in UNLIMITED_ROLES:
        caller = _machine_caller_for(username) if role != ADMIN_ROLE else None
        return assess_client_exposure_budget(
            username, rows, source=source, commit=True, enforce=False, role=role, caller=caller
        )
    mode = client_exposure_worker_mode()
    if mode == "none":
        return {"block": False, "categories": [], "request_unique_count": 0}
    return assess_client_exposure_budget(username, rows, source=source, commit=True, enforce=mode == "block")


