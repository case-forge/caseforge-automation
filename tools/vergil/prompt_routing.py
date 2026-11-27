from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Mapping

from onboarding import notice_of_acting as notice_of_acting_tool
from vergil_chat import vergil_chat_ai_helpers as ai_helpers
from vergil_chat import vergil_chat_status as status_helper

from vergil.client_search import client_lookup_prefixes
from vergil.formatting import parse_iso_dt
from vergil.model_provider import canonical_model_key, display_model_name
from vergil.primitives import SESSION_DIR, normalise_space, prompt_lower
from vergil.sql_cooldown import sql_cooldown_until


CODE_PATTERNS = (
    "streamlit", "app.py", "python", "repo", "codebase", "git", "commit", "push",
    "branch", "bug", "fix", "implement", "refactor", "patch", "script", "ui", "sidebar",
)
DRAFT_PATTERNS = (
    "draft", "prepare", "write", "generate", "create", "attendance note", "brief",
    "bundle", "statement of service", "closing letter", "client care letter", "summary", "startup", "triage",
    "email", "counsel", "calendar", "todo review", "to do review",
)
TOOL_PATTERNS = (
    "what time", "current time", "what day", "today's date", "todays date",
    "what hearings are coming up", "hearings are coming up", "next 14 days",
    "next 7 days", "same day hearings", "stale tasks", "todo lint", "to do lint",
    "daily briefing",
)


def looks_like_code_task(prompt: str) -> bool:
    text = prompt_lower(prompt)
    return any(token in text for token in CODE_PATTERNS)


def looks_like_drafting_task(prompt: str) -> bool:
    text = prompt_lower(prompt)
    return any(token in text for token in DRAFT_PATTERNS)


def looks_like_complex_matter_workflow(prompt: str) -> bool:
    text = prompt_lower(prompt)
    action_hits = sum(
        1
        for pattern in (
            r"\bsend\b",
            r"\bemail\b",
            r"\bservice\b|\bserve\b|\bprocess server\b",
            r"\bbrief\b|\binstructions to counsel\b",
            r"\bbundle\b",
            r"\bcounsel\b|\bchambers\b",
            r"\bprevious\s+an\b|\bprevious attendance note\b",
            r"\bnmo\b|\bnon[- ]molestation\b|\border\b",
        )
        if re.search(pattern, text)
    )
    family_ops = re.search(r"\bnmo\b|\bnon[- ]molestation\b|\bfl401\b|\bfl404\b|\border\b", text) is not None
    return family_ops and action_hits >= 4


def looks_like_tool_task(prompt: str) -> bool:
    text = prompt_lower(prompt)
    return any(token in text for token in TOOL_PATTERNS) or status_helper.looks_like_status_prompt(prompt)


def is_client_search_assistant_message(msg: dict) -> bool:
    return (
        str(msg.get("workflow", "")).strip() == "client_search"
        or str(msg.get("route_reason", "")).strip() == "Local client DB search"
        or str(msg.get("model", "")).strip() == "Client DB"
    )


def looks_like_client_care_letter_request(prompt: str) -> bool:
    text = prompt_lower(prompt)
    return bool(
        "client care letter" in text
        or "tasks/opening-letter" in text
        or "tasks/client-care-letter" in text
        or re.search(r"\bccl\b", text)
        or "terms of business and privacy notice" in text
    )


_CCL_MENTION_RE = re.compile(r"\bccls?\b|\bclient[- ]care letters?\b")
_QUESTION_OPENER_RE = re.compile(
    r"^\W*(?:has|have|did|was|were|is|are|when|where|why|what|which|who|how)\b"
)
_REQUEST_OPENER_RE = re.compile(r"^\W*(?:please\W+)?(?:can|could|would|will) you\b")
_QUESTION_MARKER_RE = re.compile(r"\bstatus\b|\btell me whether\b|\blet me know if\b")


def _reads_as_a_question(text: str) -> bool:
    if _QUESTION_OPENER_RE.search(text) or _QUESTION_MARKER_RE.search(text):
        return True
    return text.rstrip().endswith("?") and not _REQUEST_OPENER_RE.search(text)


def looks_like_ccl_drafting_request(prompt: str) -> bool:
    text = prompt_lower(prompt)
    return bool(_CCL_MENTION_RE.search(text)) and not _reads_as_a_question(text)


def ccl_only_in_case_flow_reply() -> str:
    from vergil.background_jobs import CCL_USE_CASEFLOW_MESSAGE

    return CCL_USE_CASEFLOW_MESSAGE


def looks_like_notice_of_acting_request(prompt: str) -> bool:
    return notice_of_acting_tool.looks_like_notice_request(prompt)


def looks_like_legal_aid_signing_request(prompt: str) -> bool:
    text = prompt_lower(prompt)
    return (
        "legal aid" in text
        and any(token in text for token in ("sign", "signature", "privacy", "application", "forms", "letter"))
        and any(token in text for token in ("draft", "email", "send", "prepare", "set up", "setup"))
    )


def looks_like_client_lookup_request(prompt: str) -> bool:
    text = prompt_lower(prompt)
    if text.startswith(client_lookup_prefixes()):
        return True
    if len(text) < 180 and re.search(r"\b(details?|info|information|phone|email|dob|case number|case no|ref|reference)\b", text):
        return True
    return False



ADMIN_AUDIT_HEALTH_RE = re.compile(
    r"^(?:show |run |val )?(?:system |ops |operational )?health(?: check| status| snapshot)?$"
)
ADMIN_AUDIT_BRIEFING_RE = re.compile(
    r"^(?:show |run |val )?(?:audit|pii|daily|supervisor) (?:briefing|review|table|audit)$"
)


def admin_audit_intent(text: str) -> str:
    clean = str(text or "").strip().lower()
    if ADMIN_AUDIT_HEALTH_RE.match(clean):
        return "health"
    if ADMIN_AUDIT_BRIEFING_RE.match(clean):
        return "briefing"
    return ""


def is_model_available(model_key: str, provider_state: dict) -> bool:
    outage = provider_state.get("model_outages", {}).get(canonical_model_key(model_key), {})
    until_str = str(outage.get("unavailable_until", "")).strip()
    if not until_str:
        return True
    until = parse_iso_dt(until_str)
    if until is None:
        return True
    return dt.datetime.now(dt.timezone.utc) >= until


def _sql_cooldown_json_path() -> Path:
    return SESSION_DIR / "sql-cooldown.json"


def is_sql_available() -> bool:
    if os.getenv("LOCAL_SQLITE_PATH", "").strip() or os.getenv("LOCAL_SQL_CONNECTION_STRING", "").strip():
        return True
    try:
        path = _sql_cooldown_json_path()
        if not path.exists():
            return True
        data = json.loads(path.read_text(encoding="utf-8"))
        until_str = str(data.get("unavailable_until", "")).strip()
        if not until_str:
            return True
        until = dt.datetime.fromisoformat(until_str.replace("Z", "+00:00"))
        return dt.datetime.now(dt.timezone.utc) >= until
    except Exception:
        return True




def vergil_chat_hash_for_audit(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()




def missing_order_client_context(queue: list[str]) -> tuple[str, str]:
    names = "; ".join(queue)
    names_key = hashlib.sha1(names.lower().encode("utf-8")).hexdigest()[:16]
    return names, names_key


def missing_order_calendar_payload(queue: list[str], names: str, names_key: str) -> dict:
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    return {
        "source": "caseforge-chat-missing-order",
        "mode": "poll",
        "client_names": list(queue),
        "client_filter": names,
        "folders": "Inbox,SentItems",
        "since_days": 30,
        "top": 50,
        "max_messages": 50,
        "dry_run": False,
        "allow_write": True,
        "idempotency_key": f"calendar-finder:missing-order:{today}:{names_key}",
    }


def missing_order_download_prompt(names: str) -> str:
    return (
        "Use tasks/order-intake/AGENT.md. Missing order downloader only for CLIENTS: "
        f"{names}. For each client, resolve the matter and find/download or file the latest incoming court order, "
        "sealed order, directions order, or hearing notice from mailbox/live matter storage. Stop after the downloader "
        "phase: do not draft client emails, counsel requests, service emails, bundle tasks, or calendar changes. "
        "Do not prepare Outlook drafts in this step. List exact saved/downloaded/live order locations and blockers."
    )


def missing_order_client_draft_prompt(names: str) -> str:
    return (
        "Use tasks/order-intake/AGENT.md. Draft order to client workflow for CLIENTS: "
        f"{names}. For each client, use the latest verified order/hearing notice already downloaded/filed by the "
        "Missing Order downloader or found in the live matter Court Orders folder. Prepare Outlook draft only; "
        "human sends after review. Address the draft to the recorded client email with the verified order attached. "
        "Do not run calendar-finder, do not create or update calendar entries, and do not draft "
        "counsel/service follow-up in this step. List draft locations, attachment/order locations, and blockers."
    )


def missing_order_sos_court_prompt(names: str) -> str:
    return (
        "Use tasks/order-intake/AGENT.md and context/emails.md. Draft Statement of Service to court workflow for CLIENTS: "
        f"{names}. For each client, find the latest Statement of Service / SOS from mailbox or live matter storage, "
        "verify the court email from the order/live matter/sent precedent, and verify the recorded client email for BCC. "
        "Prepare Outlook draft only; human sends after review. Only create the draft when the court email, client BCC "
        "address, SOS attachment, matter identity, and C8/protected-address safety checks are all verified. If any fact "
        "is missing or ambiguous, do not create the draft; list the blocker. Do not put the client in To or CC. Do not "
        "include protected applicant addresses in the body, subject, filename, or attachment description. Report draft "
        "location, SOS attachment location, and blockers."
    )



BRIEFING_ORDER_RE = re.compile(
    r"\b("
    r"sealed order|order attached|general form of order|directions order|"
    r"hearing notice|notice of hearing|return hearing|non-molestation order|"
    r"occupation order|child arrangements order|court order|order"
    r")\b",
    re.I,
)
BRIEFING_ARCHIVE_CATEGORIES = {"clients", "court", "counsel", "drug test labs"}


def briefing_row_text(row: Mapping) -> str:
    parts: list[str] = []
    for field in ("subject", "category", "from", "source_folder"):
        value = row.get(field)
        if value:
            parts.append(str(value))
    for field in ("score_reasons", "score_flags"):
        values = row.get(field)
        if isinstance(values, list):
            parts.extend(str(value) for value in values if value)
    return " ".join(parts)


def briefing_row_client(row: Mapping) -> str:
    return normalise_space(str(row.get("client_match") or row.get("client") or "")).strip(" .,:;")


def looks_like_incoming_order_row(row: Mapping) -> bool:
    client = briefing_row_client(row)
    if not client:
        return False
    source_folder = str(row.get("source_folder") or "").strip().lower()
    if source_folder and source_folder not in {"inbox", "sentitems"}:
        return False
    text = briefing_row_text(row)
    if not BRIEFING_ORDER_RE.search(text):
        return False
    return bool(row.get("has_attachments")) or "hearing notice" in text.lower() or "notice of hearing" in text.lower()


def looks_like_missing_email_archive_row(row: Mapping) -> bool:
    client = briefing_row_client(row)
    if not client:
        return False
    if not str(row.get("proposed_destination_folder") or "").strip():
        return False
    source_folder = str(row.get("source_folder") or "").strip().lower()
    if source_folder and source_folder not in {"inbox", "sentitems"}:
        return False
    category = str(row.get("category") or "").strip().lower()
    return category in BRIEFING_ARCHIVE_CATEGORIES




def vergil_chat_runtime_prefix(username: str | None, auto_approve: bool) -> str:
    sql_status = ""
    if not is_sql_available():
        until = sql_cooldown_until()
        sql_status = (
            f"IMPORTANT: the client database is unavailable until {until}. "
            "Do NOT attempt any client database connection or run any clientdb_sql code. "
            "Skip any workflow step that needs the client database and continue with available data.\n"
        )
    return (
        "[CaseForge CHAT RUNTIME]\n"
        "You are running inside caseforge-chat, the Streamlit UI, as a non-interactive subprocess.\n"
        f"User: {username or 'unknown'}.\n"
        f"Mode: {'auto-approve — all tools available without prompting' if auto_approve else 'supervised'}.\n"
        + sql_status +
        "Available local tools include shell/Bash and existing repository Python tools. "
        "Bash is available; do not assume otherwise. Use existing tools under tools/ for Graph, "
        "document, and telemetry work where possible.\n"
        "Credentials are already supplied through the subprocess environment when available; "
        "do not read, print, cat, grep, or inspect .secrets files directly.\n"
        "Workflow: when doing operational work, read the relevant task AGENT.md or workflow doc first "
        "(tasks/AGENTS.md holds the casework rules). Do not use subagents or interactive prompts; this subprocess cannot "
        "coordinate them. If a command or API call fails, report the error and avoid retry loops.\n"
        "Output style: do not narrate which files you are reading or tools you are calling. "
        "Read silently and deliver the result directly to the user.\n\n"
    )


AUTO_HEAVY_FIRST = ["Claude Sonnet", "Claude"]
AUTO_LIGHT_FIRST = ["Claude", "Claude Sonnet"]
AUTO_ROUTE_TIMEOUTS = {
    "tool": 60,
    "claude": 300,
    "claude sonnet": 300,
    "manual": 600,
}


def resolve_route(prompt: str, selected_model: str, provider_state: dict | None = None) -> dict:
    from vergil.attendance import (
        looks_like_attendance_note_request,
        looks_like_mixed_or_multi_attendance_workflow,
    )

    def _avail(key: str) -> bool:
        return provider_state is None or is_model_available(key, provider_state)

    def _route_model(model_key: str, reason: str, kind: str = "model", label_prefix: str = "Auto ->") -> dict:
        route_key = model_key.split("(", 1)[0].strip().lower()
        display_model = display_model_name(model_key).split("(", 1)[0].strip()
        return {
            "kind": kind,
            "model": model_key,
            "label": f"{label_prefix} {display_model}".strip(),
            "reason": reason,
            "timeout_seconds": AUTO_ROUTE_TIMEOUTS.get(route_key, AUTO_ROUTE_TIMEOUTS["manual"]),
        }

    def _first_available(preferred: list[str], reason: str) -> dict:
        for model_key in preferred:
            if _avail(model_key):
                return _route_model(model_key, reason)
        return {
            "kind": "tool",
            "model": None,
            "label": "Auto -> Tool",
            "reason": "All configured models are marked rate-limited; deterministic tools only",
            "timeout_seconds": AUTO_ROUTE_TIMEOUTS["tool"],
        }

    if selected_model != "Auto":
        return _route_model(selected_model, "Manual model override", kind="manual", label_prefix="")

    text = prompt_lower(prompt)
    if admin_audit_intent(text):
        return {
            "kind": "tool",
            "model": None,
            "label": "Auto -> Tool",
            "reason": "Supervisor audit request",
            "timeout_seconds": AUTO_ROUTE_TIMEOUTS["tool"],
        }
    gate_intent = ai_helpers.deterministic_intent(prompt)
    if gate_intent in {"destructive_gate", "c8_gate", "permissions"}:
        return {
            "kind": "tool",
            "model": None,
            "label": "Auto -> Tool",
            "reason": f"Deterministic safety gate: {gate_intent}",
            "timeout_seconds": AUTO_ROUTE_TIMEOUTS["tool"],
        }

    if looks_like_legal_aid_signing_request(prompt):
        return {
            "kind": "tool",
            "model": None,
            "label": "Auto -> Tool",
            "reason": "Legal Aid signing draft",
            "timeout_seconds": 120,
        }

    if looks_like_mixed_or_multi_attendance_workflow(prompt):
        return _route_model(AUTO_LIGHT_FIRST[0], "Mixed attendance-note model route")

    if looks_like_notice_of_acting_request(prompt):
        return {
            "kind": "tool",
            "model": None,
            "label": "Auto -> Tool",
            "reason": "Approved Notice of Acting route",
            "timeout_seconds": AUTO_ROUTE_TIMEOUTS["tool"],
        }

    if looks_like_attendance_note_request(prompt):
        return _route_model(AUTO_LIGHT_FIRST[0], "Attendance-note model route")

    if status_helper.looks_like_status_prompt(prompt):
        return {
            "kind": "tool",
            "model": None,
            "label": "Auto -> Tool",
            "reason": "Factual case snapshot",
            "timeout_seconds": AUTO_ROUTE_TIMEOUTS["tool"],
        }
    if looks_like_client_lookup_request(prompt):
        if is_sql_available():
            return {
                "kind": "tool",
                "model": None,
                "label": "Auto -> Tool",
                "reason": "Local client DB search",
                "timeout_seconds": AUTO_ROUTE_TIMEOUTS["tool"],
            }
        until = sql_cooldown_until()
        reason = f"SQL cooldown (until {until}) — AI Graph/email search" if until else "SQL cooldown — AI Graph/email search"
        return _first_available(AUTO_LIGHT_FIRST, reason)

    if looks_like_ccl_drafting_request(prompt):
        return {
            "kind": "tool",
            "model": None,
            "label": "Auto -> Tool",
            "reason": "Client care letters are made in Case Flow",
            "answer": ccl_only_in_case_flow_reply(),
            "timeout_seconds": AUTO_ROUTE_TIMEOUTS["tool"],
        }

    if looks_like_code_task(prompt):
        return _first_available(AUTO_HEAVY_FIRST, "Code or repo task")
    if looks_like_complex_matter_workflow(prompt):
        return _first_available(AUTO_HEAVY_FIRST, "Complex matter workflow")
    if looks_like_drafting_task(prompt):
        return _first_available(AUTO_HEAVY_FIRST, "Drafting or multi-step workflow task")
    if looks_like_tool_task(prompt):
        return {
            "kind": "tool",
            "model": None,
            "label": "Auto -> Tool",
            "reason": "Deterministic quick lookup",
            "timeout_seconds": AUTO_ROUTE_TIMEOUTS["tool"],
        }
    assisted = ai_helpers.route_intent(prompt)
    if assisted.get("source") in {"codex", "nano", "api"}:
        intent = str(assisted.get("intent") or "")
        source_label = "Codex-assisted" if assisted.get("source") == "codex" else "Small-model-assisted"
        if intent in {"case_snapshot", "client_search", "hearing_lookup", "time_date", "todo_lookup"}:
            return {
                "kind": "tool",
                "model": None,
                "label": "Auto -> Tool",
                "reason": f"{source_label} route: {intent}",
                "timeout_seconds": AUTO_ROUTE_TIMEOUTS["tool"],
            }
        if intent in {"drafting", "bundle", "email"}:
            return _first_available(
                AUTO_HEAVY_FIRST,
                f"{source_label} route: {intent}",
            )
    return _first_available(AUTO_HEAVY_FIRST, "Default heavy route")
