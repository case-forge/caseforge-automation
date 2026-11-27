#!/usr/bin/env python3
"MCP server exposing this repo's read-only lookup/health tools -- client and"
from __future__ import annotations

import argparse
import dataclasses
import functools
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
for sub in ("tools", "tools/documents", "tools/agents"):
    p = str(REPO_ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from mcp.server.mcpserver import MCPServer
from vergil import chat_session

mcp = MCPServer("caseforge-ops")

USAGE_LOG_PATH = REPO_ROOT / "telemetry" / "mcp-caseforge-ops-usage.jsonl"


def _record_usage(tool_name: str, *, ok: bool, error_type: str = "") -> None:
    "Length/name only, never arguments or results -- those can carry client PII."
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": tool_name,
        "ok": ok,
        "error_type": error_type,
    }
    try:
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from graph_mail_safe_ops import _append_jsonl_locked

        USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _append_jsonl_locked(USAGE_LOG_PATH, row)
    except Exception:
        pass


def _tracked(fn: Callable) -> Callable:
    "Wrap a tool function to log its invocation before returning its result."

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            _record_usage(fn.__name__, ok=False, error_type=type(exc).__name__)
            raise
        _record_usage(fn.__name__, ok=not (isinstance(result, dict) and "error" in result))
        return result

    return wrapper


def _asdict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _asdict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_asdict(v) for v in obj]
    return obj


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def check_ops_health(hours: int = 72, startup_days: int = 7) -> dict:
    "Run the operational supervisor over background automation (job queue,"
    from monitoring import ops_supervisor

    payload = ops_supervisor.evaluate_supervisor(hours=hours, startup_days=startup_days)
    operator_view = os.environ.get("CASEFORGE_OPS_FULL_HEALTH", "").strip().lower() in {"1", "true", "yes", "on"}
    if operator_view and not chat_session.in_chat():
        return payload
    return ops_supervisor.plain_health_view(payload)


def _hard_anchor_matter_id() -> str:
    "The matter id this MCP server subprocess is hard-anchored to, or ''."
    return chat_session.anchored_matter_id()


_HARD_ANCHOR_REFUSAL = (
    "This conversation is restricted to the client currently open in client "
    "viewer. Searching for, or discussing, a different client is not "
    "available here -- open that client's own record to start a new "
    "conversation about them."
)

_EXPOSURE_REFUSAL = (
    "The client-exposure limit for this service has been reached, so no client "
    "records can be returned for now. Say so plainly; do not guess at a client."
)


@mcp.tool()
@_tracked
def search_clients(query: str, limit: int = 6) -> dict:
    "Search CaseForge's client/matter database, retrying through the fuzzy name"
    if _hard_anchor_matter_id():
        return {"rows": [], "display_query": query, "was_fuzzy_resolved": False, "error": _HARD_ANCHOR_REFUSAL}

    import agwu
    from vergil.user_state import enforce_client_exposure_budget, mcp_budget_identity

    _result = agwu.resolve_client(query, limit=limit, caller="ops_mcp_server.search_clients")
    rows, display_query = [m.row for m in _result.matches], _result.display_query
    was_exact = bool(_result.top and "exact_search" in _result.top.match_sources)
    exposure = enforce_client_exposure_budget(mcp_budget_identity(), rows, source="mcp_search_clients")
    if exposure.get("block"):
        return {"rows": [], "display_query": query, "was_fuzzy_resolved": False, "error": _EXPOSURE_REFUSAL}
    from vergil import model_safe

    return model_safe.strip_c8_values({
        "rows": rows,
        "display_query": display_query,
        "was_fuzzy_resolved": not was_exact,
    })


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def matter_snapshot(query: str) -> dict:
    "What the system holds on one matter, in one read-only call: the folder pointer (from the cache),"
    from agwu.matter_snapshot import matter_snapshot as _snapshot
    from vergil import model_safe
    from vergil.user_state import enforce_client_exposure_budget, mcp_budget_identity

    snap = _snapshot(query, caller="ops_mcp_server.matter_snapshot")
    named = [{"matter_id": c["matter_id"], "client_name": c["client_name"]} for c in snap.candidates]
    if snap.matter_id:
        named.append({"matter_id": snap.matter_id, "client_name": snap.client_name})
    exposure = enforce_client_exposure_budget(mcp_budget_identity(), named, source="mcp_matter_snapshot")
    if exposure.get("block"):
        return {"status": "refused", "error": _EXPOSURE_REFUSAL}
    return model_safe.strip_c8_values(snap.as_dict())


@mcp.tool()
@_tracked
def retrieve_matter_context(question: str, matter_id: str = "") -> dict:
    "Run the same SQL -> RAG -> live-folder -> mailbox retrieval chain"
    from vergil.retrieval import CarriedScope, retrieve
    from vergil.user_state import enforce_client_exposure_budget, mcp_budget_identity

    anchor = _hard_anchor_matter_id()
    if anchor:
        carried_scope = CarriedScope(matter_id=anchor, hard=True)
    else:
        carried_scope = CarriedScope(matter_id=matter_id) if matter_id else None
    context = retrieve(question, carried_scope=carried_scope)
    exposure = enforce_client_exposure_budget(mcp_budget_identity(), context.sql_hits, source="mcp_retrieve_matter_context")
    if exposure.get("block"):
        return {"error": _EXPOSURE_REFUSAL, "sql_hits": [], "rag_hits": [], "mail_hits": [], "gaps": [_EXPOSURE_REFUSAL]}
    from vergil import model_safe

    def _row(mid: str) -> dict | None:
        from clientdb_sql import get_client_by_matter_id

        return get_client_by_matter_id(mid)

    return model_safe.strip_c8_values(_asdict(context), anchor or matter_id or str(getattr(context, "matter_id", "") or ""), lookup=_row)


@mcp.tool()
@_tracked
def get_matter_court(matter_id: str = "") -> dict:
    "The court a matter is proceeding in, as recorded for that matter -- the"
    from documents.court_of_record import get_courts

    mid = _hard_anchor_matter_id() or str(matter_id or "").strip()
    if not mid:
        return {"recorded": False, "court": "", "note": "matter_id is required -- resolve the client with search_clients first."}
    try:
        rows = [r for r in get_courts(mid) if r.get("court")]
    except Exception as exc:
        return {
            "matter_id": mid,
            "recorded": False,
            "court": "",
            **chat_session.failure(
                f"Court lookup failed: {type(exc).__name__}: {exc}",
                exc,
                plain="The court lookup isn't available just now.",
                where="get_matter_court",
            ),
        }
    if not rows:
        return {
            "matter_id": mid,
            "recorded": False,
            "court": "",
            "note": (
                "No court is recorded for this matter. Do not guess one. Read the matter's own "
                "FL401, witness statement or sealed order, or ask the caseworker which court."
            ),
        }

    def _source_kind(row: dict) -> str:
        return str(row.get("source") or "").split(":", 1)[0] or "unknown"

    result = {
        "matter_id": mid,
        "recorded": True,
        "court": rows[0]["court"],
        "source_kind": _source_kind(rows[0]),
    }
    if len(rows) > 1:
        result["conflict"] = True
        result["courts"] = [
            {"court": r["court"], "source_kind": _source_kind(r), "is_primary": bool(r.get("is_primary"))}
            for r in rows
        ]
        result["note"] = (
            f"The recorded sources disagree: {len(rows)} different courts are recorded for this matter. "
            "Do not pick one. Say which courts are recorded and ask the caseworker to confirm the court "
            "before it is named in any document or email."
        )
    return result


@mcp.tool()
@_tracked
@chat_session.refuse_in_chat
@chat_session.refuse_when_anchored
def check_letter_coverage(include_concluded: bool = False) -> dict:
    "Scan the local OneDrive index for which matters already have an"
    from documents.letter_coverage import DEFAULT_OPS_DB, scan

    if not DEFAULT_OPS_DB.exists():
        return {
            "error": (
                f"No OneDrive index at {DEFAULT_OPS_DB}. Build one with: "
                "python3 tools/graph_index.py refresh"
            )
        }
    matters = scan(DEFAULT_OPS_DB, include_concluded=include_concluded)
    return {"matters": _asdict(matters)}


_JOB_REASON_FOR_CHAT = {
    "failed": "The job failed. The team can see why.",
    "blocked": "The job is blocked and needs attention from the team.",
    "waiting_approval": "The job is waiting for approval.",
}


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def get_job_status(job_id: str) -> dict:
    "Look up one background job's current status by id. Read-only."
    from agents import job_queue

    job = job_queue.get_job(job_id)
    if job is None:
        return {"error": f"No job found with id: {job_id}"}
    if chat_session.in_chat():
        view = {key: job.get(key) for key in ("job_id", "job_type", "status", "created_utc", "updated_utc", "started_utc", "finished_utc")}
        reason = _JOB_REASON_FOR_CHAT.get(str(job.get("status") or ""))
        if reason:
            view["reason"] = reason
        return view
    return job


@mcp.tool()
@_tracked
@chat_session.refuse_in_chat
def list_recent_jobs(status: str = "", limit: int = 20, job_types: list[str] | None = None) -> dict:
    "List recent background jobs, newest first. Read-only."
    from agents import job_queue

    jobs = job_queue.list_jobs(status=status, limit=limit, job_types=tuple(job_types or ()))
    return {"jobs": jobs, "count": len(jobs)}


@mcp.tool()
@_tracked
@chat_session.refuse_in_chat
@chat_session.refuse_when_anchored
def list_job_events(job_id: str) -> dict:
    "List the event history for one background job. Read-only."
    from agents import job_queue

    return {"job_id": job_id, "events": job_queue.list_events(job_id)}


@mcp.tool()
@_tracked
@chat_session.refuse_in_chat
@chat_session.refuse_when_anchored
def list_job_artifacts(job_id: str) -> dict:
    "List the artifacts recorded against one background job. Read-only."
    from agents import job_queue

    return {"job_id": job_id, "artifacts": job_queue.list_artifacts(job_id)}


@mcp.tool()
@_tracked
@chat_session.refuse_in_chat
def check_tunnel_health(timeout: float = 4.0, skip_http: bool = False, check_subscriptions: bool = False) -> dict:
    "Check the health of the tunnel/webhook/service stack (systemd units,"
    from monitoring import tunnel_health

    return tunnel_health.build_payload(
        max(timeout, 1.0), skip_http, auto_repair=False, check_subscriptions=check_subscriptions
    )


@mcp.tool()
@_tracked
@chat_session.refuse_in_chat
def check_model_health() -> dict:
    "Report the last-known health/outage state for each configured model."
    from monitoring import model_health
    from vergil.model_provider import MODEL_HEALTH_FILE, MODEL_OPTIONS

    stored = model_health.load_health(MODEL_HEALTH_FILE)
    return model_health.build_health_snapshot(MODEL_OPTIONS, stored_health=stored)


@mcp.tool()
@_tracked
@chat_session.refuse_when_anchored
def check_openrouter_spend() -> dict:
    "Fetch current OpenRouter spend/credit numbers. Read-only."
    from monitoring.openrouter_spend import OpenRouterFetchError, fetch_spend

    try:
        spend = fetch_spend()
    except OpenRouterFetchError as exc:
        return chat_session.failure(str(exc), exc, plain="Spend figures are unavailable right now.", where="check_openrouter_spend")
    if chat_session.in_chat():
        return {key: spend.get(key) for key in ("total_credits", "total_usage", "key_usage", "key_limit", "key_limit_remaining", "fetched_at")}
    return spend


@mcp.tool()
@_tracked
@chat_session.refuse_in_chat
def check_llamacpp_health(host: str, timeout: float = 4.0) -> dict:
    "Ping a local llama.cpp server's /health endpoint. Read-only, never raises."
    from monitoring.llamacpp_health import probe

    up, detail = probe(host, timeout)
    return {"up": up, "detail": detail}


def _http_token() -> str:
    return os.getenv("CASEFORGE_MCP_OPS_TOKEN", "").strip()


def _bearer_protected_app():
    "Wrap FastMCP's streamable-http ASGI app with the same bearer-token gate"
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    token = _http_token()
    if not token:
        raise SystemExit(
            "CASEFORGE_MCP_OPS_TOKEN is not set. This service can return client and case "
            "data; there is no unauthenticated mode. Set it and re-run."
        )

    class _BearerAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            header = request.headers.get("authorization", "")
            presented = header[7:] if header.lower().startswith("bearer ") else ""
            if not presented or not secrets.compare_digest(presented.encode(), token.encode()):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    inner = mcp.streamable_http_app()
    return Starlette(routes=inner.routes, middleware=[Middleware(_BearerAuth)], lifespan=inner.router.lifespan_context)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run()
    else:
        host = os.getenv("CASEFORGE_MCP_OPS_HOST", "127.0.0.1")
        port = int(os.getenv("CASEFORGE_MCP_OPS_PORT", "8767"))
        app = _bearer_protected_app()
        import uvicorn

        uvicorn.run(app, host=host, port=port)
