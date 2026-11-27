from __future__ import annotations

import datetime as dt
import logging
import os
from pathlib import Path
from typing import Any

import model_registry as reg

log = logging.getLogger(__name__)

STATS_DAYS = 14
AUDIT_FILENAME = "model-role-changes.jsonl"
SAFETY_ROLES = frozenset({reg.ROLE_SAFETY_GUARD, reg.ROLE_SAFETY_GUARD_FALLBACK})
SINGLE_PURPOSE_ROLES = frozenset({reg.ROLE_VISION})

PURPOSES: dict[str, str] = {
    "case_summary": "Writes the case summary on a bundle front page",
    "chronology": "Writes the chronology on a bundle front page",
    "ccl_draft": "Drafts the client care letter",
    "ccl_escalation": "Second look at a client care letter the first pass was unsure about",
    "ccl_field_check": "Checks the fields of a client care letter",
    "fact_reconciler": "Settles what a client's statement, form and referral say about their family into one set of facts",
    "intro_audit": "Reads each client's referral intro every night to fill gaps and raise differences",
    "client_letter": "Drafts letters to clients",
    "brief_to_counsel": "Drafts the brief to counsel",
    "email_task_triage": "Turns an email into a to-do for the team",
    "order_type_tags": "Tags a court order with its type",
    "matter_facts": "Pulls the basic facts of a matter from its documents",
    "matter_incidents": "Lists incidents mentioned in a matter's documents",
    "matter_timeline": "Builds the dated timeline of a matter",
    "form_fill_strong": "Fills court forms (the careful pass)",
    "form_fill_cheap": "Fills court forms (the quick pass)",
    "an_draft": "Proofreads attendance notes: spelling, punctuation and grammar only",
    "an_memo_classifier": "Sorts old memo text into attendance note types",
    "opening_letter": "Drafts the opening letter on a new matter",
    "vergil_chat": "Answers questions in Vergil, the chat assistant",
    "chat_chitchat": "Handles small talk in Vergil",
    "chat_helpers": "Small helper steps inside Vergil chats",
    "chat_title": "Gives each Vergil chat a short title",
    "retrieval_answer": "Answers a search question from retrieved passages",
    "retrieval_answer_deep": "Answers harder search questions from retrieved passages",
    "safety_guard": "Checks messages for unsafe requests before they are answered",
    "safety_guard_fallback": "Takes over the safety check when the main guard does not answer",
    "mail_triage": "Sorts incoming mail into categories",
    "mail_escalation": "Second look at mail the first pass could not sort",
    "email_pdf_label": "Names the PDF made from an email",
    "scanned_docs_triage": "Works out what a scanned document is",
    "notice_of_acting": "Fills the notice of acting",
    "referralpartner_intake": "Reads referrer referrals into client details",
    "statement_postcode": "Finds a postcode in a witness statement",
    "name_extractor": "Pulls names out of documents",
    "hearing_extract": "Reads hearing dates and details out of court documents",
    "calendar_finder": "Finds hearings in calendar and email text",
    "hearing_judge": "Reads the email behind a hearing waiting for review and says whether the hearing is real",
    "spelling_tiebreak": "Settles a doubtful spelling of a name",
    "spelling_second": "Reads what the first proofreader could not settle in a witness statement",
    "compliance_test": "Used by the model compliance test only",
    "vision": "Reads the text on a scanned page image",
    "urgent_review": "Reviews mail flagged as urgent",
    "amend_planner": "Case flow amend rounds: plans the changes",
    "amend_worker": "Case flow amend rounds: does the work",
    "amend_questioner": "Case flow amend rounds: asks what is missing",
    "amend_editor": "Case flow amend rounds: edits the draft",
    "amend_critic": "Case flow amend rounds: criticises the draft",
    "amend_judge": "Case flow amend rounds: judges between versions",
    "amend_small": "Case flow amend rounds: light steps",
    "amend_large": "Case flow amend rounds: heavy steps",
}

SOURCE_WORDS = {
    "env": "Pinned by an environment variable",
    "override": "Changed in Settings",
    "file": "Model roles file (default)",
}


class ModelSwapError(Exception):

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def anthropic_key_configured() -> bool:
    return bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip())


def _direct_model(model_id: str) -> str:
    try:
        import model_backend as mb

        return mb.anthropic_direct_model(model_id)
    except Exception:
        return ""


def anthropic_usable(model_id: str) -> bool:
    return bool(_direct_model(model_id))


def _is_anthropic(model_id: str) -> bool:
    return model_id.lower().startswith("anthropic/")


def role_stats(days: int = STATS_DAYS) -> dict[str, dict[str, Any]] | None:
    try:
        import telemetry_sqlite

        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with telemetry_sqlite._connect() as conn:
            rows = conn.execute(
                "SELECT route_label, final_state, elapsed_seconds, estimated_cost_usd FROM model_context_events "
                "WHERE recorded_at >= ? AND route_label LIKE 'deterministic:%'",
                (since,),
            ).fetchall()
    except Exception as exc:
        log.warning("model role stats unavailable: %s", type(exc).__name__)
        return None
    seconds: dict[str, list[float]] = {}
    out: dict[str, dict[str, Any]] = {}
    for label, state, elapsed, cost in rows:
        role = str(label).rsplit(":", 1)[-1]
        if role not in reg.ROLE_TIERS:
            continue
        row = out.setdefault(role, {"calls": 0, "failures": 0, "cost_usd": 0.0})
        row["calls"] += 1
        row["failures"] += 1 if state == "failed" else 0
        row["cost_usd"] += float(cost or 0.0)
        seconds.setdefault(role, []).append(float(elapsed or 0.0))
    for role, row in out.items():
        values = sorted(seconds[role])
        row["p50_seconds"] = round(values[len(values) // 2], 2) if len(values) % 2 else round((values[len(values) // 2 - 1] + values[len(values) // 2]) / 2, 2)
        row["cost_usd"] = round(row["cost_usd"], 4)
    return out


def _resolved(role: str) -> tuple[str, str]:
    try:
        model, source = reg.resolve(role, reg.OPENROUTER)
    except reg.ModelRoleError:
        return "", "missing"
    return model, source.split(":", 1)[0]


def _file_default(role: str) -> str:
    return (reg.load_registry().get(reg.role_key(role)) or "").strip()


def in_use_models() -> dict[str, list[str]]:
    used: dict[str, list[str]] = {}
    for role in reg.ROLES:
        model, _ = _resolved(role)
        if model:
            used.setdefault(model, []).append(role)
    return used


def _refusal(role: str, new: str, used: dict[str, list[str]]) -> str:
    roles = used.get(new)
    if not roles:
        return "That model is not serving any role at the moment, and only models already in use can be chosen."
    if not any(reg.ROLE_TIERS[r] == reg.ROLE_TIERS[role] for r in roles):
        return "That model is used only for jobs of a different size class; only models used for the same size of job can be chosen."
    if role in SAFETY_ROLES and not any(r in SAFETY_ROLES for r in roles):
        return "The safety check can only use a model that already does a safety check."
    if role not in SAFETY_ROLES and all(r in SAFETY_ROLES for r in roles):
        return "That model is used only as a safety check, so it cannot be chosen for another job."
    if role in SINGLE_PURPOSE_ROLES and role not in roles:
        return "Reading page images needs a model already doing that job, so no other model can be chosen."
    return ""


def candidates_for(role: str, used: dict[str, list[str]] | None = None) -> list[str]:
    used = used if used is not None else in_use_models()
    current, _ = _resolved(role)
    return sorted(m for m in used if m != current and not _refusal(role, m, used))


def _caps(backend: str) -> dict[str, Any]:
    try:
        import model_backend as mb

        if backend == "anthropic-direct":
            return {"daily_usd": mb.daily_spend_cap_usd("anthropic"), "total_usd": mb.anthropic_total_cap_usd()}
        return {"daily_usd": mb.daily_spend_cap_usd("openrouter"), "total_usd": None}
    except Exception:
        return {"daily_usd": None, "total_usd": None}


def _retention(model: str, backend: str) -> dict[str, str]:
    if backend == "anthropic-direct":
        return {"status": "direct", "text": "Anthropic's own API, switched on for testing on this box. It has no per-request zero retention setting, so it is not for unattended work."}
    return {"status": "zdr", "text": "Zero data retention asserted on every request; a model with no such provider is refused."}


def build_view(*, can_edit: bool) -> dict[str, Any]:
    used = in_use_models()
    stats = role_stats()
    roles = []
    for role in reg.ROLES:
        model, kind = _resolved(role)
        direct = bool(model) and anthropic_usable(model)
        backend = "anthropic-direct" if direct else "openrouter"
        row_stats = (stats or {}).get(role, {"calls": 0, "failures": 0, "p50_seconds": None, "cost_usd": 0.0}) if stats is not None else None
        locked = kind == "env"
        cands = [] if locked else candidates_for(role, used)
        default = _file_default(role)
        if locked:
            note = "Pinned by an environment variable on the server, so it cannot be changed here."
        elif kind == "missing":
            note = "No model is set for this role."
        elif not cands:
            note = "No other model in use can do this job."
        else:
            note = ""
        roles.append({
            "role": role,
            "purpose": PURPOSES.get(role, role.replace("_", " ").capitalize()),
            "tier": reg.ROLE_TIERS[role],
            "model": model,
            "source": kind,
            "source_text": SOURCE_WORDS.get(kind, "Not set"),
            "default_model": default,
            "overridden": kind == "override",
            "backend": backend,
            "anthropic_direct": direct,
            "retention": _retention(model, backend),
            "spend_cap": _caps(backend),
            "stats": row_stats,
            "swappable": bool(cands) and not locked,
            "locked": locked,
            "note": note,
            "candidates": cands,
            "applies": "next call",
        })
    return {
        "can_edit": can_edit,
        "stats_days": STATS_DAYS,
        "stats_available": stats is not None,
        "anthropic_key_configured": anthropic_key_configured(),
        "models_in_use": sorted(used),
        "roles": roles,
    }


def audit_path() -> Path:
    return reg.overrides_path().with_name(AUDIT_FILENAME)


def _write_audit(row: dict[str, Any]) -> None:
    from graph_mail_safe_ops import _append_jsonl_locked

    audit_path().parent.mkdir(parents=True, exist_ok=True)
    _append_jsonl_locked(audit_path(), row)


def _audited(by: str, role: str, action: str, old: str, new: str) -> None:
    row = {
        "at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by": by,
        "role": role,
        "action": action,
        "old": old,
        "new": new,
    }
    try:
        _write_audit(row)
    except Exception as exc:
        log.error("model role change audit failed: %s", type(exc).__name__)
        raise ModelSwapError("The change was not made because it could not be recorded. Try again shortly.", 502) from exc


def _check_role(role: str) -> None:
    if role not in reg.ROLE_TIERS:
        raise ModelSwapError("There is no such role.", 404)


def set_role_model(role: str, new_model: str, by: str, expected_old: str = "") -> dict[str, str]:
    _check_role(role)
    new_model = (new_model or "").strip()
    old, kind = _resolved(role)
    if kind == "env":
        raise ModelSwapError("This role is pinned by an environment variable on the server, so it cannot be changed here.", 409)
    if expected_old and expected_old != old:
        raise ModelSwapError("This role was changed by someone else since you opened the page. Reload and try again.", 409)
    if new_model == old:
        raise ModelSwapError("That model is already serving this role.", 422)
    why = _refusal(role, new_model, in_use_models())
    if why:
        raise ModelSwapError(why, 422)
    _audited(by, role, "set", old, new_model)
    entries = reg.load_overrides()
    if new_model == _file_default(role):
        entries.pop(role, None)
    else:
        entries[role] = new_model
    reg.write_overrides(entries)
    return {"role": role, "old": old, "new": new_model}


def reset_role_model(role: str, by: str) -> dict[str, str]:
    _check_role(role)
    entries = reg.load_overrides()
    if role not in entries:
        raise ModelSwapError("This role is not changed from its default.", 422)
    old, _ = _resolved(role)
    default = _file_default(role)
    _audited(by, role, "reset", old, default)
    entries.pop(role)
    reg.write_overrides(entries)
    return {"role": role, "old": old, "new": default}
