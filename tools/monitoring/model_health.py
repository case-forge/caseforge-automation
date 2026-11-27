#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Mapping


HEALTH_SCHEMA_VERSION = "caseforge.model-health.v1"
ACTIVE_STATES = {"available", "unknown"}
FAILURE_STATES = {
    "rate_limited",
    "quota_exhausted",
    "deprecated_not_found",
    "auth_failure",
    "timeout",
    "cli_missing",
    "unavailable",
}

PROVIDER_FAMILIES = {
    "claude": {"claude", "claude_sonnet", "claude_demo"},
    "codex": {"codex", "codex_mini", "codex_demo"},
}
PROVIDER_ISSUE_TTL = dt.timedelta(hours=6)


def utc_now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_future(value: str, *, now: dt.datetime | None = None) -> bool:
    parsed = parse_iso(value)
    if parsed is None:
        return False
    return parsed > (now or dt.datetime.now(dt.timezone.utc))


def _normalise_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (headers or {}).items()}


def parse_rate_limit_headers(headers: Mapping[str, Any] | None, text: str = "") -> dict[str, str]:
    normalised = _normalise_headers(headers)
    result: dict[str, str] = {}
    for key in (
        "x-ratelimit-remaining-requests",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "retry-after",
    ):
        if key in normalised:
            result[key] = normalised[key]

    lower_text = str(text or "")
    for key in (
        "x-ratelimit-remaining-requests",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "retry-after",
    ):
        if key in result:
            continue
        match = re.search(rf"{re.escape(key)}\s*[:=]\s*([^\s,;]+)", lower_text, flags=re.I)
        if match:
            result[key] = match.group(1)
    return result


def _status_from_error(text: str, returncode: int = 0, *, timed_out: bool = False) -> tuple[str, str]:
    lower = str(text or "").lower()
    if timed_out:
        return "timeout", "Provider timed out."
    if not lower and returncode == 0:
        return "available", "Last call completed."
    if "not found on path" in lower or "no such file or directory" in lower:
        return "cli_missing", "CLI binary is missing."
    if "model_not_found" in lower or "model not found" in lower or "unknown model" in lower:
        return "deprecated_not_found", "Configured model was not found."
    if "does not exist" in lower and "model" in lower:
        return "deprecated_not_found", "Configured model does not exist."
    if "deprecated" in lower and "model" in lower:
        return "deprecated_not_found", "Configured model is deprecated."
    if "insufficient_quota" in lower or ("quota" in lower and ("exceeded" in lower or "exhaust" in lower)):
        return "quota_exhausted", "Provider quota or usage is exhausted."
    if "usage limit" in lower or "credit balance" in lower or "billing hard limit" in lower:
        return "quota_exhausted", "Provider quota or usage is exhausted."
    if "rate limit" in lower or "too many requests" in lower or re.search(r"\b429\b", lower):
        return "rate_limited", "Provider is rate-limited."
    if "api_retry" in lower or "reconnecting" in lower:
        return "rate_limited", "Provider is retrying under load."
    if "unauthorized" in lower or "invalid_grant" in lower or "api key" in lower or "authentication" in lower:
        return "auth_failure", "Authentication failed."
    if "manual authorization is required" in lower or "authenticat" in lower:
        return "auth_failure", "Authentication failed."
    if returncode != 0:
        return "unavailable", "Provider command failed."
    return "available", "Last call completed."


def classify_model_result(
    model_name: str,
    config: Mapping[str, Any],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
    exception: str = "",
    headers: Mapping[str, Any] | None = None,
    now_utc: str | None = None,
) -> dict[str, Any]:
    now = now_utc or utc_now_z()
    command = list(config.get("command") or [])
    provider = str(config.get("provider") or "").strip()
    cli_missing = bool(command and shutil.which(str(command[0])) is None)
    text = "\n".join(part for part in (stderr, stdout, exception) if str(part or "").strip())
    if cli_missing:
        status, reason = "cli_missing", f"{command[0]} is not available on PATH."
    else:
        status, reason = _status_from_error(text, returncode, timed_out=timed_out)
    rate_headers = parse_rate_limit_headers(headers, text)
    available = status == "available"
    record = {
        "schema": HEALTH_SCHEMA_VERSION,
        "model": model_name,
        "provider": provider,
        "available": available,
        "status": status,
        "reason": reason,
        "last_success_utc": now if available else "",
        "last_failure_utc": now if not available else "",
        "rate_limit": rate_headers,
        "current_fallback": "",
        "source": "provider_result",
    }
    if text and not available:
        record["error_preview"] = text[:500]
    return record


def _empty_record(model_name: str, config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": HEALTH_SCHEMA_VERSION,
        "model": model_name,
        "provider": str(config.get("provider") or "").strip(),
        "available": True,
        "status": "available",
        "reason": "No recent provider issues.",
        "last_success_utc": "",
        "last_failure_utc": "",
        "rate_limit": {},
        "current_fallback": "",
        "source": "snapshot",
    }


def _provider_issue_status(record: Mapping[str, Any]) -> tuple[str, str] | None:
    category = str(record.get("last_error_category") or "").strip()
    error = str(record.get("last_error") or "").strip()
    terminal = str(record.get("last_terminal_state") or "").strip()
    if category == "auth":
        return "auth_failure", error or "Authentication failed."
    if terminal == "timed_out":
        return "timeout", "Provider timed out."
    if category in {"provider-busy", "network"}:
        return "rate_limited", error or "Provider appears busy."
    if category in {"interactive-mode", "execution-policy", "empty-output"}:
        return "unavailable", error or "Provider cannot run headlessly."
    if error:
        status, reason = _status_from_error(error, 1)
        if status != "available":
            return status, reason
    return None


def _provider_family(provider_id: str) -> set[str]:
    provider = str(provider_id or "").strip()
    for family in PROVIDER_FAMILIES.values():
        if provider in family:
            return family
    return {provider}


def _latest_provider_record(providers: Mapping[str, Any], provider_id: str) -> Mapping[str, Any]:
    family = _provider_family(provider_id)
    candidates: list[tuple[dt.datetime, Mapping[str, Any]]] = []
    fallback: Mapping[str, Any] = {}
    for candidate_provider in family:
        record = providers.get(candidate_provider, {}) if isinstance(providers, Mapping) else {}
        if not isinstance(record, Mapping):
            continue
        if candidate_provider == provider_id:
            fallback = record
        seen = parse_iso(str(record.get("last_seen_utc") or ""))
        if seen is not None:
            candidates.append((seen, record))
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
    return fallback


def _fallback_order(capability: str) -> list[str]:
    if capability == "code":
        return ["Codex", "Codex Mini", "Gemini", "Copilot", "Cursor", "Agy", "Claude Sonnet", "Claude", "Codex Demo", "Claude Demo"]
    if capability == "drafting":
        return ["Codex", "Claude Sonnet", "Claude", "Gemini", "Copilot", "Cursor", "Agy", "Codex Mini", "Codex Demo", "Claude Demo"]
    return ["Codex Mini", "Codex", "Gemini", "Copilot", "Cursor", "Agy", "Claude Sonnet", "Claude", "Codex Demo", "Claude Demo"]


def choose_fallback(
    model_name: str,
    health: Mapping[str, Mapping[str, Any]],
    *,
    capability: str = "default",
    configured_order: list[str] | None = None,
) -> str:
    configured = configured_order or list(health.keys())
    ordered = [name for name in _fallback_order(capability) if name in configured]
    ordered.extend(name for name in configured if name not in ordered and name != "Auto")
    for candidate in ordered:
        if candidate == model_name:
            continue
        row = health.get(candidate, {})
        if bool(row.get("available", False)) and str(row.get("status") or "") in ACTIVE_STATES:
            return candidate
    return ""


def build_health_snapshot(
    model_options: Mapping[str, Mapping[str, Any]],
    *,
    provider_state: Mapping[str, Any] | None = None,
    stored_health: Mapping[str, Any] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, dict[str, Any]]:
    now_dt = now or dt.datetime.now(dt.timezone.utc)
    provider_state = provider_state or {}
    stored_models = (stored_health or {}).get("models", stored_health or {})
    if not isinstance(stored_models, Mapping):
        stored_models = {}
    outages = provider_state.get("model_outages", {}) if isinstance(provider_state, Mapping) else {}
    providers = provider_state.get("providers", {}) if isinstance(provider_state, Mapping) else {}
    snapshot: dict[str, dict[str, Any]] = {}
    for model_name, config in model_options.items():
        if model_name == "Auto":
            continue
        row = _empty_record(model_name, config)
        stored = stored_models.get(model_name, {}) if isinstance(stored_models, Mapping) else {}
        if isinstance(stored, Mapping):
            for key in ("last_success_utc", "last_failure_utc", "rate_limit", "error_preview"):
                if stored.get(key) not in ("", None, {}, []):
                    row[key] = stored[key]
        command = list(config.get("command") or [])
        if command and shutil.which(str(command[0])) is None:
            row.update(
                {
                    "available": False,
                    "status": "cli_missing",
                    "reason": f"{command[0]} is not available on PATH.",
                    "source": "cli_check",
                }
            )
        outage = outages.get(model_name, {}) if isinstance(outages, Mapping) else {}
        if isinstance(outage, Mapping) and is_future(str(outage.get("unavailable_until", "")), now=now_dt):
            row.update(
                {
                    "available": False,
                    "status": "rate_limited",
                    "reason": str(outage.get("reason") or "Marked as unavailable."),
                    "rate_limit": {
                        **dict(row.get("rate_limit") or {}),
                        "unavailable_until": str(outage.get("unavailable_until") or ""),
                    },
                    "source": "manual_outage",
                }
            )
        provider_id = str(config.get("provider") or "").strip()
        provider_record = _latest_provider_record(providers, provider_id) if provider_id else {}
        if isinstance(provider_record, Mapping):
            issue = _provider_issue_status(provider_record)
            seen = parse_iso(str(provider_record.get("last_seen_utc") or ""))
            if issue and seen is not None and now_dt - seen > PROVIDER_ISSUE_TTL:
                issue = None
            if issue:
                status, reason = issue
                row.update(
                    {
                        "available": False,
                        "status": status,
                        "reason": reason,
                        "last_failure_utc": str(provider_record.get("last_seen_utc") or row.get("last_failure_utc") or ""),
                        "source": "provider_state",
                    }
                )
            elif str(provider_record.get("last_terminal_state") or "") == "completed":
                row.update(
                    {
                        "available": True,
                        "status": "available",
                        "reason": "Last call completed.",
                        "last_success_utc": str(provider_record.get("last_seen_utc") or row.get("last_success_utc") or ""),
                        "source": "provider_state",
                    }
                )
        snapshot[model_name] = row
    configured_order = [name for name in model_options if name != "Auto"]
    for model_name, row in snapshot.items():
        row["current_fallback"] = choose_fallback(model_name, snapshot, configured_order=configured_order)
    return snapshot


def load_health(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": HEALTH_SCHEMA_VERSION, "models": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": HEALTH_SCHEMA_VERSION, "models": {}}
    if not isinstance(data, dict):
        return {"schema": HEALTH_SCHEMA_VERSION, "models": {}}
    data.setdefault("schema", HEALTH_SCHEMA_VERSION)
    data.setdefault("models", {})
    return data


def save_health(path: Path, models: Mapping[str, Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema": HEALTH_SCHEMA_VERSION, "updated_utc": utc_now_z(), "models": models}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def changed_rows(
    previous: Mapping[str, Any],
    current: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    previous_models = previous.get("models", previous) if isinstance(previous, Mapping) else {}
    if not isinstance(previous_models, Mapping):
        previous_models = {}
    changes: list[dict[str, Any]] = []
    for model, row in current.items():
        old = previous_models.get(model, {}) if isinstance(previous_models, Mapping) else {}
        if not isinstance(old, Mapping):
            old = {}
        if old.get("status") != row.get("status") or bool(old.get("available", True)) != bool(row.get("available", True)):
            changes.append({"model": model, "previous": dict(old), "current": dict(row)})
    return changes


def log_health_changes(changes: list[dict[str, Any]], telemetry_root: Path) -> None:
    if not changes:
        return
    path = telemetry_root / "model-health" / "model-health.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    now = utc_now_z()
    with path.open("a", encoding="utf-8") as handle:
        for change in changes:
            payload = {"event_utc": now, **change}
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    try:
        import sys

        tools_dir = str(Path(__file__).resolve().parents[1])
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from telemetry_sqlite import record_runtime_event

        fingerprint = hashlib.sha256(json.dumps(changes, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        record_runtime_event(
            {
                "timestamp": now,
                "event_name": "model_health_change",
                "runtime_label": os.getenv("CASEFORGE_RUNTIME_LABEL", ""),
                "model_label": os.getenv("CASEFORGE_MODEL_LABEL", ""),
                "command": "caseforge-chat model health snapshot",
                "files_read": [],
                "files_written": [str(path)],
                "metrics": {"change_count": len(changes), "fingerprint": fingerprint},
            }
        )
    except Exception:
        pass
