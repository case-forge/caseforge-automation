from __future__ import annotations

from typing import Any

import app_settings

MAX_SETTINGS_BODY = 64 * 1024
OPERATIONS_STATUS = (
    ("auto_draft_hold", "Automatic drafting", "agents.auto_draft_hold",
     "While held, Case flow auto mode skips every drafting step."),
    ("email_filing_hold", "Automatic filing of court replies", "agents.email_filing_hold",
     "While held, court replies are not filed automatically."),
)
SECRETS_NOTE = "Passwords, tokens and connection strings are managed in Key Vault and never shown or stored on this page."


def _entry(r: app_settings.Resolved) -> dict[str, Any]:
    s = r.setting
    out = s.describe()
    out.update(value=r.value, default=app_settings._default(s), source=r.source, locked=r.locked,
               env_invalid=r.env_invalid, updated_by=r.updated_by, updated_at=r.updated_at)
    if s.type == "person_choice":
        out["choices"] = [p["name"] for p in app_settings.resolve("solicitors").value]
    return out


def _statuses() -> list[dict[str, Any]]:
    import importlib

    out = []
    for key, label, module, help_ in OPERATIONS_STATUS:
        try:
            held, reason = importlib.import_module(module).is_held()
            out.append({"key": key, "label": label, "help": help_, "held": bool(held), "reason": str(reason)})
        except Exception:
            out.append({"key": key, "label": label, "help": help_, "held": True, "reason": "state unreadable"})
    return out


def set_operation(actor: str, key: str, held: bool) -> None:
    import importlib

    module = next((m for k, _label, m, _help in OPERATIONS_STATUS if k == key), None)
    if module is None:
        raise KeyError(key)
    mod = importlib.import_module(module)
    if held:
        mod.set_hold(reason=f"held from the Settings page by {actor}", set_by=actor)
    else:
        mod.release(set_by=actor)


def build_view(*, can_edit: bool) -> dict[str, Any]:
    return {
        "can_edit": can_edit,
        "secrets_note": SECRETS_NOTE,
        "groups": [{"key": k, "label": label, "description": d} for k, label, d in app_settings.GROUPS],
        "settings": [_entry(r) for r in app_settings.resolve_all() if not r.setting.hidden],
        "status": _statuses(),
    }

