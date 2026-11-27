#!/usr/bin/env python3
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = REPO_ROOT / "runtime-data" / "model-roles.env"
REGISTRY_ENV_VAR = "CASEFORGE_MODEL_ROLES_FILE"

TIER_SMALL = "small"
TIER_LARGE = "large"

ROLE_CASE_SUMMARY = "case_summary"
ROLE_CHRONOLOGY = "chronology"
ROLE_CCL_DRAFT = "ccl_draft"
ROLE_CCL_ESCALATION = "ccl_escalation"
ROLE_CCL_FIELD_CHECK = "ccl_field_check"
ROLE_INTRO_AUDIT = "intro_audit"
ROLE_FACT_RECONCILER = "fact_reconciler"
ROLE_CLIENT_LETTER = "client_letter"
ROLE_BRIEF_TO_COUNSEL = "brief_to_counsel"
ROLE_EMAIL_TASK_TRIAGE = "email_task_triage"
ROLE_ORDER_TYPE_TAGS = "order_type_tags"
ROLE_MATTER_FACTS = "matter_facts"
ROLE_MATTER_INCIDENTS = "matter_incidents"
ROLE_MATTER_TIMELINE = "matter_timeline"
ROLE_FORM_FILL_STRONG = "form_fill_strong"
ROLE_FORM_FILL_CHEAP = "form_fill_cheap"
ROLE_AN_DRAFT = "an_draft"
ROLE_AN_MEMO_CLASSIFIER = "an_memo_classifier"
ROLE_OPENING_LETTER = "opening_letter"
ROLE_VERGIL_CHAT = "vergil_chat"
ROLE_CHAT_CHITCHAT = "chat_chitchat"
ROLE_CHAT_HELPERS = "chat_helpers"
ROLE_CHAT_TITLE = "chat_title"
ROLE_RETRIEVAL_ANSWER = "retrieval_answer"
ROLE_RETRIEVAL_ANSWER_DEEP = "retrieval_answer_deep"
ROLE_SAFETY_GUARD = "safety_guard"
ROLE_SAFETY_GUARD_FALLBACK = "safety_guard_fallback"
ROLE_MAIL_TRIAGE = "mail_triage"
ROLE_MAIL_ESCALATION = "mail_escalation"
ROLE_EMAIL_PDF_LABEL = "email_pdf_label"
ROLE_SCANNED_DOCS_TRIAGE = "scanned_docs_triage"
ROLE_NOTICE_OF_ACTING = "notice_of_acting"
ROLE_REFERRALPARTNER_INTAKE = "referralpartner_intake"
ROLE_STATEMENT_POSTCODE = "statement_postcode"
ROLE_NAME_EXTRACTOR = "name_extractor"
ROLE_HEARING_EXTRACT = "hearing_extract"
ROLE_CALENDAR_FINDER = "calendar_finder"
ROLE_HEARING_JUDGE = "hearing_judge"
ROLE_SPELLING_TIEBREAK = "spelling_tiebreak"
ROLE_SPELLING_SECOND = "spelling_second"
ROLE_COMPLIANCE_TEST = "compliance_test"
ROLE_VISION = "vision"
ROLE_URGENT_REVIEW = "urgent_review"
ROLE_AMEND_PLANNER = "amend_planner"
ROLE_AMEND_WORKER = "amend_worker"
ROLE_AMEND_QUESTIONER = "amend_questioner"
ROLE_AMEND_EDITOR = "amend_editor"
ROLE_AMEND_CRITIC = "amend_critic"
ROLE_AMEND_JUDGE = "amend_judge"
ROLE_AMEND_SMALL = "amend_small"
ROLE_AMEND_LARGE = "amend_large"

ROLE_TIERS: dict[str, str] = {
    ROLE_CASE_SUMMARY: TIER_LARGE,
    ROLE_CHRONOLOGY: TIER_LARGE,
    ROLE_CCL_DRAFT: TIER_LARGE,
    ROLE_CCL_ESCALATION: TIER_LARGE,
    ROLE_CCL_FIELD_CHECK: TIER_SMALL,
    ROLE_INTRO_AUDIT: TIER_SMALL,
    ROLE_FACT_RECONCILER: TIER_LARGE,
    ROLE_CLIENT_LETTER: TIER_LARGE,
    ROLE_BRIEF_TO_COUNSEL: TIER_LARGE,
    ROLE_EMAIL_TASK_TRIAGE: TIER_LARGE,
    ROLE_ORDER_TYPE_TAGS: TIER_LARGE,
    ROLE_MATTER_FACTS: TIER_LARGE,
    ROLE_MATTER_INCIDENTS: TIER_SMALL,
    ROLE_MATTER_TIMELINE: TIER_SMALL,
    ROLE_FORM_FILL_STRONG: TIER_LARGE,
    ROLE_FORM_FILL_CHEAP: TIER_SMALL,
    ROLE_AN_DRAFT: TIER_LARGE,
    ROLE_AN_MEMO_CLASSIFIER: TIER_SMALL,
    ROLE_OPENING_LETTER: TIER_LARGE,
    ROLE_VERGIL_CHAT: TIER_LARGE,
    ROLE_CHAT_CHITCHAT: TIER_SMALL,
    ROLE_CHAT_HELPERS: TIER_SMALL,
    ROLE_CHAT_TITLE: TIER_SMALL,
    ROLE_RETRIEVAL_ANSWER: TIER_SMALL,
    ROLE_RETRIEVAL_ANSWER_DEEP: TIER_LARGE,
    ROLE_SAFETY_GUARD: TIER_SMALL,
    ROLE_SAFETY_GUARD_FALLBACK: TIER_SMALL,
    ROLE_MAIL_TRIAGE: TIER_SMALL,
    ROLE_MAIL_ESCALATION: TIER_LARGE,
    ROLE_EMAIL_PDF_LABEL: TIER_SMALL,
    ROLE_SCANNED_DOCS_TRIAGE: TIER_SMALL,
    ROLE_NOTICE_OF_ACTING: TIER_SMALL,
    ROLE_REFERRALPARTNER_INTAKE: TIER_SMALL,
    ROLE_STATEMENT_POSTCODE: TIER_SMALL,
    ROLE_NAME_EXTRACTOR: TIER_SMALL,
    ROLE_HEARING_EXTRACT: TIER_SMALL,
    ROLE_CALENDAR_FINDER: TIER_SMALL,
    ROLE_HEARING_JUDGE: TIER_LARGE,
    ROLE_SPELLING_TIEBREAK: TIER_SMALL,
    ROLE_SPELLING_SECOND: TIER_LARGE,
    ROLE_COMPLIANCE_TEST: TIER_LARGE,
    ROLE_VISION: TIER_SMALL,
    ROLE_URGENT_REVIEW: TIER_LARGE,
    ROLE_AMEND_PLANNER: TIER_LARGE,
    ROLE_AMEND_WORKER: TIER_LARGE,
    ROLE_AMEND_QUESTIONER: TIER_LARGE,
    ROLE_AMEND_EDITOR: TIER_LARGE,
    ROLE_AMEND_CRITIC: TIER_LARGE,
    ROLE_AMEND_JUDGE: TIER_LARGE,
    ROLE_AMEND_SMALL: TIER_SMALL,
    ROLE_AMEND_LARGE: TIER_LARGE,
}
ROLES = tuple(ROLE_TIERS)

OPENROUTER = "openrouter"


class ModelRoleError(RuntimeError):
    pass


_cache_lock = threading.Lock()
_cache: dict[str, tuple[tuple[int, int], dict[str, str]]] = {}


def registry_path() -> Path:
    override = (os.environ.get(REGISTRY_ENV_VAR) or "").strip()
    return Path(override) if override else DEFAULT_REGISTRY_PATH


def parse_registry(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        if key:
            out[key] = value.strip()
    return out


def load_registry() -> dict[str, str]:
    path = registry_path()
    try:
        stat = path.stat()
    except OSError:
        return {}
    signature = (stat.st_mtime_ns, stat.st_size)
    key = str(path)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] == signature:
            return dict(hit[1])
    try:
        entries = parse_registry(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    with _cache_lock:
        _cache[key] = (signature, entries)
    return dict(entries)


OVERRIDES_ENV_VAR = "CASEFORGE_MODEL_OVERRIDES_FILE"
OVERRIDES_FILENAME = "model-role-overrides.json"
_overrides_cache: dict[str, tuple[tuple[int, int], dict[str, str]]] = {}


def overrides_path() -> Path:
    explicit = (os.environ.get(OVERRIDES_ENV_VAR) or "").strip()
    if explicit:
        return Path(explicit)
    try:
        import ops_db

        configured = ops_db.configured_ops_db_path()
        if configured:
            return Path(configured).parent / OVERRIDES_FILENAME
    except Exception:
        pass
    return REPO_ROOT / "ops" / OVERRIDES_FILENAME


def load_overrides() -> dict[str, str]:
    import json

    path = overrides_path()
    try:
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        with _cache_lock:
            hit = _overrides_cache.get(str(path))
        if hit and hit[0] == signature:
            return dict(hit[1])
        raw = json.loads(path.read_text(encoding="utf-8")).get("roles")
    except (OSError, ValueError, AttributeError):
        return {}
    entries = {r: str(m).strip() for r, m in raw.items() if r in ROLE_TIERS and str(m).strip()} if isinstance(raw, dict) else {}
    with _cache_lock:
        _overrides_cache[str(path)] = (signature, entries)
    return dict(entries)


def write_overrides(entries: dict[str, str]) -> Path:
    import json

    path = overrides_path()
    if not entries:
        path.unlink(missing_ok=True)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"roles": dict(sorted(entries.items()))}, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def _lookup(key: str) -> Optional[tuple[str, str]]:
    env_value = (os.environ.get(key) or "").strip()
    if env_value:
        return env_value, "env"
    file_value = (load_registry().get(key) or "").strip()
    if file_value:
        return file_value, "file"
    return None


def role_key(role: str, backend: str = OPENROUTER) -> str:
    return f"CASEFORGE_MODEL_{role.upper()}" if backend == OPENROUTER else f"CASEFORGE_MODEL_{backend.upper()}_{role.upper()}"


def resolve(role: str, backend: str = OPENROUTER, *, active: bool = True) -> tuple[str, str]:
    if role not in ROLE_TIERS:
        raise ValueError(f"unknown role {role!r}; expected one of {ROLES}")
    backend = backend.lower()
    registry = load_registry()
    env_keys = [f"CASEFORGE_MODEL_{backend.upper()}_{role.upper()}"]
    if active:
        env_keys.append(f"CASEFORGE_MODEL_{role.upper()}")
    if backend != OPENROUTER:
        env_keys.append(f"CASEFORGE_MODEL_{backend.upper()}_{ROLE_TIERS[role].upper()}")
    for key in env_keys:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value, f"env:{key}"
    if backend == OPENROUTER:
        override = load_overrides().get(role)
        if override:
            return override, f"override:{role_key(role)}"
    file_keys = [f"CASEFORGE_MODEL_{backend.upper()}_{role.upper()}"]
    if backend == OPENROUTER:
        file_keys.append(f"CASEFORGE_MODEL_{role.upper()}")
    else:
        file_keys.append(f"CASEFORGE_MODEL_{backend.upper()}_{ROLE_TIERS[role].upper()}")
    for key in file_keys:
        value = (registry.get(key) or "").strip()
        if value:
            return value, f"file:{key}"
    raise ModelRoleError(
        f"no model set for role {role!r} on backend {backend!r}: set {file_keys[-1] if backend != OPENROUTER else role_key(role)} "
        f"in {registry_path()} (or as an environment variable)"
    )


def set_role(role: str, model: str, backend: str = OPENROUTER, path: Optional[Path] = None) -> Path:
    if role not in ROLE_TIERS:
        raise ValueError(f"unknown role {role!r}; expected one of {ROLES}")
    model = model.strip()
    if not model or any(ch.isspace() for ch in model) or "=" in model:
        raise ValueError(f"not a model id: {model!r}")
    target = path or registry_path()
    key = role_key(role, backend.lower())
    lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    replaced = False
    for index, line in enumerate(lines):
        if line.strip().partition("=")[0].strip() == key:
            lines[index] = f"{key}={model}"
            replaced = True
    if not replaced:
        lines.append(f"{key}={model}")
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target
