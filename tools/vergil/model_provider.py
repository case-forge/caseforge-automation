from __future__ import annotations

import datetime as dt
import importlib
import json
import os
import re
import shlex
from pathlib import Path

import monitoring.model_health as model_health_lib

from vergil.formatting import format_countdown, parse_iso_dt
from vergil.primitives import SESSION_DIR, REPO_ROOT, utc_now_iso

MODEL_OPTIONS: dict[str, dict[str, object]] = {
    "Auto": {
        "provider": "auto",
        "command": [],
        "parser": "auto",
        "supports_resume": False,
        "context_budget": 0,
        "reset_window_hours": 0,
    },
    "Claude": {
        "provider": "claude",
        "command": [],
        "parser": "claude",
        "supports_resume": True,
        "context_budget": 180_000,
        "reset_window_hours": 5,
    },
    "Claude Sonnet": {
        "provider": "claude_sonnet",
        "command": [],
        "parser": "claude",
        "supports_resume": True,
        "context_budget": 180_000,
        "reset_window_hours": 5,
    },
}
MODEL_ALIASES = {
    "Claude (default)": "Claude",
    "Sonnet": "Claude Sonnet",
    "Claude (Sonnet)": "Claude Sonnet",
    "Claude Code Demo": "Claude",
    "Claude Demo": "Claude",
    "Codex Spark": "Auto",
    "Codex Mini": "Auto",
    "Codex": "Auto",
    "Codex Demo": "Auto",
    "Codex 5.3 Spark": "Auto",
    "Codex 5.5": "Auto",
    "Codex 5.4 Mini": "Auto",
    "Copilot": "Auto",
    "Cursor": "Auto",
    "Agy": "Auto",
    "Gemini": "Auto",
}
MANUAL_WINDOWS = {
    "claude_web": {"label": "Claude web", "reset_window_hours": 5},
    "chatgpt_web": {"label": "ChatGPT web", "reset_window_hours": 3},
}
MODEL_HEALTH_FILE = SESSION_DIR / "model-health.json"

SELECTABLE_MODEL_PROVIDER_PREFIXES = ("auto", "claude")

EFFORT = "high"
CLAUDE_EFFORT_MAP = {"medium": "medium", "high": "high", "xhigh": "max"}

MODEL_COST_PER_MTK = {
    "Claude":   (3.00,  15.00, 0.30, 3.75),
    "claude":   (3.00,  15.00, 0.30, 3.75),
    "Copilot":  (0.00,   0.00, 0.00, 0.00),
    "Cursor":   (0.00,   0.00, 0.00, 0.00),
    "Agy":      (0.00,   0.00, 0.00, 0.00),
}


def selectable_model_keys() -> list[str]:
    keys: list[str] = []
    for name, config in MODEL_OPTIONS.items():
        provider = str(config.get("provider", ""))
        if not provider.startswith(SELECTABLE_MODEL_PROVIDER_PREFIXES):
            continue
        if name.endswith("Demo"):
            continue
        keys.append(name)
    return keys


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    rates = MODEL_COST_PER_MTK.get(model, (3.00, 15.00, 0.00, 0.00))
    mtk = 1_000_000
    return round(
        input_tokens * rates[0] / mtk
        + output_tokens * rates[1] / mtk
        + cache_read_tokens * rates[2] / mtk
        + cache_creation_tokens * rates[3] / mtk,
        6,
    )


def provider_state_file(username: str) -> Path:
    return SESSION_DIR / f"{username}.provider-state.json"


def save_provider_state(username: str, payload: dict) -> None:
    try:
        provider_payload = dict(payload or {})
        provider_payload.pop("model_outages", None)
        provider_state_file(username).write_text(
            json.dumps(provider_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def model_outages_file() -> Path:
    return SESSION_DIR / "model-outages.json"


def kv_env() -> dict[str, str]:
    env = os.environ.copy()
    local_bin = str(Path.home() / ".local" / "bin")
    if local_bin not in env.get("PATH", "").split(":"):
        env["PATH"] = local_bin + ":" + env.get("PATH", "")
    codex_home = Path.home() / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    env.setdefault("CODEX_HOME", str(codex_home))
    if env.get("CASEFORGE_CLIENTDB_PG_URL") or env.get("AZURE_SQL_CONNECTION_STRING"):
        return env
    kv_file = REPO_ROOT / ".secrets" / "caseforge-env"
    try:
        st_mode = kv_file.stat().st_mode
        if kv_file.stat().st_uid == os.getuid() and (st_mode & 0o077) == 0:
            for line in kv_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                k, _, raw_v = line.partition("=")
                k = k.strip()
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
                    continue
                try:
                    parts = shlex.split(raw_v, posix=True)
                    env[k] = parts[0] if parts else ""
                except ValueError:
                    continue
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return env


def canonical_model_key(model_key: str) -> str:
    return MODEL_ALIASES.get(str(model_key).strip(), str(model_key).strip())


def model_config(model_key: str) -> dict[str, object]:
    return dict(MODEL_OPTIONS.get(canonical_model_key(model_key), MODEL_OPTIONS["Claude"]))


def provider_id_for_model(model_key: str) -> str:
    return str(model_config(model_key).get("provider", ""))


def empty_provider_state(legacy_sid: str | None = None) -> dict:
    providers = {}
    for model_name, config in MODEL_OPTIONS.items():
        provider = str(config.get("provider", ""))
        if provider in ("", "auto"):
            continue
        providers[provider] = {
            "model": model_name,
            "session_id": legacy_sid if provider == "claude" and legacy_sid else "",
            "continuity": "fresh session",
            "execution_mode": "web-safe",
            "context_tokens": 0,
            "context_pct": 0,
            "context_label": "Low",
            "pressure_label": "OK",
            "pressure_reason": "No recent provider issues.",
            "warning": "",
            "last_error": "",
            "last_error_category": "",
            "last_retry_count": 0,
            "max_retry_delay_ms": 0,
            "session_anchor_utc": "",
            "next_reset_utc": "",
            "last_seen_utc": "",
            "last_terminal_state": "",
            "last_route": "",
        }
    return {
        "providers": providers,
        "current_provider": "claude" if legacy_sid else "",
        "manual_windows": {
            key: {"active": False, "started_utc": "", "next_reset_utc": "", "note": ""}
            for key in MANUAL_WINDOWS
        },
        "model_outages": {},
    }


def normalise_model_outages(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    raw_outages = value.get("model_outages", value)
    outages = raw_outages if isinstance(raw_outages, dict) else value
    normalised: dict[str, dict] = {}
    for model_key, outage in outages.items():
        if not isinstance(model_key, str) or not isinstance(outage, dict):
            continue
        canonical_key = canonical_model_key(model_key)
        until = str(outage.get("unavailable_until", "")).strip()
        if not until:
            continue
        normalised[canonical_key] = {
            "unavailable_until": until,
            "reason": str(outage.get("reason", "Hit usage limit") or "Hit usage limit"),
        }
    return normalised


def save_model_outages(outages: dict) -> None:
    try:
        model_outages_file().write_text(
            json.dumps(normalise_model_outages(outages), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def load_model_outages() -> dict:
    shared: dict = {}
    path = model_outages_file()
    if path.exists():
        try:
            return normalise_model_outages(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return {}

    migrated: dict = {}
    try:
        for state_file in SESSION_DIR.glob("*.provider-state.json"):
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            for model_key, outage in normalise_model_outages(data.get("model_outages", {})).items():
                migrated.setdefault(model_key, outage)
    except Exception:
        pass
    if migrated != shared:
        save_model_outages(migrated)
    return migrated


def empty_provider_state_with_outages(legacy_sid: str | None = None) -> dict:
    state = empty_provider_state(legacy_sid)
    state["model_outages"] = load_model_outages()
    return state


def load_provider_state(username: str) -> dict:
    from vergil.user_state import load_session

    legacy_sid = load_session(username)
    path = provider_state_file(username)
    if not path.exists():
        return empty_provider_state_with_outages(legacy_sid)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return empty_provider_state_with_outages(legacy_sid)
    except Exception:
        return empty_provider_state_with_outages(legacy_sid)

    base = empty_provider_state(legacy_sid)
    base.update({k: v for k, v in data.items() if k != "providers"})
    loaded_providers = data.get("providers", {})
    if isinstance(loaded_providers, dict):
        for provider, provider_payload in loaded_providers.items():
            if provider in base["providers"] and isinstance(provider_payload, dict):
                base["providers"][provider].update(provider_payload)
    loaded_windows = data.get("manual_windows", {})
    if isinstance(loaded_windows, dict):
        for key, window_payload in loaded_windows.items():
            if key in base["manual_windows"] and isinstance(window_payload, dict):
                base["manual_windows"][key].update(window_payload)
    base["model_outages"] = load_model_outages()
    return base


def provider_record(provider_state: dict, provider_id: str) -> dict:
    providers = provider_state.setdefault("providers", {})
    record = providers.setdefault(provider_id, {})
    template = empty_provider_state().get("providers", {}).get(provider_id, {})
    if isinstance(template, dict):
        for key, value in template.items():
            record.setdefault(key, value)
    return record


def provider_session_ids(provider_state: dict | None) -> dict[str, str]:
    sessions: dict[str, str] = {}
    providers = (provider_state or {}).get("providers", {})
    if isinstance(providers, dict):
        for provider, record in providers.items():
            if isinstance(record, dict):
                sid = str(record.get("session_id", "")).strip()
                if sid:
                    sessions[str(provider)] = sid
    return sessions


def model_outage(model_key: str, provider_state: dict) -> dict:
    return provider_state.get("model_outages", {}).get(canonical_model_key(model_key), {})


def context_band(model_key: str, token_estimate: int) -> tuple[int, str]:
    budget = int(model_config(model_key).get("context_budget", 0) or 0)
    if budget <= 0:
        return 0, "Low"
    pct = max(0, min(100, round((token_estimate / budget) * 100)))
    if pct >= 90:
        return pct, "Critical"
    if pct >= 70:
        return pct, "High"
    if pct >= 45:
        return pct, "Medium"
    return pct, "Low"


def apply_window_anchor(anchor_utc: str, hours: int) -> str:
    anchor = parse_iso_dt(anchor_utc)
    if anchor is None or hours <= 0:
        return ""
    return (anchor + dt.timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def classify_error(text: str) -> str:
    lower = str(text or "").lower()
    if not lower:
        return ""
    if "not found on path" in lower or "no such file or directory" in lower:
        return "cli_missing"
    if "term is set to \"dumb\"" in lower or "no terminal is available" in lower or "tty" in lower:
        return "interactive-mode"
    if "manual authorization is required" in lower or "authenticat" in lower or "invalid_grant" in lower:
        return "auth"
    if "reconnecting" in lower or "api_retry" in lower or "retry" in lower:
        return "provider-busy"
    if "operation not permitted" in lower or "websocket" in lower or "network" in lower:
        return "network"
    if "approval" in lower or "sandbox" in lower or "permission" in lower:
        return "execution-policy"
    return "general"


def provider_warning(record: dict) -> tuple[str, str]:
    retries = int(record.get("last_retry_count", 0) or 0)
    context_label = str(record.get("context_label", "Low"))
    error_category = str(record.get("last_error_category", ""))
    continuity = str(record.get("continuity", "fresh session"))
    if error_category == "cli_missing":
        return "Degraded", "Provider CLI is missing from PATH."
    if error_category == "auth":
        return "Degraded", "Authentication is blocking headless runs."
    if error_category == "interactive-mode":
        return "Degraded", "Provider attempted an interactive prompt in web mode."
    if retries >= 5:
        return "Hammered", "Repeated retries indicate the provider is under pressure."
    if retries >= 2:
        return "Busy", "Recent retries suggest the provider is slowing down."
    if error_category in {"network", "execution-policy"}:
        return "Degraded", "Recent run hit a connectivity or execution-policy issue."
    if context_label in {"High", "Critical"}:
        return "Busy", "Estimated context load is high for this session."
    if continuity == "one-shot":
        return "OK", "Scoped one-shot run; no prior chat context was resumed."
    return "OK", "No recent provider issues."


def record_provider_event(provider_state: dict, event: dict) -> None:
    provider_id = str(event.get("provider", "")).strip()
    if not provider_id:
        return
    record = provider_record(provider_state, provider_id)
    event_name = str(event.get("event", "")).strip()
    now_utc = utc_now_iso()
    provider_state["current_provider"] = provider_id
    record["last_seen_utc"] = now_utc

    if event_name == "start":
        record["model"] = str(event.get("model", record.get("model", ""))).strip() or record.get("model", "")
        record["continuity"] = str(event.get("continuity", record.get("continuity", "fresh session")))
        record["execution_mode"] = str(event.get("execution_mode", record.get("execution_mode", "web-safe")))
        token_estimate = int(event.get("estimated_context_tokens", 0) or 0)
        pct, label = context_band(str(record.get("model", "Claude")), token_estimate)
        record["context_tokens"] = token_estimate
        record["context_pct"] = pct
        record["context_label"] = label
        if not record.get("session_anchor_utc") or record.get("continuity") == "fresh session":
            if not record.get("session_id"):
                record["session_anchor_utc"] = now_utc
        reset_hours = int(model_config(str(record.get("model", ""))).get("reset_window_hours", 0) or 0)
        if record.get("session_anchor_utc") and reset_hours:
            record["next_reset_utc"] = apply_window_anchor(str(record.get("session_anchor_utc", "")), reset_hours)
    elif event_name == "session":
        if bool(event.get("one_shot")):
            record["last_one_shot_session_utc"] = now_utc
            return
        session_id = str(event.get("session_id", "")).strip()
        if session_id:
            if session_id != str(record.get("session_id", "")).strip():
                record["session_anchor_utc"] = now_utc
            record["session_id"] = session_id
            reset_hours = int(model_config(str(record.get("model", ""))).get("reset_window_hours", 0) or 0)
            if reset_hours:
                record["next_reset_utc"] = apply_window_anchor(str(record.get("session_anchor_utc", "")), reset_hours)
    elif event_name == "retry":
        record["last_retry_count"] = max(int(record.get("last_retry_count", 0) or 0), int(event.get("attempt", 0) or 0))
        record["max_retry_delay_ms"] = max(int(record.get("max_retry_delay_ms", 0) or 0), int(event.get("retry_delay_ms", 0) or 0))
        retry_error = str(event.get("error", "")).strip()
        if retry_error:
            record["last_error"] = retry_error
            record["last_error_category"] = "provider-busy"
    elif event_name == "error":
        record["last_error"] = str(event.get("error", "")).strip()
        record["last_error_category"] = str(event.get("category", "")).strip() or classify_error(record["last_error"])
    elif event_name == "terminal":
        record["last_terminal_state"] = str(event.get("terminal_state", "")).strip()
        if record["last_terminal_state"] in {"timed_out", "failed"} and not record.get("last_error_category"):
            record["last_error_category"] = "provider-busy"
        if record["last_terminal_state"] == "completed" and record.get("last_error_category") == "provider-busy":
            record["last_error_category"] = ""
            record["last_error"] = ""
            record["last_retry_count"] = 0
            record["max_retry_delay_ms"] = 0

    pressure_label, pressure_reason = provider_warning(record)
    record["pressure_label"] = pressure_label
    record["pressure_reason"] = pressure_reason
    if pressure_label in {"Busy", "Hammered", "Degraded"}:
        context_note = ""
        if str(record.get("context_label", "")) in {"High", "Critical"}:
            context_note = f" Context pressure is {record.get('context_label')} ({record.get('context_pct', 0)}%)."
        record["warning"] = pressure_reason + context_note
    else:
        record["warning"] = ""


def model_health_snapshot(provider_state: dict) -> dict[str, dict]:
    global model_health_lib
    model_health_lib = importlib.reload(model_health_lib)
    previous = model_health_lib.load_health(MODEL_HEALTH_FILE)
    snapshot = model_health_lib.build_health_snapshot(
        MODEL_OPTIONS,
        provider_state=provider_state,
        stored_health=previous,
    )
    changes = model_health_lib.changed_rows(previous, snapshot)
    if changes:
        model_health_lib.log_health_changes(changes, REPO_ROOT / "telemetry")
    model_health_lib.save_health(MODEL_HEALTH_FILE, snapshot)
    return snapshot


def apply_effort_to_command(cmd: list[str], parser: str) -> list[str]:
    effort = EFFORT
    if parser in {"codex", "codex_demo"}:
        rewritten = list(cmd)
        for idx, part in enumerate(rewritten):
            if str(part).startswith("model_reasoning_effort="):
                rewritten[idx] = f'model_reasoning_effort="{effort}"'
                return rewritten
        return rewritten + ["-c", f'model_reasoning_effort="{effort}"']
    if parser in {"claude", "claude_demo"}:
        return list(cmd) + ["--effort", CLAUDE_EFFORT_MAP.get(effort, "high")]
    return list(cmd)


def display_model_name(model_key: str) -> str:
    canonical = canonical_model_key(model_key)
    if canonical == "Claude":
        return "Claude Haiku"
    return canonical


def estimate_context_tokens(messages: list[dict], pending_prompt: str = "") -> int:
    total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
    total_chars += len(pending_prompt or "")
    return max(0, round(total_chars / 4))


def selected_provider_session_id(provider_state: dict, selected_model: str) -> str:
    provider_id = provider_id_for_model(canonical_model_key(selected_model))
    if not provider_id or provider_id == "auto":
        provider_id = str(provider_state.get("current_provider", "")).strip()
    if not provider_id:
        return ""
    return str(provider_state.get("providers", {}).get(provider_id, {}).get("session_id", "")).strip()


def manual_window_summary(window: dict, key: str) -> str:
    if not window.get("active"):
        return f"{MANUAL_WINDOWS[key]['label']}: not tracking"
    started = str(window.get("started_utc", "")).strip()
    next_reset = str(window.get("next_reset_utc", "")).strip()
    return (
        f"{MANUAL_WINDOWS[key]['label']}: started {started or 'unknown'} · "
        f"next reset {next_reset or 'unknown'} ({format_countdown(next_reset)})"
    )
