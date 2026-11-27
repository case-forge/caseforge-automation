from __future__ import annotations

import contextlib
import contextvars
import os
from typing import Iterator

try:
    import env_names
except ImportError:
    from tools import env_names

PERSON, AGENT, AUTOMATION = "person", "agent", "automation"
KINDS = (PERSON, AGENT, AUTOMATION)
WORDS = {PERSON: "Person", AGENT: "Agent", AUTOMATION: "Automation"}
AUTOMATION_BY = frozenset({"auto", "case flow"})
AGENT_RUNTIME_LABELS = frozenset({"claude-cli", "codex-cli"})
ENV = "CASEFORGE_ACTOR_KIND"
HEADER = "X-CaseForge-Actor-Kind"

_REQUEST_KIND: contextvars.ContextVar[str] = contextvars.ContextVar("caseforge_actor_kind", default="")


def clean(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in KINDS else ""


@contextlib.contextmanager
def request_kind(kind: str) -> Iterator[None]:
    token = _REQUEST_KIND.set(clean(kind))
    try:
        yield
    finally:
        _REQUEST_KIND.reset(token)


def kind_for_request(remote_user: str, header_value: str) -> str:
    return PERSON if str(remote_user or "").strip() else clean(header_value)


def is_agent_process(env: dict[str, str] | None = None) -> bool:
    environ = os.environ if env is None else env
    return environ.get("CLAUDECODE", "").strip() == "1" or environ.get(env_names.RUNTIME_LABEL, "").strip().lower() in AGENT_RUNTIME_LABELS


def resolve(by: str = "", *, kind: str = "", env: dict[str, str] | None = None) -> str:
    explicit = clean(kind)
    if explicit:
        return explicit
    environ = os.environ if env is None else env
    names_case_flow = str(by or "").strip().lower() in AUTOMATION_BY
    in_request = _REQUEST_KIND.get()
    if in_request and not (names_case_flow and in_request == PERSON):
        return in_request
    declared = clean(environ.get(ENV, ""))
    if declared:
        return declared
    if is_agent_process(environ):
        return AGENT
    if names_case_flow:
        return AUTOMATION
    return ""


def for_stored(stored: str, by: str = "") -> str:
    return clean(stored) or (AUTOMATION if str(by or "").strip().lower() in AUTOMATION_BY else "")
