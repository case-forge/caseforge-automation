
from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import model_backend
from documents import note_proofread

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TickOption:
    id: str
    label: str
    fact: str


@dataclass(frozen=True)
class TickGroup:
    id: str
    heading: str | None
    options: tuple[TickOption, ...]
    stock_answers: tuple[str, ...] = ()
    collapsible: bool = False


_COURT_PROCESS_ANSWERS: tuple[str, ...] = (
    "The court moves at its own pace.",
    "We don't know when the next hearing is.",
    "We will inform them the moment we know.",
    "We will send them the order the moment we get it, and send it off to serve the Respondent.",
    "It's their statement -- they can modify it how they wish, so long as they sign and send it back to us.",
)

TICK_GROUPS: tuple[TickGroup, ...] = (
    TickGroup(
        id="asked_whether",
        heading="Client asked whether",
        options=(
            TickOption(
                "received_email", "we received their email",
                "Client asked whether we had received their email.",
            ),
            TickOption(
                "evidence_needed", "further evidence was needed",
                "Client asked whether further evidence was needed.",
            ),
            TickOption(
                "evidence_can_send", "they could send further evidence",
                "Client asked whether they could send further evidence.",
            ),
            TickOption(
                "ws_edit_statement", "they could edit their witness statement",
                "Client asked whether they could edit their witness statement.",
            ),
            TickOption(
                "order_arrived", "the order had arrived from court",
                "Client asked whether the order had arrived from court.",
            ),
            TickOption(
                "respondent_served", "the respondent had been served",
                "Client asked whether the respondent had been served.",
            ),
            TickOption(
                "bring_witnesses", "they need to bring witnesses",
                "Client asked whether they need to bring witnesses.",
            ),
        ),
        stock_answers=_COURT_PROCESS_ANSWERS,
    ),
    TickGroup(
        id="court",
        heading="Court",
        options=(
            TickOption("must_attend", "must I attend", "Client asked whether they have to attend court."),
            TickOption(
                "respondent_attending", "will the respondent be there",
                "Client asked whether the respondent will be at the hearing.",
            ),
            TickOption(
                "has_clash", "they have a clash / are not in the area",
                "Client said they have a scheduling clash or are not in the area for the hearing.",
            ),
        ),
        stock_answers=_COURT_PROCESS_ANSWERS,
    ),
    TickGroup(
        id="respondent_status",
        heading="Respondent",
        collapsible=True,
        options=(
            TickOption(
                "resp_served", "have they been served",
                "The Respondent has been served.",
            ),
            TickOption(
                "resp_attending", "will they attend court",
                "The Respondent is expected to attend the hearing.",
            ),
            TickOption(
                "resp_breaching_order", "they're breaching the order",
                "The Respondent is breaching the order currently in force.",
            ),
            TickOption(
                "resp_harassing_no_order", "they're harassing me (no order)",
                "Client said the Respondent is harassing them; no order is currently in place.",
            ),
        ),
    ),
    TickGroup(
        id="client_evidence",
        heading="Client",
        collapsible=True,
        options=(
            TickOption(
                "cli_evidence_sent", "sent more evidence",
                "Client said they sent further evidence.",
            ),
            TickOption(
                "cli_evidence_seen", "have we seen it",
                "Client asked whether we had seen the further evidence they sent.",
            ),
            TickOption(
                "cli_evidence_bring_more", "should they bring more evidence",
                "Client asked whether they should bring more evidence to court.",
            ),
        ),
    ),
    TickGroup(
        id="complaint",
        heading="Complaint about",
        options=(
            TickOption("complaint_firm", "the firm", "Client complained about the firm."),
            TickOption("complaint_barrister", "the barrister", "Client complained about the barrister."),
            TickOption("complaint_court_outcome", "the court outcome", "Client complained about the court outcome."),
        ),
    ),
    TickGroup(
        id="other",
        heading=None,
        options=(TickOption("said_thank_you", "said thank you", "Client called to say thank you."),),
    ),
)

TICK_FACTS: dict[str, str] = {opt.id: opt.fact for group in TICK_GROUPS for opt in group.options}
TICK_LABELS: dict[str, str] = {opt.id: opt.label for group in TICK_GROUPS for opt in group.options}

STRUCTURED_BODY_FIELDS = ("activity", "instructions_received", "advice_given", "action_agreed")
ACTIVITY_TODO_FIELDS = ("activity", "to_do")

_KIND_TEXT = {
    "letter_out": "a letter we sent",
    "letter_in": "a letter we received",
    "perusal": "time spent reading a letter we received",
    "preparation": "time spent preparing a letter we sent",
}

MAX_SOURCE_CHARS = 12_000


class AttendanceNoteDraftGooseError(RuntimeError):
    pass


class AttendanceNoteDraftCostRefusal(AttendanceNoteDraftGooseError):
    pass


def _ticked_facts(ticks: dict[str, bool]) -> list[str]:
    ticked_ids = {key for key, checked in (ticks or {}).items() if checked}
    return [fact for tid, fact in TICK_FACTS.items() if tid in ticked_ids]


def _activity_line(kind: str, party: str) -> str:
    party = " ".join(str(party or "").split())
    if kind in _KIND_TEXT:
        what = _KIND_TEXT[kind]
        return f"{what[:1].upper()}{what[1:]}" + (f" ({party})" if party else "")
    return f"Telephone call with {party}" if party else "Telephone call with the client"


def is_paper_kind(kind: str) -> bool:
    return kind in _KIND_TEXT


def is_pasted_document(text: str) -> bool:
    from documents import perusal_summary

    return perusal_summary.summarisable(note_proofread.split_sentences(text or ""))[0]


def _joined(*parts: str) -> str:
    texts = [" ".join(str(p or "").split()) for p in parts]
    texts = [t for t in texts if t]
    return " ".join(t if (i == len(texts) - 1 or t[-1] in ".!?") else f"{t}." for i, t in enumerate(texts))


def activity_todo(kind: str, party: str, fields: dict[str, str] | None = None) -> dict[str, str]:
    fields = fields or {}
    return {
        "activity": _joined(_activity_line(kind, party), fields.get("instructions_received", ""), fields.get("advice_given", ""), fields.get("note", "")),
        "to_do": " ".join(str(fields.get("action_agreed") or "").split()),
    }


def _ticks_only_fields(ticks: dict[str, bool], kind: str, party: str) -> dict[str, str]:
    fields = {
        "activity": _activity_line(kind, party),
        "instructions_received": " ".join(_ticked_facts(ticks)),
        "advice_given": "",
        "action_agreed": "",
    }
    return activity_todo(kind, party, fields) if is_paper_kind(kind) else fields


def _as_written(note_text: str, kind: str, party: str) -> dict[str, str]:
    if is_paper_kind(kind):
        return activity_todo(kind, party, {"note": (note_text or "").strip()})
    return {
        "activity": _activity_line(kind, party), "instructions_received": "", "advice_given": "", "action_agreed": "",
        "note": (note_text or "").strip(),
    }


PROOFREAD_FLAGS_KEY = "_proofread_flags"


def _run_model_bounded(prompt: str, *, model: str, max_tokens: int, timeout: float = 60) -> str:
    result = model_backend.run_model(
        model_backend.ROLE_AN_DRAFT, prompt, model=model, timeout=timeout, reasoning="low", max_tokens=max_tokens,
    )
    if result.ok:
        return result.text
    errors = "; ".join(attempt.error for attempt in result.attempts if attempt.error) or "no attempt was made"
    if any(attempt.refusal for attempt in result.attempts) or model_backend.is_cost_refusal_text(errors):
        raise AttendanceNoteDraftCostRefusal(f"AN draft refused for cost/credit: {errors[:500]}")
    raise AttendanceNoteDraftGooseError(f"AN draft failed: {errors[:500]}")


def draft_body_fields(
    *, ticks: dict[str, bool], note_text: str, backend: str | None = None, kind: str = "call", party: str = ""
) -> dict[str, str]:
    note = (note_text or "").strip()
    if not note:
        return _ticks_only_fields(ticks, kind, party)
    if is_paper_kind(kind) and is_pasted_document(note):
        log.info("AN draft: a pasted document on a %s note; the Activity line stands alone", kind)
        return activity_todo(kind, party)
    facts = _ticked_facts(ticks)
    if len("\n".join([*facts, note])) > MAX_SOURCE_CHARS:
        log.warning("AN draft: note of %d characters is too long for a model; filed as written", len(note))
        return _as_written(note, kind, party)
    model = model_backend.model_for_role(model_backend.ROLE_AN_DRAFT, backend=backend)
    max_tokens = min(8000, 3000 + 3 * len(note))
    result = note_proofread.proofread(
        [*facts, *note_proofread.split_sentences(note)], lambda prompt: _run_model_bounded(prompt, model=model, max_tokens=max_tokens),
    )
    flagged = {PROOFREAD_FLAGS_KEY: "; ".join(result.flags)} if result.flags else {}
    if all(item.as_typed for item in result.items):
        log.warning("AN draft: the model's reply changed the caseworker's text (%s); filed as written", "; ".join(result.flags)[:300])
        return {**_as_written(note, kind, party), **flagged}
    for flag in result.flags:
        log.warning("AN draft: %s", flag)
    fields = result.fields()
    if is_paper_kind(kind):
        return {**activity_todo(kind, party, fields), **flagged}
    return {"activity": _activity_line(kind, party), **fields, **flagged}
