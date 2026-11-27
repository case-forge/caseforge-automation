from __future__ import annotations

import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from vergil import tool_verbs
from vergil.retrieval import (
    CarriedScope,
    RetrievalContext,
    RetrievalStep,
    StepCallback,
    retrieve,
)

MODEL_FAILURE_TEXT = "I could not answer this just now. Please try again shortly."
MODEL_FAILURE_GAP = "The answer could not be generated this time."

EXPOSURE_BLOCK_TEXT = (
    "I have stopped this lookup because it would show more client records at once "
    "than this account is allowed to see. This limit exists to contain bulk "
    "disclosure of client data. Please narrow the question to a specific client "
    "or matter, or ask the supervising solicitor if you genuinely need a wider view."
)
EXPOSURE_BLOCK_ROLLING_TEXT = (
    "I have stopped this lookup because this account has already reached its "
    "rolling 24-hour limit on distinct client/matter lookups through this chat. "
    "This is about the account's total lookups today, not this specific "
    "question -- narrowing it will not help. Please wait for the limit to "
    "reset, or ask the supervising solicitor if it needs to be lifted sooner."
)
EXPOSURE_BLOCK_GAP = (
    "Stopped by the client-exposure limit before any client details were shown."
)


def _exposure_block_text(categories: list) -> str:
    from vergil.user_state import blocked_by_rolling_window_only

    if blocked_by_rolling_window_only(categories):
        return EXPOSURE_BLOCK_ROLLING_TEXT
    return EXPOSURE_BLOCK_TEXT


def _enforce_exposure(username: str, rows: list, *, source: str) -> dict:
    from vergil.user_state import enforce_client_exposure_budget

    return enforce_client_exposure_budget(username, rows, source=source)

MODEL_VERB = "Writing the answer"

MAX_PRIOR_TURNS = 2


@dataclass
class InternAnswer:

    text: str
    ok: bool
    served_by: str = ""
    model: str = ""
    matter_id: Optional[str] = None
    client_name: str = ""
    client_email: str = ""
    carried_over_from: str = ""
    sources_checked: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    steps: list[RetrievalStep] = field(default_factory=list)
    elapsed_seconds: float = 0.0


def prompt_context(
    context: RetrievalContext, *, prior_turns: Optional[list[dict]] = None
) -> dict[str, Any]:
    return {
        "matter_id": context.matter_id,
        "sql_hits": context.sql_hits,
        "rag_hits": context.prompt_rag_hits,
        "graph_listing": context.graph_listing,
        "mail_hits": context.mail_hits,
        "sources_checked": checked_labels(context.steps),
        "gaps": [tool_verbs.gap_for(gap) for gap in context.gaps],
        "prior_turns": list(prior_turns or [])[-MAX_PRIOR_TURNS:],
        "carried_over_from": context.carried_client_name if context.carried_over else "",
        "resolved_via_rag": context.resolved_via_rag,
    }


def client_name_for(context: RetrievalContext) -> str:
    return context.client_name


def answer(
    question: str,
    *,
    role: str = "",
    request_id: str = "",
    username: str = "",
    on_step: Optional[StepCallback] = None,
    engine: Any = None,
    runner: Any = None,
    carried_scope: Optional[CarriedScope] = None,
    prior_turns: Optional[list[dict]] = None,
) -> InternAnswer:
    from retrieval_engine import engine as default_engine
    import model_backend

    role = role or default_engine.DEFAULT_MODEL_ROLE
    run_model = runner or model_backend.run_model
    started = time.monotonic()

    context = retrieve(question, on_step=on_step, engine=engine, carried_scope=carried_scope)

    if username:
        exposure = _enforce_exposure(username, context.sql_hits, source="retrieval_answer")
        if exposure.get("block"):
            return InternAnswer(
                text=_exposure_block_text(exposure.get("categories")),
                ok=False,
                matter_id=context.matter_id,
                sources_checked=context.sources_checked,
                gaps=list(context.gaps) + [EXPOSURE_BLOCK_GAP],
                steps=context.steps,
                elapsed_seconds=round(time.monotonic() - started, 2),
            )
    as_dict = prompt_context(context, prior_turns=prior_turns)
    backend = model_backend.backend_order(role, backend=default_engine.MODEL_BACKEND, fallbacks=[])[0]
    as_dict["mail_hits"], mail_gap = default_engine.mail_hits_for_backend(as_dict["mail_hits"], backend)
    if mail_gap:
        as_dict["gaps"] = list(as_dict["gaps"]) + [tool_verbs.gap_for(mail_gap)]
        context.gaps.append(mail_gap)
    prompt = default_engine.render_prompt(question, as_dict)

    _emit(context, on_step, RetrievalStep("model", MODEL_VERB, "running"))
    model_started = time.monotonic()
    result = run_model(
        role,
        prompt,
        backend=default_engine.MODEL_BACKEND,
        fallbacks=[],
        timeout=default_engine.ANSWER_TIMEOUT_SECONDS,
        request_id=request_id or uuid.uuid4().hex[:12],
    )
    model_ms = int((time.monotonic() - model_started) * 1000)
    elapsed = time.monotonic() - started

    gaps = list(context.gaps)
    text = result.text
    if not result.ok:
        for attempt in getattr(result, "attempts", []):
            print(
                f"[retrieval_answer] model attempt failed: "
                f"{attempt.backend}:{attempt.model}: {attempt.error}",
                file=sys.stderr,
            )
        text = MODEL_FAILURE_TEXT
        gaps = gaps + [MODEL_FAILURE_GAP]
        _emit(context, on_step, RetrievalStep(
            "model", MODEL_VERB, "error", detail="failed (see server log)",
            elapsed_ms=model_ms,
        ))
    else:
        _emit(context, on_step, RetrievalStep(
            "model", MODEL_VERB, "hit", detail=result.served_by, elapsed_ms=model_ms,
        ))

    try:
        default_engine._record_event(as_dict, result, elapsed)
    except Exception:
        pass

    return InternAnswer(
        text=text,
        ok=bool(result.ok),
        served_by=getattr(result, "served_by", ""),
        model=getattr(result, "model", ""),
        matter_id=context.matter_id,
        client_name=client_name_for(context),
        client_email=context.client_email,
        carried_over_from=context.carried_client_name if context.carried_over else "",
        sources_checked=context.sources_checked,
        gaps=gaps,
        steps=context.steps,
        elapsed_seconds=round(elapsed, 2),
    )


def checked_labels(steps: list[RetrievalStep]) -> list[str]:
    seen: list[str] = []
    for step in steps:
        if step.status in {"skipped", "declined"}:
            continue
        verb = step.verb or ""
        if verb and verb not in seen:
            seen.append(verb)
    return seen


def step_outcome(step: RetrievalStep) -> str:
    verb = step.verb
    if step.status == "skipped":
        return f"{verb}: not needed"
    if step.status == "declined":
        return f"{verb}: {step.detail or 'not applicable this turn'}"
    if step.status == "error":
        return f"{verb}: unavailable this turn"
    if step.status == "empty":
        return f"{verb}: nothing found"
    if step.source == "model":
        return f"{verb}: done"
    suffix = f" ({step.count})" if step.count else ""
    return f"{verb}: found{suffix}"


def _emit(
    context: RetrievalContext, on_step: Optional[StepCallback], step: RetrievalStep
) -> None:
    context.steps.append(step)
    if on_step is None:
        return
    try:
        on_step(step)
    except Exception:
        pass
