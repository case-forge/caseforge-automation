from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
import uuid
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import sentry_sdk
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.background import BackgroundTask

from billing import billing_items
from documents import attendance_note_drafts
import robot_notices
from todos import todo_email, todo_store
from onboarding import pipeline as intake_pipeline
from onboarding.pipeline import markers as intake_markers
from onboarding.pipeline import milestones as matter_milestones
from vergil import court_prep
from vergil import hearing_extract as hearing_extractor
from vergil import hearing_markers
from vergil.schemas import HearingExtractRequest, HearingExtractResponse
from hearing_calendar import bank_holidays, hearing_store
from scanned_docs import scan_rows
from products.ikoro import obligation_aging
from vergil import signin_names
from vergil import mailbox_drafts, an_backup, form_draft_backup, attention_store, auto_flags, notification_feed, bill_export, case_board, client_rows, bill_of_costs, billing_daily, case_flow, client_edits, intake_tray, matter_tasks, person_matters, retrieval, same_name, sos_status, sql_cooldown, statement_replies, work_log
import actor_kind
import clientdb_sql
from vergil.goose import goose_ask, vergil_identity, goose_turn
from vergil.goose import conversation_log, conversation_state_store, goose_client, goose_routing
from vergil.schemas import (
    LogoResponse,
    DraftsResponse,
    FolderLockRequest,
    AuditFolderFlagRequest,
    MatterMilestoneRequest,
    WeTransferGateRequest,
    RecordSignedWsRequest,
    ClientNudgeRequest,
    ClientNudgeResponse,
    AutoSendDismissRequest,
    AutoSendDismissResponse,
    ScansCountResponse,
    ScansResponse,
    StatementRepliesResponse,
    StatementReplyRequest,
    StatementReplyResponse,
    MatterMarkersResponse,
    PipelineMarkDoneRequest,
    PipelineConfirmCourtRequest,
    PipelineServiceRecipientRequest,
    PipelineAmendApproveRequest,
    PipelineAmendDiscardRequest,
    PipelineAmendPrepareRequest,
    PipelineModeRequest,
    PipelineModeResponse,
    PipelineMatterModeRequest,
    PipelineMatterModeResponse,
    PipelineResetRequest,
    PipelineResetStepRequest,
    CaseBoardRemoveRequest,
    ClientMergeRequest,
    MailReviewAnswerRequest,
    MailReviewControlReleaseRequest,
    MailReviewControlRequest,
    MailReviewDecideRequest,
    MailReviewExtendRequest,
    ClientRemoveRequest,
    ClientUndoMergeRequest,
    ClientUndoRemoveRequest,
    ManualClientRequest,
    NewClientRequest,
    PendingNewClientCancelRequest,
    PendingNewClientResumeRequest,
    CaseReviewResponse,
    CaseReviewSaveRequest,
    ConflictCheckResponse,
    CourtRouteResponse,
    ConflictCheckRunRequest,
    IntroLinkResponse,
    LexcelAutoRequest,
    LexcelMakeRequest,
    LexcelMakeResponse,
    LexcelResponse,
    NotificationStateRequest,
    StatementReplyHideRequest,
    PipelineActivityResponse,
    PipelineResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    BillOfCostsResponse,
    RestoreBillingItemRequest,
    RestoreBillingItemResponse,
    CaseFlowResponse,
    ClientMatch,
    CreateCclRequest,
    ClientEdit,
    AttendanceNoteRecentResponse,
    AttendanceNoteStatus,
    CreateAttendanceNoteRequest,
    AppSettingsResponse,
    SpecialSendersRequest,
    SpecialSendersResponse,
    MinutesPerPageRequest,
    ModelRoleChangeResponse,
    ModelRoleSwapRequest,
    ModelRolesResponse,
    MinutesPerPageResponse,
    ScannedFolderRequest,
    EmailClassifierRequest,
    EmailClassifierResponse,
    ScannedFolderResponse,
    CreateAttendanceNoteResponse,
    RetryAttendanceNoteRequest,
    AttendanceNoteEditResponse,
    CompleteTodoRequest,
    CreateTodoRequest,
    DeleteTodoRequest,
    TodoAutomaticRequest,
    DismissRobotNoticeRequest,
    TodoEmailClientResponse,
    TodoItem,
    TodoSummaryResponse,
    TodosResponse,
    UpdateTodoRequest,
    RobotNotice,
    RobotNoticesResponse,
    OpsHealthAlert,
    StorageStatusResponse,
    SystemStatusResponse,
    SystemSpend,
    SystemWorkers,
    SystemRows,
    SystemFunction,
    SystemServices,
    BoxExtrasPush,
    SystemBox,
    SystemProviders,
    BoxStatsPush,
    OpsHealthResponse,
    DeleteAttendanceNoteBillingRequest,
    FrequentCallersResponse,
    GooseAskRequest,
    HealthResponse,
    InternAuditEntry,
    InternAuditResponse,
    RetrievalFeedbackRequest,
    RetrievalFeedbackResponse,
    MatterFlagsResponse,
    FieldReviewFlag,
    FieldReviewQueueResponse,
    PersonMattersResponse,
    ResolveFieldReviewRequest,
    MatterParty,
    MatterPartiesResponse,
    AddPartyRequest,
    UpdatePartyRequest,
    RemovePartyRequest,
    MatterChild,
    MatterChildrenResponse,
    AddChildRequest,
    UpdateChildRequest,
    RemoveChildRequest,
    MatterWorkResponse,
    MonitorAlert,
    MonitorSummaryResponse,
    DocumentChecklistResponse,
    ObligationItem,
    ObligationsResponse,
    RadarItem,
    RadarSummaryResponse,
    RecordEditRequest,
    RecordWorkRequest,
    SetCaseStageRequest,
    SetFlagRequest,
    SosStatusResponse,
    VergilTitleRequest,
    VergilTitleResponse,
    HearingCreateRequest,
    HearingHistoryResponse,
    HearingLinkRequest,
    HearingUnlinkRequest,
    HearingLeadResolveRequest,
    HearingLeadResponse,
    HearingLeadsResponse,
    HearingLinkResponse,
    HearingSuggestionsResponse,
    HearingResponse,
    HearingReviewResolveRequest,
    HearingStatusRequest,
    HearingUpdateRequest,
    HearingVacateRequest,
    HearingVacateResponse,
    HearingRequestOptionsResponse,
    HearingCourtRequest,
    HearingCourtRequestResponse,
    HearingCourtDecisionRequest,
    HearingsResponse,
    MatterTasksResponse,
    AttentionCompleteRequest,
    AttentionItem,
    AttentionResponse,
    LegalAidSectionResponse,
    LegalAidSendRequest,
    LegalAidSendResponse,
    AnBackupRequest,
    AnBackupResponse,
    FormDraftBackupRequest,
    FormDraftBackupResponse,
    ConcludedMattersResponse,
    FlaggedMattersResponse,
    RetrievalHit,
    RetrievalResponse,
    RetrievalStepModel,
    WorkLogEntry,
    WorkSummaryItem,
    ClientSearchResponse,
)

log = logging.getLogger("vergil.api")
MISSING_INFO_QUEUE_LIMIT = 100

DEFAULT_PORT = 8765
GOOSE_ASK_PATH = "/vergil/ask"
MAX_LIMIT = 20
MAX_GRAPH_NAMES = 200

INTERN_AUDIT_DEFAULT_LIMIT = 20
INTERN_AUDIT_MAX_LIMIT = 200



_bearer = HTTPBearer(auto_error=True)


def _expected_token() -> str:
    return os.getenv("CASEFORGE_CHAT_API_TOKEN", "").strip()


def require_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> None:
    expected = _expected_token()
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API token not configured")
    if not secrets.compare_digest(credentials.credentials.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


def require_box_push_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> None:
    expected = os.getenv("CASEFORGE_BOX_STATS_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Box stats token not configured")
    if not secrets.compare_digest(credentials.credentials.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


def verified_admin_email(request: Request) -> str:
    from vergil import access_identity, runtime_control

    try:
        email = access_identity.verify(access_identity.current_assertion())
    except access_identity.AccessIdentityError:
        email = ""
    if email and runtime_control.is_env_admin(email):
        return email
    login = tailnet_dev_login(request)
    return f"tailnet:{login}" if login else ""


def require_verified_admin(request: Request) -> str:
    email = verified_admin_email(request)
    if not email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can do this")
    return email


def verified_user_email(request: Request) -> str:
    from vergil import access_identity

    try:
        email = access_identity.verify(access_identity.current_assertion())
    except access_identity.AccessIdentityError:
        email = ""
    if email:
        return email
    login = tailnet_dev_login(request)
    return f"tailnet:{login}" if login else ""


def require_verified_user(request: Request) -> str:
    email = verified_user_email(request)
    if not email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sign in to do this")
    return email


def verified_dev_email(request: Request) -> str:
    from vergil import access_identity, runtime_control

    try:
        email = access_identity.verify(access_identity.current_assertion())
    except access_identity.AccessIdentityError:
        return ""
    return email if runtime_control.is_env_dev(email) else ""


_PUBLIC_PATH_HEADERS = ("Remote-User", "Cf-Access-Jwt-Assertion", "Cf-Access-Authenticated-User-Email", "Cf-Ray", "Cf-Connecting-Ip")


def tailnet_dev_login(request: Request) -> str:
    from vergil import runtime_control, tailnet_identity

    if any((request.headers.get(name) or "").strip() for name in _PUBLIC_PATH_HEADERS):
        return ""
    caller = tailnet_identity.current_caller()
    if not caller or caller.get("role") != tailnet_identity.TAILNET_ROLE or caller.get("tags"):
        return ""
    login = str(caller.get("login") or "").strip()
    if not login or not tailnet_identity.tailnet_ip(str(caller.get("ip") or "")):
        return ""
    if not runtime_control.is_tailnet_dev_login(login):
        return ""
    client_ip = (request.headers.get("X-CaseForge-Client-Ip") or "").strip()
    if client_ip and not tailnet_identity.tailnet_ip(client_ip):
        return ""
    return login


def dev_identity(request: Request) -> str:
    email = verified_dev_email(request)
    if email:
        return email
    login = tailnet_dev_login(request)
    return f"tailnet:{login}" if login else ""


def require_verified_dev(request: Request) -> str:
    email = dev_identity(request)
    if not email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a developer can see this")
    return email


def caller_role(request: Request) -> str:
    if dev_identity(request):
        return "dev"
    return "admin" if verified_admin_email(request) else "worker"


def _graph_child_names(graph_listing: dict | None) -> list[str]:
    if not graph_listing:
        return []
    return [
        str(child.get("name") or "")
        for child in (graph_listing.get("value") or [])
    ][:MAX_GRAPH_NAMES]


def _resolved_source(rows: list[dict], was_exact: bool) -> str:
    if not rows:
        return "none"
    return "sql" if was_exact else "resolver"


def _same_name_labelled(rows: list) -> list[dict]:
    return same_name.annotate([dict(row) if isinstance(row, dict) else row for row in rows])


def _client_matches(rows: list) -> list[ClientMatch]:
    return [ClientMatch.from_row(row) for row in _same_name_labelled(rows)]


def _client_exposure_limit_detail(categories: list | None, *, verb: str) -> str:
    from vergil.user_state import blocked_by_rolling_window_only

    if blocked_by_rolling_window_only(categories):
        return (
            "Client-exposure limit reached: this account has already reached "
            "its rolling 24-hour limit on distinct client records disclosed "
            "through this API. This is about the account's total for today, "
            f"not this request -- narrowing the {verb} will not help. Wait for "
            "the limit to reset, or ask the supervising solicitor if it needs "
            "to be lifted sooner."
        )
    return (
        "Client-exposure limit reached: this would disclose more "
        "distinct client records than this account is allowed. "
        f"Narrow the {verb}, or ask the supervising solicitor."
    )


def _refuse_if_exposure_blocked(exposure: dict | None, *, verb: str = "window") -> None:
    if exposure and exposure.get("block"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, _client_exposure_limit_detail(exposure.get("categories"), verb=verb))


def _require_known_matter(matter_id: str) -> None:
    text = str(matter_id or "").strip()
    if not (text.isdigit() and len(text) <= 20):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "matter_id must be a matter number")
    try:
        import clientdb_sql

        known = clientdb_sql._matter_exists(text)
    except Exception:
        return
    if not known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such matter")


def _charge_matter_read(request: Request, matter_id: str, source: str) -> None:
    from vergil.user_state import budget_identity, enforce_client_exposure_budget

    remote_user = (request.headers.get("Remote-User") or "").strip()
    _refuse_if_exposure_blocked(
        enforce_client_exposure_budget(budget_identity(remote_user), [{"matter_id": str(matter_id)}], source=source)
    )


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


_REPEAT_TOOL_CALL_STALL_THRESHOLD = 3


def _stable_tool_input_repr(tool_input: object) -> str:
    try:
        return json.dumps(tool_input, sort_keys=True, default=str)
    except TypeError:
        return str(tool_input)


def _stall_fallback_text(last_tool: str, repeat_count: int) -> str:
    if repeat_count:
        return (
            f"I wasn't able to finish this request -- my last {repeat_count} steps were "
            f"identical calls to {last_tool} with no progress in between. Please try "
            "again, or tell me directly what's missing (for example, a recipient email "
            "address or a document name) so I can complete it."
        )
    if last_tool:
        return (
            f"I wasn't able to finish this request -- my last step was "
            f"calling {last_tool} and I didn't reach a final answer after "
            "that. Please try again, or tell me directly what's missing "
            "(for example, a recipient email address or a document name) "
            "so I can complete it."
        )
    return (
        "I wasn't able to finish this request -- I made some tool "
        "calls but didn't reach a final answer. Please try "
        "rephrasing, or ask again with more detail."
    )


def _normalise_for_script_match(text: str) -> str:
    return " ".join(text.casefold().split())


def _first_contact_script_anchor() -> str:
    _, _, bullets = goose_client.FIRST_CONTACT_SCRIPT.partition("What I can do:")
    return _normalise_for_script_match("What I can do:" + bullets)


def _first_contact_followup_anchor() -> str:
    text = goose_client.FIRST_CONTACT_FOLLOWUP
    if text.casefold().startswith("i'm "):
        text = text[4:]
    return _normalise_for_script_match(text)


def _check_probing_contradiction(reply_text: str, *, client_resolved: bool, remote_user: str) -> None:
    normalised = _normalise_for_script_match(reply_text)
    if _first_contact_script_anchor() not in normalised and _first_contact_followup_anchor() not in normalised:
        return
    goose_routing.log_probing_contradiction(
        contradiction="safety_clear_but_probing_reply", remote_user=remote_user,
    )
    if client_resolved:
        goose_routing.log_probing_contradiction(
            contradiction="resolved_client_but_probing_reply", remote_user=remote_user,
        )


def _supervisor_quick_metrics(payload: dict) -> dict:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    calendar = metrics.get("hearing_calendar") if isinstance(metrics.get("hearing_calendar"), dict) else {}
    scanned = metrics.get("scanned_docs") if isinstance(metrics.get("scanned_docs"), dict) else {}
    tunnel = metrics.get("tunnel_health") if isinstance(metrics.get("tunnel_health"), dict) else {}
    return {
        "hearing_calendar": {
            "needs_review": calendar.get("needs_review", 0),
            "review_soon": calendar.get("review_soon", 0),
            "upcoming_14d": calendar.get("upcoming_14d", 0),
        },
        "scanned_docs": {
            "item_count": scanned.get("item_count", 0),
            "change_count": scanned.get("change_count", 0),
            "calendar_candidate_count": scanned.get("calendar_candidate_count", 0),
        },
        "tunnel_health": {
            "overall": tunnel.get("overall", "unknown"),
            "red": tunnel.get("red", 0),
            "amber": tunnel.get("amber", 0),
        },
    }


def _intern_ask_audit_path() -> Path:
    root = os.getenv("CASEFORGE_TELEMETRY_ROOT", "").strip()
    return (Path(root) if root else (REPO_ROOT / "telemetry")) / "intern-qa-audit.jsonl"


def _write_intern_ask_audit(row: dict) -> None:
    try:
        from graph_mail_safe_ops import _append_jsonl_locked

        _append_jsonl_locked(_intern_ask_audit_path(), row)
    except Exception as exc:
        log.warning("intern/ask audit write failed: %s", type(exc).__name__)


def _request_log_path() -> Path:
    import ops_db

    return ops_db.hub_request_log_path()


def _plain_ip(value: str | None) -> str:
    import ipaddress

    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return ""


def _write_request_log(row: dict) -> None:
    try:
        from graph_mail_safe_ops import _append_jsonl_locked

        _append_jsonl_locked(_request_log_path(), row, durable=False)
    except Exception as exc:
        log.warning("hub-api request log write failed: %s", type(exc).__name__)


async def _write_request_log_off_loop(row: dict) -> None:
    await asyncio.to_thread(_write_request_log, row)


RESULT_BEARING_PATHS = ("/clients/search",)


REQUIRED_ENV = {
    "CASEFORGE_CHAT_API_TOKEN": "bearer token -- without it every request is rejected",
    "CASEFORGE_CLIENTDB_PG_URL": "client database -- without it every search returns nothing",
}

OPTIONAL_ENV = {
    "OPENROUTER_API_KEY": "POST /vergil/ask cannot answer without it",
}


def preflight(env: dict[str, str] | None = None) -> list[str]:
    src = os.environ if env is None else env
    return [name for name in REQUIRED_ENV if not str(src.get(name, "")).strip()]


def _intern_qa_feedback_path() -> Path:
    from vergil.feedback import feedback_path

    return feedback_path()


_SENTRY_SAFE_HEADERS = frozenset({"host", "user-agent", "content-type", "content-length", "accept", "accept-encoding"})


def _scrub_sentry_event(event: dict, hint: dict) -> dict | None:
    request = event.get("request")
    if request:
        request.pop("query_string", None)
        request.pop("data", None)
        request.pop("cookies", None)
        if "url" in request and isinstance(request["url"], str):
            request["url"] = request["url"].split("?", 1)[0]
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if str(k).lower() in _SENTRY_SAFE_HEADERS}
    exceptions = event.get("exception")
    for exc in exceptions.get("values", []) if isinstance(exceptions, dict) else []:
        if isinstance(exc, dict):
            exc["value"] = ""
            for frame in (exc.get("stacktrace") or {}).get("frames", []):
                if isinstance(frame, dict):
                    for key in ("vars", "pre_context", "context_line", "post_context"):
                        frame.pop(key, None)
    event.pop("logentry", None)
    event.pop("message", None)
    event.pop("user", None)
    event.pop("extra", None)
    for breadcrumb in event.get("breadcrumbs", {}).get("values", []) if isinstance(event.get("breadcrumbs"), dict) else []:
        data = breadcrumb.get("data")
        if isinstance(data, dict):
            data.pop("query_string", None)
            data.pop("url", None)
    return event


def _init_sentry() -> None:
    dsn = os.getenv("GLITCHTIP_DSN_HUB_API")
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0,
        send_default_pii=False,
        include_local_variables=False,
        before_send=_scrub_sentry_event,
    )


_ACTOR_BODY_FIELDS = ("edited_by", "by", "set_by", "created_by", "resolved_by", "flagged_by", "typed_name")


def change_log_actor(body: bytes, remote_user: str, path: str) -> str:
    name = ""
    if body and len(body) <= 256_000:
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            payload = None
        if isinstance(payload, dict):
            name = next(
                (str(payload[k]) for k in _ACTOR_BODY_FIELDS if isinstance(payload.get(k), str) and payload[k].strip()),
                "",
            )
    name = " ".join((name or signin_names.display_name(remote_user)).split())[:120]
    return f"{name} via hub {path}" if name else f"hub {path}"


_MATTER_SCOPED_WRITE_PREFIXES = (
    "/client-viewer/matter-flags",
    "/client-viewer/field-review",
    "/client-viewer/hearings",
    "/client-viewer/todos",
    "/client-viewer/attendance-notes",
    "/client-viewer/case-flow",
    "/client-viewer/lexcel",
    "/client-viewer/legal-aid",
    "/client-viewer/pipeline",
)


_MATTER_SUMMARY_PARTS = ("flags", "person_matters", "sos_status", "bill_of_costs")


def write_matter_ids(body: bytes, path: str) -> list[str]:
    if not any(path == p or path.startswith(p + "/") for p in _MATTER_SCOPED_WRITE_PREFIXES):
        return []
    if not body or len(body) > 256_000:
        return []
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    matter_id = payload.get("matter_id")
    text = str(matter_id).strip() if isinstance(matter_id, (str, int)) and not isinstance(matter_id, bool) else ""
    return [text] if text.isdigit() else []


from vergil.http_headers import content_disposition


def _flag_list_reasons(flags_by_matter: dict[str, list[str]], user: str) -> dict[str, str]:
    shared = client_edits.list_reasons_by_matter("flagged")
    own = client_edits.list_personal_reasons(user, "flagged")
    mine = client_edits.list_personal_matters(user, "flagged")
    out: dict[str, str] = {}
    for matter_id, names in flags_by_matter.items():
        if "flagged" not in names:
            continue
        lines = [f"Automatic flag: {shared[matter_id]}"] if matter_id in shared else []
        if matter_id in mine:
            lines.append(f"Your flag: {own[matter_id]}" if matter_id in own else "Your flag")
        if lines:
            out[matter_id] = "\n".join(lines)
    return out


def _matter_flags_response(matter_id: str, user: str) -> MatterFlagsResponse:
    shared, reasons = client_edits.list_flags_and_reasons(matter_id)
    personal, personal_reasons = client_edits.personal_state(matter_id, user)
    flags = {**shared, **personal}
    return MatterFlagsResponse(
        matter_id=matter_id,
        flags=flags,
        reasons=reasons,
        shared={name: on for name, on in shared.items() if on and name in client_edits.PERSONAL_FLAGS},
        personal=personal,
        personal_reasons=personal_reasons,
    )


def _flag_user(request: Request) -> str:
    from vergil.user_state import budget_identity

    return budget_identity((request.headers.get("Remote-User") or "").strip())


def create_app() -> FastAPI:
    _init_sentry()
    if not _expected_token():
        raise RuntimeError(
            "CASEFORGE_CHAT_API_TOKEN is not set. This service returns live client records and "
            "will not start unauthenticated."
        )

    app = FastAPI(
        title="CaseForge Chat Core API",
        version="0.1.0",
        description="Client search over the Streamlit-free caseforge-chat core. Localhost, token-gated.",
        docs_url="/docs" if os.getenv("CASEFORGE_HUB_DOCS") == "1" else None,
        redoc_url="/redoc" if os.getenv("CASEFORGE_HUB_DOCS") == "1" else None,
    )

    @app.middleware("http")
    async def _log_request(request: Request, call_next):
        started = time.perf_counter()
        status_code = 500
        deferred = False

        def _row(stream_error: bool | None) -> dict:
            path = request.url.path
            return {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "method": request.method,
                "path": path,
                "status": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "results": getattr(request.state, "result_count", None),
                "result_bearing": path in RESULT_BEARING_PATHS,
                "stream_error": stream_error,
                "remote_user": (request.headers.get("Remote-User") or "").strip(),
                "client_ip": _plain_ip(request.headers.get("X-CaseForge-Client-Ip")),
            }

        try:
            response = await call_next(request)
            status_code = response.status_code
            if request.method != "GET" and status_code < 400:
                touched = getattr(request.state, "written_matter_ids", None)
                if touched:
                    client_rows.invalidate(touched)
                else:
                    client_rows.clear()
            if response.headers.get("content-type", "").startswith("text/event-stream"):
                body = response.body_iterator

                async def _log_after_stream():
                    try:
                        async for chunk in body:
                            yield chunk
                    finally:
                        await _write_request_log_off_loop(_row(bool(getattr(request.state, "stream_error", False))))

                response.body_iterator = _log_after_stream()
                deferred = True
            return response
        finally:
            if not deferred:
                await _write_request_log_off_loop(_row(None))

    @app.middleware("http")
    async def _name_writer_in_change_log(request: Request, call_next):
        if request.method == "GET":
            return await call_next(request)
        body = b""
        if "json" in (request.headers.get("content-type") or ""):
            body = await request.body()
        actor = change_log_actor(body, request.headers.get("Remote-User") or "", request.url.path)
        request.state.written_matter_ids = write_matter_ids(body, request.url.path)
        kind = actor_kind.kind_for_request(request.headers.get("Remote-User") or "", request.headers.get(actor_kind.HEADER) or "")
        with clientdb_sql.acting_as(actor), actor_kind.request_kind(kind):
            return await call_next(request)

    @app.middleware("http")
    async def _hold_access_assertion(request: Request, call_next):
        from starlette.concurrency import run_in_threadpool

        from vergil import access_identity, tailnet_identity

        caller = None
        if not (request.headers.get("Remote-User") or "").strip():
            peer = request.client
            server = request.scope.get("server") or (None, None)
            caller = await run_in_threadpool(
                lambda: tailnet_identity.resolve_caller(
                    peer_host=peer.host if peer else None,
                    peer_port=peer.port if peer else None,
                    local_port=server[1] if len(server) > 1 else None,
                    headers=request.headers,
                )
            )
        with access_identity.request_assertion(request.headers.get(access_identity.CF_ACCESS_JWT_HEADER)), \
                tailnet_identity.request_caller(caller):
            return await call_next(request)

    from vergil import editor_identity

    app.add_middleware(editor_identity.EditorFromIdentity, routes=lambda: app.router.routes)

    from vergil.ingress import IngressGuard

    app.add_middleware(IngressGuard, expected_token=_expected_token)
    stack = app.user_middleware
    guard = stack.pop(0)
    log_at = next(i for i, m in enumerate(stack) if getattr(m.kwargs.get("dispatch"), "__name__", "") == "_log_request")
    request_log = stack.pop(log_at)
    stack[:0] = [request_log, guard]

    from vergil import virtual_scanner_api

    app.include_router(virtual_scanner_api.router(require_token))

    @app.get("/health", response_model=HealthResponse, dependencies=[Depends(require_token)])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            sql_available=sql_cooldown.is_sql_available(),
            sql_cooldown_until=sql_cooldown.sql_cooldown_until(),
        )

    @app.get(
        "/clients/search",
        response_model=ClientSearchResponse,
        dependencies=[Depends(require_token)],
        summary="Search matters by client name, court reference, email or phone",
    )
    def search(
        request: Request,
        q: str = Query(min_length=2, description="Name, court reference, email or phone."),
        limit: int = Query(default=6, ge=1, le=MAX_LIMIT),
    ) -> ClientSearchResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()

        try:
            import agwu

            _result = agwu.resolve_client(q, limit=limit, caller="vergil.api.clients_search")
            rows, display = [m.row for m in _result.matches], _result.display_query
            was_exact = bool(_result.top and "exact_search" in _result.top.match_sources)
        except Exception as exc:
            log.error("client search failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Client search backend unavailable"
            ) from exc

        if rows:
            from vergil.user_state import (
                budget_identity,
                enforce_client_exposure_budget,
            )

            exposure = enforce_client_exposure_budget(
                budget_identity(remote_user), rows, source="clients_search"
            )
            if exposure.get("block"):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    _client_exposure_limit_detail(exposure.get("categories"), verb="search"),
                )

        request.state.result_count = len(rows)
        return ClientSearchResponse(
            query=q,
            resolved_query=display,
            source=_resolved_source(rows, was_exact),
            count=len(rows),
            results=_client_matches(rows),
        )

    @app.get(
        "/client-viewer/ccl-candidates",
        dependencies=[Depends(require_token)],
        summary="Recent matters and their CCL status, for caseforge-client-viewer's emergency CCL panel",
    )
    def ccl_candidates(
        request: Request,
        days: int = Query(default=90, ge=1, le=365),
        limit: int = Query(default=200, ge=1, le=200),
    ) -> dict:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            from vergil import background_jobs

            queue = background_jobs.ccl_status_module()
            rows = queue.load_client_care_letter_status_rows(days=days, limit=limit)
        except Exception as exc:
            log.error("ccl candidates lookup failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "CCL candidate lookup unavailable"
            ) from exc

        if rows:
            from vergil.user_state import (
                budget_identity,
                enforce_client_exposure_budget,
            )

            exposure = enforce_client_exposure_budget(
                budget_identity(remote_user), rows, source="ccl_candidates"
            )
            if exposure.get("block"):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    _client_exposure_limit_detail(exposure.get("categories"), verb="window"),
                )

        return {"rows": rows}

    @app.post(
        "/client-viewer/create-ccl",
        dependencies=[Depends(require_token)],
        summary="Refused: client care letters are made in Caseflow",
    )
    def create_ccl(request: Request, payload: CreateCclRequest) -> dict:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            from vergil import background_jobs

            ok, message = background_jobs.enqueue_client_care_letter_job(
                remote_user or "client-viewer", payload.client_name
            )
        except Exception as exc:
            log.error("create ccl failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "CCL queue unavailable"
            ) from exc
        if not ok:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, message)
        return {"ok": True, "message": message}

    @app.get(
        "/client-viewer/client-edits",
        response_model=list[ClientEdit],
        dependencies=[Depends(require_token)],
        summary="Edit history for one matter, most recent first",
    )
    def list_client_edits(
        matter_id: str = Query(..., min_length=1),
    ) -> list[ClientEdit]:
        try:
            rows = client_edits.list_edits(matter_id)
        except Exception as exc:
            log.error("client edit history read failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Edit history unavailable"
            ) from exc
        return [ClientEdit.from_row(row) for row in rows]

    @app.post(
        "/client-viewer/client-edits",
        response_model=ClientEdit,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_token)],
        summary="Apply a change to a client/matter field and record who made it",
    )
    def record_client_edit(payload: RecordEditRequest) -> ClientEdit:
        try:
            row = client_edits.record_edit(
                matter_id=payload.matter_id,
                field_name=payload.field_name,
                new_value=payload.new_value,
                note=payload.note,
                edited_by=payload.edited_by,
            )
        except client_edits.ClientEditError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("client edit write failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Edit unavailable"
            ) from exc
        return ClientEdit.from_row(row)

    @app.get(
        "/client-viewer/matter-flags",
        response_model=MatterFlagsResponse,
        dependencies=[Depends(require_token)],
        summary="Quick-tick flags (e.g. persistent caller) set for one matter",
    )
    def get_matter_flags(request: Request, matter_id: str = Query(..., min_length=1)) -> MatterFlagsResponse:
        try:
            return _matter_flags_response(matter_id, _flag_user(request))
        except Exception as exc:
            log.error("matter flag read failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Matter flags unavailable"
            ) from exc

    @app.get(
        "/client-viewer/matter-flags/batch",
        dependencies=[Depends(require_token)],
        summary="Quick-tick flags for several matters at once (the result cards' pills)",
    )
    def get_matter_flags_batch(
        request: Request,
        matter_ids: str = Query(..., min_length=1, description="Comma-separated matter ids, at most 200."),
    ) -> dict[str, dict[str, dict[str, bool]]]:
        ids = [part.strip() for part in matter_ids.split(",") if part.strip()]
        if len(ids) > 200:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "At most 200 matter ids per request")
        try:
            return {"flags_by_matter": client_edits.list_flags_for_matters(ids, user=_flag_user(request))}
        except Exception as exc:
            log.error("matter flag batch read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Matter flags unavailable") from exc

    @app.get(
        "/client-viewer/concluded-matters",
        response_model=ConcludedMattersResponse,
        dependencies=[Depends(require_token)],
        summary="Concluded matters (those with a closed_at), newest first, one page at a time",
    )
    def concluded_matters(
        request: Request,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> ConcludedMattersResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            import clientdb_sql

            ids, total = clientdb_sql.list_closed_matter_ids_page(limit, offset)
            rows = client_rows.rows_for(ids)
        except Exception as exc:
            log.error("concluded matters lookup failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Concluded matters lookup unavailable") from exc

        if rows:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            exposure = enforce_client_exposure_budget(budget_identity(remote_user), rows, source="concluded_matters")
            if exposure.get("block"):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    _client_exposure_limit_detail(exposure.get("categories"), verb="window"),
                )

        end = offset + len(ids)
        return ConcludedMattersResponse(
            results=_client_matches(rows),
            total=total,
            next_offset=end if end < total and ids else None,
        )

    @app.post(
        "/client-viewer/matter-flags",
        response_model=MatterFlagsResponse,
        dependencies=[Depends(require_token)],
        summary="Flip one quick-tick flag for a matter",
    )
    def set_matter_flag(request: Request, payload: SetFlagRequest) -> MatterFlagsResponse:
        user = _flag_user(request)
        try:
            if client_edits.is_personal_request(payload.flag_name):
                client_edits.set_personal_flag(
                    user=user, matter_id=payload.matter_id, flag_name=payload.flag_name, is_set=payload.is_set,
                    reason=payload.reason, only_if_reason=payload.only_if_reason, scope=payload.scope,
                    set_by=payload.set_by,
                )
            else:
                client_edits.set_flag(
                    matter_id=payload.matter_id,
                    flag_name=payload.flag_name,
                    is_set=payload.is_set,
                    set_by=payload.set_by,
                    reason=payload.reason,
                    only_if_reason=payload.only_if_reason,
                )
            response = _matter_flags_response(payload.matter_id, user)
        except client_edits.ClientEditError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("matter flag write failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Matter flag unavailable"
            ) from exc
        return response

    @app.post(
        "/client-viewer/field-review/resolve",
        response_model=FieldReviewFlag,
        dependencies=[Depends(require_token)],
        summary="Mark one review flag done (never deleted, same as every other edit-history row)",
    )
    def post_field_review_resolve(payload: ResolveFieldReviewRequest) -> FieldReviewFlag:
        try:
            row = client_edits.resolve_field_review(
                review_id=payload.review_id, resolved_by=payload.resolved_by
            )
        except client_edits.ClientEditError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("field review resolve failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Field review flag unavailable"
            ) from exc
        return FieldReviewFlag.from_row(row)

    @app.get(
        "/client-viewer/field-review-queue",
        response_model=FieldReviewQueueResponse,
        dependencies=[Depends(require_token)],
        summary="Every matter carrying an open 'mark for review' flag -- AppDrawer's review-queue quick list",
    )
    def field_review_queue(request: Request) -> FieldReviewQueueResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            import clientdb_sql

            matter_ids = client_edits.list_matters_with_open_review()
            rows = client_rows.rows_for(matter_ids)
            open_flags = client_edits.list_open_review_flags_for_matters([str(row.get("matter_id")) for row in rows])
            flags_by_matter: dict[str, list[FieldReviewFlag]] = {
                str(row.get("matter_id")): [
                    FieldReviewFlag.from_row(flag_row) for flag_row in open_flags.get(str(row.get("matter_id")), [])
                ]
                for row in rows
            }
        except Exception as exc:
            log.error("field review queue lookup failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Field review queue unavailable"
            ) from exc

        try:
            import clientdb_sql
            from vergil import missing_info

            gaps = missing_info.list_matters_missing_info()[:MISSING_INFO_QUEUE_LIMIT]
            new_rows = {str(r.get("matter_id")): r for r in client_rows.rows_for([str(i["matter_id"]) for i in gaps if str(i["matter_id"]) not in flags_by_matter])}
            for item in gaps:
                matter_id = str(item["matter_id"])
                if matter_id not in flags_by_matter:
                    row = new_rows.get(matter_id)
                    if not row:
                        continue
                    rows.append(row)
                    flags_by_matter[matter_id] = []
                flags_by_matter[matter_id].append(FieldReviewFlag.from_row(missing_info.review_entry(item)))
            no_referral = missing_info.list_matters_missing_referral()[:MISSING_INFO_QUEUE_LIMIT]
            more = {str(r.get("matter_id")): r for r in client_rows.rows_for([i for i in no_referral if i not in flags_by_matter])}
            for matter_id in no_referral:
                if matter_id not in flags_by_matter:
                    row = more.get(matter_id)
                    if not row:
                        continue
                    rows.append(row)
                    flags_by_matter[matter_id] = []
                flags_by_matter[matter_id].append(FieldReviewFlag.from_row(missing_info.referral_entry(matter_id)))
            for reason, ids in missing_info.list_matters_no_folder().items():
                ids = [i for i in ids if i not in no_referral][:MISSING_INFO_QUEUE_LIMIT]
                extra = {str(r.get("matter_id")): r for r in client_rows.rows_for([i for i in ids if i not in flags_by_matter])}
                for matter_id in ids:
                    if matter_id not in flags_by_matter:
                        row = extra.get(matter_id)
                        if not row:
                            continue
                        rows.append(row)
                        flags_by_matter[matter_id] = []
                    flags_by_matter[matter_id].append(FieldReviewFlag.from_row(missing_info.no_folder_entry(matter_id, reason)))
        except Exception as exc:
            log.error("missing information lookup failed: %s", type(exc).__name__)

        if rows:
            from vergil.user_state import (
                budget_identity,
                enforce_client_exposure_budget,
            )

            exposure = enforce_client_exposure_budget(
                budget_identity(remote_user), rows, source="field_review_queue"
            )
            if exposure.get("block"):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    _client_exposure_limit_detail(exposure.get("categories"), verb="window"),
                )

        return FieldReviewQueueResponse(
            results=_client_matches(rows),
            flags_by_matter=flags_by_matter,
        )

    @app.get(
        "/client-viewer/parties",
        response_model=MatterPartiesResponse,
        dependencies=[Depends(require_token)],
        summary="Respondent/other-party rows for one matter -- the real matter_parties rows, not the flattened party_summary string",
    )
    def get_parties(request: Request, matter_id: str = Query(..., min_length=1)) -> MatterPartiesResponse:
        _charge_matter_read(request, matter_id, "matter_parties")
        try:
            import clientdb_sql

            rows = clientdb_sql.list_parties(matter_id)
        except Exception as exc:
            log.error("party list failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Party records unavailable") from exc
        return MatterPartiesResponse(matter_id=matter_id, parties=[MatterParty.from_row(row) for row in rows])

    @app.get(
        "/client-viewer/portal-answers",
        dependencies=[Depends(require_token)],
        summary="Signed, short-lived answers export for the portal-fill extension: one matter, may hold C8 data (says so), audited; shown to the caseworker to copy, never saved",
    )
    def get_portal_answers(
        request: Request,
        matter_id: str = Query(..., min_length=1),
        ttl_minutes: int = Query(15, ge=1, le=60),
    ):
        from vergil import portal_answers

        _require_known_matter(matter_id)
        _charge_matter_read(request, matter_id, "portal_answers_export")
        from vergil import editor_identity

        asked_by = editor_identity.resolve_editor((request.headers.get("Remote-User") or "").strip(), via_client_viewer=True) or "machine"
        try:
            made = portal_answers.generate(matter_id, requested_by=asked_by, ttl_minutes=ttl_minutes)
        except portal_answers.ExportError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except Exception as exc:
            log.error("portal answers export failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The answers export could not be made") from exc
        return Response(content=json.dumps(made), media_type="application/json", headers={"Cache-Control": "no-store"})

    @app.post(
        "/client-viewer/parties",
        response_model=MatterParty,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_token)],
        summary="Add one respondent/other-party row (2026-09-23, owner instruction: multi-row add/remove editor)",
    )
    def post_add_party(payload: AddPartyRequest) -> MatterParty:
        fields = {
            k: v for k, v in payload.model_dump(exclude={"matter_id", "edited_by", "note"}).items()
            if v
        }
        try:
            row = client_edits.add_party(
                matter_id=payload.matter_id, fields=fields, note=payload.note, edited_by=payload.edited_by,
            )
        except (client_edits.ClientEditError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("party add failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Party record unavailable") from exc
        return MatterParty.from_row(row)

    @app.post(
        "/client-viewer/parties/update",
        response_model=MatterParty,
        dependencies=[Depends(require_token)],
        summary="Update one respondent/other-party row's fields",
    )
    def post_update_party(payload: UpdatePartyRequest) -> MatterParty:
        fields = {
            k: v for k, v in payload.model_dump(exclude={"matter_id", "party_id", "edited_by", "note"}).items()
            if v is not None
        }
        try:
            row = client_edits.update_party(
                matter_id=payload.matter_id, party_id=payload.party_id, fields=fields,
                note=payload.note, edited_by=payload.edited_by,
            )
        except (client_edits.ClientEditError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("party update failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Party record unavailable") from exc
        return MatterParty.from_row(row)

    @app.post(
        "/client-viewer/parties/remove",
        dependencies=[Depends(require_token)],
        summary="Remove one respondent/other-party row -- its last values stay in the change history",
    )
    def post_remove_party(payload: RemovePartyRequest) -> dict:
        try:
            client_edits.remove_party(
                matter_id=payload.matter_id, party_id=payload.party_id,
                note=payload.note, edited_by=payload.edited_by,
            )
        except (client_edits.ClientEditError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("party remove failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Party record unavailable") from exc
        return {"removed": True, "party_id": payload.party_id}

    @app.get(
        "/client-viewer/person-matters",
        response_model=PersonMattersResponse,
        dependencies=[Depends(require_token)],
        summary="Every matter belonging to the same person as one matter -- the case tabs",
    )
    def get_person_matters(request: Request, matter_id: str = Query(..., min_length=1)) -> PersonMattersResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            result = person_matters.person_matters(matter_id)
        except Exception as exc:
            log.error("person matters read failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Matters for this person unavailable"
            ) from exc

        others = [row for row in result["matters"] if str(row.get("matter_id") or "") != matter_id]
        if others:
            from vergil.user_state import (
                budget_identity,
                enforce_client_exposure_budget,
            )

            exposure = enforce_client_exposure_budget(
                budget_identity(remote_user), others, source="person_matters"
            )
            if exposure.get("block"):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    _client_exposure_limit_detail(exposure.get("categories"), verb="window"),
                )

        return PersonMattersResponse(
            matter_id=result["matter_id"],
            matters=_client_matches(result["matters"]),
        )

    @app.get(
        "/client-viewer/matter-neighbour",
        dependencies=[Depends(require_token)],
        summary="The live matter with the next lower or higher matter number (the CRM's number arrows)",
    )
    def get_matter_neighbour(
        request: Request,
        matter_id: int = Query(..., ge=1),
        dir: str = Query(..., pattern="^(prev|next)$"),
    ) -> dict[str, Any]:
        from vergil import matter_neighbour
        from onboarding import client_removal

        try:
            hidden = client_removal.hidden_ids()
        except Exception as exc:
            log.warning("removed clients unreadable, nothing skipped: %s", type(exc).__name__)
            hidden = set()
        try:
            found = matter_neighbour.neighbour(matter_id, dir, hidden=hidden)
        except Exception as exc:
            log.error("matter neighbour read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Next matter number unavailable") from exc
        if found:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            remote_user = (request.headers.get("Remote-User") or "").strip()
            _refuse_if_exposure_blocked(
                enforce_client_exposure_budget(budget_identity(remote_user), [{"matter_id": found}], source="matter_neighbour")
            )
        return {"matter_id": found}

    @app.post(
        "/client-viewer/vergil-title",
        response_model=VergilTitleResponse,
        dependencies=[Depends(require_token)],
        summary="A short title for a Vergil conversation, from its first question and the start of the answer",
    )
    def vergil_title(payload: VergilTitleRequest) -> VergilTitleResponse:
        from vergil.titles import make_title

        return VergilTitleResponse(title=make_title(payload.question, payload.answer))

    @app.get(
        "/client-viewer/children",
        response_model=MatterChildrenResponse,
        dependencies=[Depends(require_token)],
        summary="The real matter_children rows for one matter",
    )
    def get_children(request: Request, matter_id: str = Query(..., min_length=1)) -> MatterChildrenResponse:
        _charge_matter_read(request, matter_id, "matter_children")
        try:
            import clientdb_sql

            rows = clientdb_sql.list_children(matter_id)
        except Exception as exc:
            log.error("child list failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Children records unavailable") from exc
        return MatterChildrenResponse(matter_id=matter_id, children=[MatterChild.from_row(row) for row in rows])

    @app.post(
        "/client-viewer/children",
        response_model=MatterChild,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_token)],
        summary="Add one child",
    )
    def post_add_child(payload: AddChildRequest) -> MatterChild:
        fields = {
            k: v for k, v in payload.model_dump(exclude={"matter_id", "edited_by", "note"}).items()
            if v
        }
        try:
            row = client_edits.add_child(
                matter_id=payload.matter_id, fields=fields, note=payload.note, edited_by=payload.edited_by,
            )
        except (client_edits.ClientEditError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("child add failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Child record unavailable") from exc
        return MatterChild.from_row(row)

    @app.post(
        "/client-viewer/children/update",
        response_model=MatterChild,
        dependencies=[Depends(require_token)],
        summary="Update one child's fields",
    )
    def post_update_child(payload: UpdateChildRequest) -> MatterChild:
        fields = {
            k: v for k, v in payload.model_dump(exclude={"matter_id", "child_id", "edited_by", "note"}).items()
            if v is not None
        }
        try:
            row = client_edits.update_child(
                matter_id=payload.matter_id, child_id=payload.child_id, fields=fields,
                note=payload.note, edited_by=payload.edited_by,
            )
        except (client_edits.ClientEditError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("child update failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Child record unavailable") from exc
        return MatterChild.from_row(row)

    @app.post(
        "/client-viewer/children/remove",
        dependencies=[Depends(require_token)],
        summary="Remove one child -- its last values stay in the change history",
    )
    def post_remove_child(payload: RemoveChildRequest) -> dict:
        try:
            client_edits.remove_child(
                matter_id=payload.matter_id, child_id=payload.child_id,
                note=payload.note, edited_by=payload.edited_by,
            )
        except (client_edits.ClientEditError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("child remove failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Child record unavailable") from exc
        return {"removed": True, "child_id": payload.child_id}

    @app.get(
        "/client-viewer/sos-status",
        response_model=SosStatusResponse,
        dependencies=[Depends(require_token)],
        summary="Statement of Service documents filed for one matter, most recent first",
    )
    def get_sos_status(matter_id: str = Query(..., min_length=1)) -> SosStatusResponse:
        try:
            result = sos_status.sos_status(matter_id)
        except Exception as exc:
            log.error("sos status read failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Statement of Service status unavailable"
            ) from exc
        return SosStatusResponse(**result)

    @app.get(
        "/client-viewer/case-flow",
        response_model=CaseFlowResponse,
        dependencies=[Depends(require_token)],
        summary="Which stages of the NMO/CAO case flow a matter has evidence for, plus the caseworker's own stage",
    )
    def get_case_flow(matter_id: str = Query(..., min_length=1)) -> CaseFlowResponse:
        try:
            return CaseFlowResponse(**case_flow.case_flow(matter_id))
        except case_flow.CaseFlowError as exc:
            code = status.HTTP_404_NOT_FOUND if "not found" in str(exc) else status.HTTP_422_UNPROCESSABLE_CONTENT
            raise HTTPException(code, str(exc)) from exc
        except Exception as exc:
            log.error("case flow read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Case flow unavailable") from exc

    @app.post(
        "/client-viewer/case-flow/stage",
        response_model=CaseFlowResponse,
        dependencies=[Depends(require_token)],
        summary="Set or clear the caseworker's own current stage for a matter",
    )
    def set_case_flow_stage(payload: SetCaseStageRequest) -> CaseFlowResponse:
        try:
            case_flow.require_matter(payload.matter_id)
            case_flow.set_manual_stage(matter_id=payload.matter_id, stage=payload.stage, set_by=payload.set_by)
            return CaseFlowResponse(**case_flow.case_flow(payload.matter_id))
        except case_flow.CaseFlowError as exc:
            code = status.HTTP_404_NOT_FOUND if "not found" in str(exc) else status.HTTP_422_UNPROCESSABLE_CONTENT
            raise HTTPException(code, str(exc)) from exc
        except Exception as exc:
            log.error("case flow stage write failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Case flow stage unavailable") from exc

    @app.get(
        "/client-viewer/matter-tasks",
        response_model=MatterTasksResponse,
        dependencies=[Depends(require_token)],
        summary="Complaints and updates the secretary triage routed to one matter, open complaints first",
    )
    def get_matter_tasks(matter_id: str = Query(..., min_length=1)) -> MatterTasksResponse:
        try:
            result = matter_tasks.matter_tasks(matter_id)
        except Exception as exc:
            log.error("matter tasks read failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Matter tasks unavailable"
            ) from exc
        return MatterTasksResponse(**result)

    def _hearings_response(rows: list[dict], request: Request, *, source: str) -> HearingsResponse:
        exposure_rows = [
            {"matter_id": row["matter_id"], "canonical_name": row.get("client_name")}
            for row in rows if row.get("matter_id") is not None
        ]
        if exposure_rows:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            remote_user = (request.headers.get("Remote-User") or "").strip()
            _refuse_if_exposure_blocked(enforce_client_exposure_budget(budget_identity(remote_user), exposure_rows, source=source))
        return HearingsResponse(
            hearings=rows, needs_review_count=sum(1 for row in rows if row["review_state"] == "needs_review"),
        )

    def _hearing_failure(exc: Exception, what: str) -> HTTPException:
        if isinstance(exc, hearing_store.HearingError):
            return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
        log.error("hearing %s failed: %s", what, type(exc).__name__)
        return HTTPException(status.HTTP_502_BAD_GATEWAY, "Hearing calendar unavailable")

    @app.get(
        "/client-viewer/hearings",
        response_model=HearingsResponse,
        dependencies=[Depends(require_token)],
        summary="Hearings falling in a date range, for the Calendar view",
    )
    def get_hearings(
        request: Request,
        date_from: str = Query(..., alias="from", min_length=10, max_length=10),
        date_to: str = Query(..., alias="to", min_length=10, max_length=10),
        matter_id: int | None = Query(default=None),
    ) -> HearingsResponse:
        try:
            rows = hearing_store.list_hearings(date_from, date_to, matter_id=matter_id)
            hearing_markers.annotate(rows)
            response = _hearings_response(rows, request, source="hearings_calendar")
            response.needs_review_count = hearing_store.count_needs_review()
            response.open_leads_count = hearing_store.count_open_leads()
            response.bank_holidays = bank_holidays.between(date_from, date_to)
            return response
        except HTTPException:
            raise
        except Exception as exc:
            raise _hearing_failure(exc, "list") from exc

    @app.get(
        "/client-viewer/hearings/review",
        response_model=HearingsResponse,
        dependencies=[Depends(require_token)],
        summary="Every hearing awaiting a human decision -- the one manual queue",
    )
    def get_hearings_review(request: Request) -> HearingsResponse:
        try:
            response = _hearings_response(hearing_store.review_queue(), request, source="hearings_review")
            response.open_leads_count = hearing_store.count_open_leads()
            return response
        except HTTPException:
            raise
        except Exception as exc:
            raise _hearing_failure(exc, "review list") from exc

    @app.post(
        "/client-viewer/hearings",
        response_model=HearingResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_token)],
        summary="Add a hearing by hand",
    )
    def post_hearing(payload: HearingCreateRequest) -> HearingResponse:
        fields = payload.model_dump(exclude={"edited_by"})
        try:
            return HearingResponse(hearing=hearing_store.create_hearing(fields, actor=payload.edited_by))
        except Exception as exc:
            raise _hearing_failure(exc, "create") from exc

    @app.post(
        "/client-viewer/hearing-extract",
        response_model=HearingExtractResponse,
        dependencies=[Depends(require_token)],
        summary="Hearing details an attendance note states (court, counsel, chambers, ...); grounded in its own words",
    )
    def post_hearing_extract(payload: HearingExtractRequest) -> HearingExtractResponse:
        import datetime as dt

        try:
            today = dt.date.fromisoformat(payload.today)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "today must be a real date") from exc
        return HearingExtractResponse(**hearing_extractor.extract(payload.text, today))

    @app.post(
        "/client-viewer/hearings/update",
        response_model=HearingResponse,
        dependencies=[Depends(require_token)],
        summary="Edit a hearing's fields; a person's edit is never overwritten by an email",
    )
    def post_hearing_update(payload: HearingUpdateRequest) -> HearingResponse:
        try:
            return HearingResponse(hearing=hearing_store.update_hearing(payload.hearing_id, payload.edits, actor=payload.edited_by))
        except Exception as exc:
            raise _hearing_failure(exc, "update") from exc

    @app.post(
        "/client-viewer/hearings/status",
        response_model=HearingResponse,
        dependencies=[Depends(require_token)],
        summary="Reinstate a hearing, or vacate it with no reason (never deleted; cancelled is an old word for vacated)",
    )
    def post_hearing_status(payload: HearingStatusRequest) -> HearingResponse:
        try:
            return HearingResponse(hearing=hearing_store.set_status(payload.hearing_id, payload.status, actor=payload.edited_by, note=payload.note))
        except Exception as exc:
            raise _hearing_failure(exc, "status") from exc

    @app.post(
        "/client-viewer/hearings/vacate",
        response_model=HearingVacateResponse,
        dependencies=[Depends(require_token)],
        summary="Vacate a hearing with a reason; a move also creates its replacement in the same step (never deleted)",
    )
    def post_hearing_vacate(payload: HearingVacateRequest) -> HearingVacateResponse:
        try:
            return HearingVacateResponse(**hearing_store.vacate_hearing(
                payload.hearing_id, payload.kind, actor=payload.edited_by, reason=payload.reason, replacement=payload.replacement,
            ))
        except Exception as exc:
            raise _hearing_failure(exc, "vacate") from exc

    @app.get(
        "/client-viewer/hearings/request-options",
        response_model=HearingRequestOptionsResponse,
        dependencies=[Depends(require_token)],
        summary="The application form (FP2 or C2) and the stock reasons for asking the court about a hearing",
    )
    def get_hearing_request_options(hearing_id: int = Query(..., ge=1)) -> HearingRequestOptionsResponse:
        from hearing_calendar import hearing_requests

        try:
            return HearingRequestOptionsResponse(**hearing_requests.options(hearing_id))
        except Exception as exc:
            raise _hearing_failure(exc, "request options") from exc

    @app.post(
        "/client-viewer/hearings/request",
        response_model=HearingCourtRequestResponse,
        dependencies=[Depends(require_token)],
        summary="Ask the court to vacate a hearing or hear it remotely: a draft FP2/C2 email (AI DRAFTED, never sent), then the hearing shows as requested",
    )
    def post_hearing_request(payload: HearingCourtRequest) -> HearingCourtRequestResponse:
        from hearing_calendar import hearing_requests

        try:
            return HearingCourtRequestResponse(**hearing_requests.request_court(
                payload.hearing_id, payload.kind, actor=payload.edited_by, reasons=payload.reasons, form=payload.form, draft=payload.draft,
            ))
        except Exception as exc:
            raise _hearing_failure(exc, "request") from exc

    @app.post(
        "/client-viewer/hearings/court-decision",
        response_model=HearingResponse,
        dependencies=[Depends(require_token)],
        summary="Record the court's answer to a request: agreed (vacated, or hybrid) or refused (back to normal)",
    )
    def post_hearing_court_decision(payload: HearingCourtDecisionRequest) -> HearingResponse:
        try:
            return HearingResponse(hearing=hearing_store.court_decision(payload.hearing_id, payload.agreed, actor=payload.edited_by))
        except Exception as exc:
            raise _hearing_failure(exc, "court decision") from exc

    @app.post(
        "/client-viewer/hearings/review-resolve",
        response_model=HearingResponse,
        dependencies=[Depends(require_token)],
        summary="Confirm (optionally with edits) or dismiss a hearing in the review queue",
    )
    def post_hearing_review_resolve(payload: HearingReviewResolveRequest) -> HearingResponse:
        try:
            return HearingResponse(hearing=hearing_store.resolve_review(payload.hearing_id, payload.action, actor=payload.edited_by, edits=payload.edits))
        except Exception as exc:
            raise _hearing_failure(exc, "review resolve") from exc

    @app.post(
        "/client-viewer/hearings/link",
        response_model=HearingLinkResponse,
        dependencies=[Depends(require_token)],
        summary="Link a hearing to a client; the case number is remembered so the next email links itself",
    )
    def post_hearing_link(payload: HearingLinkRequest) -> HearingLinkResponse:
        try:
            return HearingLinkResponse(**hearing_store.link_hearing_to_matter(payload.hearing_id, payload.matter_id, actor=payload.edited_by))
        except Exception as exc:
            raise _hearing_failure(exc, "link") from exc

    @app.post(
        "/client-viewer/hearings/unlink",
        response_model=HearingResponse,
        dependencies=[Depends(require_token)],
        summary="Take a hearing off its client; it is then never auto-linked again",
    )
    def post_hearing_unlink(payload: HearingUnlinkRequest) -> HearingResponse:
        try:
            return HearingResponse(hearing=hearing_store.unlink_hearing(payload.hearing_id, actor=payload.edited_by))
        except Exception as exc:
            raise _hearing_failure(exc, "unlink") from exc

    @app.get(
        "/client-viewer/hearings/suggest-matters",
        response_model=HearingSuggestionsResponse,
        dependencies=[Depends(require_token)],
        summary="Fuzzy client suggestions for an unlinked hearing; a person chooses, nothing is applied",
    )
    def get_hearing_suggestions(request: Request, hearing_id: int = Query(...)) -> HearingSuggestionsResponse:
        try:
            suggestions = hearing_store.suggest_matters(hearing_id)
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            _refuse_if_exposure_blocked(enforce_client_exposure_budget(
                budget_identity((request.headers.get("Remote-User") or "").strip()),
                [{"matter_id": row["matter_id"], "canonical_name": row["client_name"]} for row in suggestions],
                source="hearings_suggest",
            ))
            return HearingSuggestionsResponse(suggestions=suggestions)
        except HTTPException:
            raise
        except Exception as exc:
            raise _hearing_failure(exc, "suggest") from exc

    @app.get(
        "/client-viewer/hearings/leads",
        response_model=HearingLeadsResponse,
        dependencies=[Depends(require_token)],
        summary="Emails that look like hearing notices but could not be read into a hearing",
    )
    def get_hearing_leads() -> HearingLeadsResponse:
        try:
            return HearingLeadsResponse(leads=hearing_store.list_leads("open"))
        except Exception as exc:
            raise _hearing_failure(exc, "leads") from exc

    @app.post(
        "/client-viewer/hearings/leads/resolve",
        response_model=HearingLeadResponse,
        dependencies=[Depends(require_token)],
        summary="Mark a lead done (a person handled it) or dismissed (not a hearing)",
    )
    def post_hearing_lead_resolve(payload: HearingLeadResolveRequest) -> HearingLeadResponse:
        try:
            return HearingLeadResponse(lead=hearing_store.resolve_lead(payload.lead_id, payload.action, actor=payload.edited_by))
        except Exception as exc:
            raise _hearing_failure(exc, "lead resolve") from exc

    @app.get(
        "/client-viewer/hearings/history",
        response_model=HearingHistoryResponse,
        dependencies=[Depends(require_token)],
        summary="Who changed a hearing, when, and what it was before",
    )
    def get_hearing_history(hearing_id: int = Query(...)) -> HearingHistoryResponse:
        try:
            return HearingHistoryResponse(events=hearing_store.history(hearing_id))
        except Exception as exc:
            raise _hearing_failure(exc, "history") from exc

    @app.get(
        "/client-viewer/hearings/ics",
        dependencies=[Depends(require_token)],
        summary="An iCalendar export of the hearings in a date range (download)",
    )
    def get_hearings_ics(
        request: Request,
        date_from: str = Query(..., alias="from", min_length=10, max_length=10),
        date_to: str = Query(..., alias="to", min_length=10, max_length=10),
    ) -> Response:
        try:
            rows = hearing_store.list_hearings(date_from, date_to)
            _hearings_response(rows, request, source="hearings_ics")
            body = hearing_store.render_ics(rows)
        except HTTPException:
            raise
        except Exception as exc:
            raise _hearing_failure(exc, "ics") from exc
        return Response(
            content=body, media_type="text/calendar; charset=utf-8",
            headers={"Content-Disposition": content_disposition("attachment", f"hearings-{date_from}-to-{date_to}.ics")},
        )

    @app.get(
        "/client-viewer/attention",
        response_model=AttentionResponse,
        dependencies=[Depends(require_token)],
        summary="Open complaints, tasks, settlements, scope creep, counsel replies and monitor obligations across every client, for the header bell",
    )
    def get_attention(request: Request) -> AttentionResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            result = matter_tasks.attention()
        except Exception as exc:
            log.error("attention read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Attention list unavailable") from exc

        shown = [
            {"matter_id": item.get("matter_id"), "client_name": item.get("who")}
            for item in (
                result["red"] + result["yellow"] + result["green"] + result["scope_creep"]
                + result["counsel_accepted"] + result["counsel_rejected"]
                + result.get("court_order", []) + result.get("court_rejected", [])
            )
            if item.get("matter_id")
        ] + [
            {"matter_id": ob.get("matter_id"), "client_name": ob.get("client")}
            for ob in result["obligations"]
            if ob.get("matter_id")
        ]
        if shown:
            from vergil.user_state import (
                budget_identity,
                enforce_client_exposure_budget,
            )

            _refuse_if_exposure_blocked(enforce_client_exposure_budget(budget_identity(remote_user), shown, source="attention"))
        for bucket in ("red", "yellow", "green", "scope_creep", "counsel_accepted", "counsel_rejected", "court_order", "court_rejected", "obligations"):
            if isinstance(result.get(bucket), list):
                result[bucket] = _same_name_labelled(result[bucket])
        return AttentionResponse(**result)

    @app.post(
        "/client-viewer/attention/complete",
        response_model=AttentionItem,
        dependencies=[Depends(require_token)],
        summary="Close one bell item from the attention store",
    )
    def complete_attention_item(payload: AttentionCompleteRequest) -> AttentionItem:
        try:
            return AttentionItem(**matter_tasks.complete_item(payload.task_id, payload.by))
        except attention_store.AttentionNotFound as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except attention_store.AttentionError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        except Exception as exc:
            log.error("attention complete failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Attention list unavailable") from exc

    @app.get(
        "/client-viewer/drafts",
        response_model=DraftsResponse,
        dependencies=[Depends(require_token)],
        summary="AI DRAFTED drafts waiting in the shared mailbox's Drafts folder (read only; nothing is sent)",
    )
    def get_drafts(request: Request) -> DraftsResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            result = mailbox_drafts.list_drafts()
        except Exception as exc:
            log.error("drafts read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Drafts unavailable") from exc
        shown = [{"matter_id": i["matter_id"], "client_name": i["client_name"]} for i in result["items"] if i.get("matter_id")]
        if shown:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            _refuse_if_exposure_blocked(enforce_client_exposure_budget(budget_identity(remote_user), shown, source="drafts"))
        return DraftsResponse(**result)

    @app.get(
        "/client-viewer/bill-of-costs",
        response_model=BillOfCostsResponse,
        dependencies=[Depends(require_token)],
        summary="This matter's billing ledger, grouped and totalled Bill-of-Costs-style",
    )
    def get_bill_of_costs(request: Request, matter_id: str = Query(..., min_length=1)) -> BillOfCostsResponse:
        _charge_matter_read(request, matter_id, "matter_bill_of_costs")
        try:
            result = bill_of_costs.bill_of_costs(matter_id)
        except Exception as exc:
            log.error("bill of costs read failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Bill of costs unavailable"
            ) from exc
        return BillOfCostsResponse(**result)

    @app.get(
        "/client-viewer/matter-summary",
        dependencies=[Depends(require_token)],
        summary="Quick-tick flags, the person's other matters, Statement of Service and Bill of Costs for one matter in one answer",
    )
    def get_matter_summary(
        request: Request,
        matter_id: str = Query(..., min_length=1),
        parts: str = Query(
            default=",".join(_MATTER_SUMMARY_PARTS),
            description="Comma-separated parts to include: " + ", ".join(_MATTER_SUMMARY_PARTS) + ".",
        ),
    ) -> dict[str, Any]:
        from concurrent.futures import ThreadPoolExecutor

        from fastapi.encoders import jsonable_encoder

        wanted = list(dict.fromkeys(part.strip() for part in parts.split(",") if part.strip()))
        unknown = [part for part in wanted if part not in _MATTER_SUMMARY_PARTS]
        if not wanted or unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "parts must name one or more of: " + ", ".join(_MATTER_SUMMARY_PARTS),
            )
        readers: dict[str, Any] = {
            "flags": lambda: get_matter_flags(request, matter_id),
            "person_matters": lambda: get_person_matters(request, matter_id),
            "sos_status": lambda: get_sos_status(matter_id),
            "bill_of_costs": lambda: get_bill_of_costs(request, matter_id),
        }

        def run(name: str) -> tuple[str, Any, bool]:
            try:
                return name, jsonable_encoder(readers[name]()), True
            except HTTPException as exc:
                log.warning("matter summary part %s failed: %s", name, exc.status_code)
            except Exception as exc:
                log.warning("matter summary part %s failed: %s", name, type(exc).__name__)
            return name, None, False

        with ThreadPoolExecutor(max_workers=len(wanted)) as pool:
            futures = [pool.submit(contextvars.copy_context().run, run, name) for name in wanted]
            results = [future.result() for future in futures]
        out: dict[str, Any] = {"matter_id": matter_id}
        out.update({name: value for name, value, _ok in results})
        out["errors"] = [name for name, _value, ok in results if not ok]
        return out

    @app.get(
        "/client-viewer/billing/daily-totals",
        dependencies=[Depends(require_token)],
        summary="Money billed per UK day over a range (default the last 30 days), for the Billing by day chart; read only",
    )
    def get_billing_daily_totals(
        start: str | None = Query(default=None, description="First day, YYYY-MM-DD."),
        end: str | None = Query(default=None, description="Last day, YYYY-MM-DD."),
    ) -> dict[str, Any]:
        import datetime as dt

        if (start is None) != (end is None):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "give both start and end, or neither")
        try:
            last = dt.date.fromisoformat(end) if end else billing_daily.london_today()
            first = dt.date.fromisoformat(start) if start else last - dt.timedelta(days=billing_daily.DEFAULT_DAYS - 1)
            return billing_daily.daily_totals(first, last)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("billing daily totals read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Billing totals unavailable") from exc

    @app.get(
        "/client-viewer/billing/export.csv",
        dependencies=[Depends(require_token)],
        summary="The matter's itemised bill as a CSV download, Bill-of-Costs-<SURNAME>.csv; writes nothing to OneDrive",
    )
    def export_bill_csv(matter_id: str = Query(..., min_length=1)) -> Response:
        try:
            filename, text = bill_export.bill_csv(matter_id)
        except Exception as exc:
            raise _pipeline_error(exc, "bill export") from exc
        return Response(
            content=text.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": content_disposition("attachment", filename)},
        )

    @app.get(
        "/client-viewer/legal-aid",
        response_model=LegalAidSectionResponse,
        dependencies=[Depends(require_token)],
        summary="The Details tab's Legal aid section for one matter: benefits, the completed application, its signed declaration",
    )
    def get_legal_aid(request: Request, matter_id: str = Query(..., min_length=1, max_length=20)) -> LegalAidSectionResponse:
        _charge_matter_read(request, matter_id, "matter_legal_aid")
        from onboarding.pipeline import legal_aid_declaration

        try:
            return LegalAidSectionResponse(**legal_aid_declaration.state(matter_id))
        except intake_pipeline.PipelineError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("legal aid section read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Legal aid is unavailable just now") from exc

    @app.post(
        "/client-viewer/legal-aid/send",
        response_model=LegalAidSendResponse,
        dependencies=[Depends(require_token)],
        summary="Send to client to sign: a Documenso envelope for the completed application and an AI DRAFTED email for a person to send (nothing is sent)",
    )
    def post_legal_aid_send(payload: LegalAidSendRequest) -> LegalAidSendResponse:
        from onboarding.pipeline import legal_aid_declaration

        try:
            outcome = legal_aid_declaration.send(payload.matter_id, payload.by, address_checked=payload.address_checked)
            section = legal_aid_declaration.state(payload.matter_id, check=False)
        except intake_pipeline.PipelineError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("legal aid send failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Legal aid is unavailable just now") from exc
        return LegalAidSendResponse(**outcome, section=LegalAidSectionResponse(**section))

    @app.get(
        "/client-viewer/flag-counts",
        dependencies=[Depends(require_token)],
        summary="How many matters carry each flag, counts only, for the header badges",
    )
    def flag_counts(
        request: Request,
        flags: str = Query(default="flagged,starred", description="Comma-separated flag names."),
    ) -> dict[str, dict[str, int]]:
        requested = [name.strip() for name in flags.split(",") if name.strip()]
        try:
            return {"counts": client_edits.count_matters_with_flags(requested, user=_flag_user(request))}
        except Exception as exc:
            log.error("flag counts lookup failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Flag counts unavailable") from exc

    @app.get(
        "/client-viewer/flagged-matters",
        response_model=FlaggedMattersResponse,
        dependencies=[Depends(require_token)],
        summary="Every matter flagged, starred, or a persistent caller (client or Respondent), for the pull-up browse view",
    )
    def flagged_matters(
        request: Request,
        flags: str = Query(
            default="flagged,starred,persistent_caller,persistent_caller_respondent",
            description="Comma-separated flag names.",
        ),
    ) -> FlaggedMattersResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        requested = [name.strip() for name in flags.split(",") if name.strip()]
        try:
            import clientdb_sql

            flags_by_matter = client_edits.list_matters_with_flags(requested, user=_flag_user(request))
            rows = client_rows.rows_for(list(flags_by_matter))
        except Exception as exc:
            log.error("flagged matters lookup failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Flagged matters lookup unavailable"
            ) from exc

        if rows:
            from vergil.user_state import (
                budget_identity,
                enforce_client_exposure_budget,
            )

            exposure = enforce_client_exposure_budget(
                budget_identity(remote_user), rows, source="flagged_matters"
            )
            if exposure.get("block"):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    _client_exposure_limit_detail(exposure.get("categories"), verb="window"),
                )

        return FlaggedMattersResponse(
            results=_client_matches(rows),
            flags_by_matter=flags_by_matter,
            flag_reasons_by_matter=_flag_list_reasons(flags_by_matter, _flag_user(request)),
        )

    @app.get(
        "/client-viewer/attendance-notes/folders",
        dependencies=[Depends(require_token)],
        summary="The attendance notes folders a matter already has, for the folder choice on the note form",
    )
    def attendance_note_folders(matter_id: str) -> dict[str, Any]:
        import agwu

        folder = agwu.resolve_folder(matter_id, allow_live_fallback=False, caller="attendance_note_folders")
        if getattr(folder, "status", "not_found") == "not_found":
            return {"folders": []}
        return {"folders": agwu.folder.attendance_folders_of(folder.matter_folder_id, folder.drive_id)}

    @app.post(
        "/client-viewer/attendance-notes/create",
        response_model=CreateAttendanceNoteResponse,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_token)],
        summary="Queue one attendance note (caller + content): saved now, filed and billed in the background",
    )
    def create_attendance_note(payload: CreateAttendanceNoteRequest) -> CreateAttendanceNoteResponse:
        from billing import letter_notes as _letter_notes

        if not _letter_notes.clean_folder(payload.attendance_folder):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose an attendance notes folder: FLA, CA or Other.")
        try:
            row = attendance_note_drafts.create_queued(
                matter_id=payload.matter_id,
                caller=payload.caller,
                caller_other=payload.caller_other,
                note_text=payload.note_text,
                time_minutes=payload.time_minutes,
                kind=payload.kind,
                pages=payload.pages,
                doc_kind=payload.doc_kind or None,
                doc_other=payload.doc_other,
                attendance_folder=payload.attendance_folder,
            )
        except attendance_note_drafts.AttendanceNoteDraftError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("attendance note create failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Attendance note creation unavailable") from exc
        attendance_note_drafts.start_background_commit(row["draft_id"])
        return CreateAttendanceNoteResponse(
            draft_id=row["draft_id"], matter_id=row["matter_id"], status=row["status"]
        )

    @app.get(
        "/client-viewer/settings/minutes-per-page",
        response_model=MinutesPerPageResponse,
        dependencies=[Depends(require_token)],
        summary="The firm's minutes a page for perusal and preparation",
    )
    def get_minutes_per_page() -> MinutesPerPageResponse:
        from billing import letter_notes

        return MinutesPerPageResponse(minutes_per_page=letter_notes.minutes_per_page())

    @app.put(
        "/client-viewer/settings/minutes-per-page",
        response_model=MinutesPerPageResponse,
        dependencies=[Depends(require_token)],
        summary="Set the minutes a page (administrators only; audited; only notes made afterwards use it)",
    )
    async def put_minutes_per_page(request: Request, actor: str = Depends(require_verified_admin)) -> MinutesPerPageResponse:
        from billing import letter_notes
        from vergil import settings_admin

        _body_size_ok(request)
        payload = await _legacy_payload(request, MinutesPerPageRequest, settings_admin.MAX_SETTINGS_BODY)
        _apply_settings(actor, {"minutes_per_page": payload.minutes_per_page})
        return MinutesPerPageResponse(minutes_per_page=letter_notes.minutes_per_page())

    def _body_size_ok(request: Request) -> None:
        from vergil import settings_admin

        declared = (request.headers.get("content-length") or "").strip()
        if declared.isdigit() and int(declared) > settings_admin.MAX_SETTINGS_BODY + 600 * 1024:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Request too large")

    async def _capped_body(request: Request, limit: int) -> bytes:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > limit:
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Request too large")
        return bytes(body)

    async def _legacy_payload(request: Request, model, limit: int):
        raw = await _capped_body(request, limit)
        try:
            return model.model_validate_json(raw)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Send a valid value") from exc

    def _apply_settings(actor: str, values: dict) -> None:
        import app_settings

        try:
            app_settings.apply_changes(actor, values)
        except app_settings.UnknownSetting as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such setting") from exc
        except app_settings.SettingLocked as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except app_settings.SettingError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            log.error("settings not saved: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Settings not saved") from exc

    def _settings_view(request: Request) -> AppSettingsResponse:
        from vergil import settings_admin

        try:
            return AppSettingsResponse(**settings_admin.build_view(can_edit=bool(verified_admin_email(request))))
        except Exception as exc:
            log.error("settings view failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Settings unavailable") from exc

    @app.get(
        "/client-viewer/settings",
        response_model=AppSettingsResponse,
        dependencies=[Depends(require_token)],
        summary="Every runtime setting with its schema, value, source and lock (no secrets exist here)",
    )
    def get_app_settings(request: Request) -> AppSettingsResponse:
        return _settings_view(request)

    @app.patch(
        "/client-viewer/settings",
        response_model=AppSettingsResponse,
        dependencies=[Depends(require_token)],
        summary="Change several settings all or nothing (administrators only; audited; a blank value restores the default)",
    )
    async def patch_app_settings(request: Request, actor: str = Depends(require_verified_admin)) -> AppSettingsResponse:
        from vergil import settings_admin

        _body_size_ok(request)
        raw = await _capped_body(request, settings_admin.MAX_SETTINGS_BODY)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed request") from exc
        values = payload.get("values") if isinstance(payload, dict) else None
        if not isinstance(values, dict) or not values or len(values) > 100:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Send the settings to change as {\"values\": {...}}")
        _apply_settings(actor, values)
        return _settings_view(request)

    @app.put(
        "/client-viewer/settings/key/{key}",
        response_model=AppSettingsResponse,
        dependencies=[Depends(require_token)],
        summary="Change one setting (administrators only; audited; a blank value restores the default)",
    )
    async def put_app_setting(key: str, request: Request, actor: str = Depends(require_verified_admin)) -> AppSettingsResponse:
        from vergil import settings_admin

        _body_size_ok(request)
        raw = await _capped_body(request, settings_admin.MAX_SETTINGS_BODY)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed request") from exc
        if not isinstance(payload, dict) or "value" not in payload:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Send {\"value\": ...}")
        _apply_settings(actor, {key: payload["value"]})
        return _settings_view(request)

    @app.put(
        "/client-viewer/settings/operations/{key}",
        response_model=AppSettingsResponse,
        dependencies=[Depends(require_token)],
        summary="Hold or release one automatic operation (administrators only)",
    )
    async def put_operation_switch(key: str, request: Request, actor: str = Depends(require_verified_admin)) -> AppSettingsResponse:
        from vergil import settings_admin

        _body_size_ok(request)
        raw = await _capped_body(request, settings_admin.MAX_SETTINGS_BODY)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed request") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("held"), bool):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Send {\"held\": true or false}")
        try:
            settings_admin.set_operation(actor, key, payload["held"])
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such switch") from exc
        except Exception as exc:
            log.error("operation switch not saved: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Switch not saved") from exc
        return _settings_view(request)

    @app.get(
        "/client-viewer/settings/special-senders",
        response_model=SpecialSendersResponse,
        dependencies=[Depends(require_token)],
        summary="The special senders (name, domains, new-clients switch, logo hash) the CRM marks and sorts first",
    )
    def get_special_senders() -> SpecialSendersResponse:
        from vergil import special_senders

        try:
            return SpecialSendersResponse(**special_senders.view())
        except Exception as exc:
            log.error("special senders read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Special senders unavailable") from exc

    @app.put(
        "/client-viewer/settings/special-senders",
        response_model=SpecialSendersResponse,
        dependencies=[Depends(require_token)],
        summary="Replace the special senders (administrators only; audited; a sender keeps its logo while its id is kept)",
    )
    async def put_special_senders(request: Request, actor: str = Depends(require_verified_admin)) -> SpecialSendersResponse:
        from vergil import settings_admin, special_senders

        _body_size_ok(request)
        payload = await _legacy_payload(request, SpecialSendersRequest, settings_admin.MAX_SETTINGS_BODY)
        try:
            return SpecialSendersResponse(**special_senders.save([s.model_dump() for s in payload.senders], actor))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("special senders not saved: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The special senders were not saved") from exc

    @app.get(
        "/client-viewer/settings/special-senders/{sender_id}/logo",
        dependencies=[Depends(require_token)],
        summary="One special sender's logo file (404 when it has none)",
    )
    def get_special_sender_logo(sender_id: str) -> Response:
        from vergil import special_senders

        found = special_senders.logo(sender_id)
        if not found:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No logo")
        return Response(content=found[0], media_type=found[1], headers={"X-Content-Type-Options": "nosniff"})

    @app.post(
        "/client-viewer/settings/special-senders/{sender_id}/logo",
        response_model=LogoResponse,
        dependencies=[Depends(require_token)],
        summary="Upload one special sender's logo (administrators only; the type is read from the bytes; an SVG is checked and cleaned)",
    )
    async def post_special_sender_logo(sender_id: str, request: Request, actor: str = Depends(require_verified_admin)) -> LogoResponse:
        from vergil import branding_logo, special_senders

        _body_size_ok(request)
        data = await _capped_body(request, branding_logo.MAX_BYTES)
        try:
            return LogoResponse(logo=special_senders.set_logo(sender_id, data, actor))
        except (branding_logo.LogoError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("special sender logo not saved: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Logo not saved") from exc

    @app.delete(
        "/client-viewer/settings/special-senders/{sender_id}/logo",
        response_model=LogoResponse,
        dependencies=[Depends(require_token)],
        summary="Remove one special sender's logo (administrators only; audited)",
    )
    def delete_special_sender_logo(sender_id: str, actor: str = Depends(require_verified_admin)) -> LogoResponse:
        from vergil import special_senders

        try:
            special_senders.clear_logo(sender_id, actor)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        return LogoResponse(logo="")

    @app.get(
        "/client-viewer/settings/models",
        response_model=ModelRolesResponse,
        dependencies=[Depends(require_token)],
        summary="Every model role: the model now, where it came from, and 14 days of aggregate use (no prompts, no client data)",
    )
    def get_model_roles(_dev: str = Depends(require_verified_dev)) -> ModelRolesResponse:
        from vergil import model_roles_admin

        try:
            return ModelRolesResponse(**model_roles_admin.build_view(can_edit=True))
        except Exception as exc:
            log.error("model roles view failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Models unavailable") from exc

    @app.put(
        "/client-viewer/settings/models/{role}",
        response_model=ModelRoleChangeResponse,
        dependencies=[Depends(require_token)],
        summary="Swap the model for one role to a model already in use (developers only; audited; next call uses it)",
    )
    async def put_model_role(role: str, request: Request, by: str = Depends(require_verified_dev)) -> ModelRoleChangeResponse:
        from vergil import model_roles_admin

        raw = await _capped_body(request, 4096)
        try:
            payload = ModelRoleSwapRequest.model_validate_json(raw)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Send a role's model") from exc
        try:
            return ModelRoleChangeResponse(**model_roles_admin.set_role_model(role, payload.model, by, payload.expected_old))
        except model_roles_admin.ModelSwapError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    @app.delete(
        "/client-viewer/settings/models/{role}",
        response_model=ModelRoleChangeResponse,
        dependencies=[Depends(require_token)],
        summary="Put one role back to the model roles file's default (developers only; audited)",
    )
    def delete_model_role(role: str, by: str = Depends(require_verified_dev)) -> ModelRoleChangeResponse:
        from vergil import model_roles_admin

        try:
            return ModelRoleChangeResponse(**model_roles_admin.reset_role_model(role, by))
        except model_roles_admin.ModelSwapError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    async def _folder_map_entries(request: Request) -> Any:
        raw = await _capped_body(request, 16 * 1024)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed request") from exc
        return payload.get("entries") if isinstance(payload, dict) else None

    @app.get(
        "/client-viewer/settings/folder-map",
        dependencies=[Depends(require_token)],
        summary="The folders a new client gets, today's standard map, and a preview (no client data)",
    )
    def get_folder_map(request: Request) -> dict:
        import folder_map

        return folder_map.view(can_edit=bool(verified_admin_email(request)))

    @app.post(
        "/client-viewer/settings/folder-map/preview",
        dependencies=[Depends(require_token)],
        summary="Check an edited folder map and show what a new client would get; saves nothing",
    )
    async def post_folder_map_preview(request: Request) -> dict:
        import folder_map

        entries = await _folder_map_entries(request)
        try:
            return folder_map.preview(entries)
        except folder_map.FolderMapError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    @app.put(
        "/client-viewer/settings/folder-map",
        dependencies=[Depends(require_token)],
        summary="Save the folder map for clients opened from now on (administrators only; audited; existing folders untouched)",
    )
    async def put_folder_map(request: Request, actor: str = Depends(require_verified_admin)) -> dict:
        import folder_map

        entries = await _folder_map_entries(request)
        try:
            folder_map.save(actor, entries)
        except folder_map.FolderMapError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("folder map not saved: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The folder map was not saved") from exc
        return folder_map.view(can_edit=True)

    @app.delete(
        "/client-viewer/settings/folder-map",
        dependencies=[Depends(require_token)],
        summary="Go back to the standard folder map for clients opened from now on (administrators only; audited)",
    )
    def delete_folder_map(actor: str = Depends(require_verified_admin)) -> dict:
        import folder_map

        folder_map.save(actor, folder_map.defaults())
        return folder_map.view(can_edit=True)

    @app.get(
        "/client-viewer/settings/scanned-docs-folder",
        response_model=ScannedFolderResponse,
        dependencies=[Depends(require_token)],
        summary="The OneDrive folder scanned documents wait in (the Scans view, the board and the monitor read it)",
    )
    def get_scanned_docs_folder() -> ScannedFolderResponse:
        from scanned_docs import scan_setting
        from scanned_docs.intake_facts import DEFAULT_SCANNED_DOCS_PATH

        return ScannedFolderResponse(path=scan_setting.scanned_docs_path(), default=DEFAULT_SCANNED_DOCS_PATH)

    @app.put(
        "/client-viewer/settings/scanned-docs-folder",
        response_model=ScannedFolderResponse,
        dependencies=[Depends(require_token)],
        summary="Set the scanned documents folder (administrators only; audited; an empty path goes back to the default)",
    )
    async def put_scanned_docs_folder(request: Request, actor: str = Depends(require_verified_admin)) -> ScannedFolderResponse:
        from scanned_docs import scan_setting
        from scanned_docs.intake_facts import DEFAULT_SCANNED_DOCS_PATH
        from vergil import settings_admin

        _body_size_ok(request)
        payload = await _legacy_payload(request, ScannedFolderRequest, settings_admin.MAX_SETTINGS_BODY)
        _apply_settings(actor, {"scanned_docs_folder": payload.path})
        return ScannedFolderResponse(path=scan_setting.scanned_docs_path(), default=DEFAULT_SCANNED_DOCS_PATH)

    def _email_classifier_view() -> EmailClassifierResponse:
        import email_sorter_common
        from mail_intake import routing_overrides

        stored = routing_overrides.load()
        lists = {}
        for name in routing_overrides.editable_lists():
            live = getattr(email_sorter_common, name.upper(), None)
            base = tuple(getattr(live, "_base", ()) or ())
            added = list((stored["add"].get(name) or []))
            removed = list((stored["remove"].get(name) or []))
            effective = list(routing_overrides.apply(name, base, stored))
            lists[name] = {"default": list(base), "added": added, "removed": removed, "effective": effective}
        audit = [{k: str(v) for k, v in row.items()} for row in stored["_audit"][-10:]]
        return EmailClassifierResponse(lists=lists, audit=audit)

    @app.get(
        "/client-viewer/settings/email-classifier",
        response_model=EmailClassifierResponse,
        dependencies=[Depends(require_token)],
        summary="The email classifier's sender and keyword lists: shipped entries, firm-wide additions and removals, and recent changes",
    )
    def get_email_classifier() -> EmailClassifierResponse:
        return _email_classifier_view()

    @app.put(
        "/client-viewer/settings/email-classifier",
        response_model=EmailClassifierResponse,
        dependencies=[Depends(require_token)],
        summary="Replace the email classifier's added and removed entries (administrators only; audited; reaches the classifier within a minute)",
    )
    async def put_email_classifier(request: Request, actor: str = Depends(require_verified_admin)) -> EmailClassifierResponse:
        import email_sorter_common
        from mail_intake import routing_overrides
        from vergil import settings_admin

        _body_size_ok(request)
        payload = await _legacy_payload(request, EmailClassifierRequest, settings_admin.MAX_SETTINGS_BODY)
        try:
            routing_overrides.save({"add": payload.add, "remove": payload.remove}, actor)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("email classifier settings not saved: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The classifier settings were not saved") from exc
        email_sorter_common.reload()
        return _email_classifier_view()

    @app.get(
        "/client-viewer/attendance-notes/status",
        response_model=AttendanceNoteStatus,
        dependencies=[Depends(require_token)],
        summary="Where one queued attendance note is: filing, filed or failed",
    )
    def attendance_note_status(draft_id: str = Query(..., min_length=1)) -> AttendanceNoteStatus:
        try:
            view = attendance_note_drafts.status_of(draft_id)
        except Exception as exc:
            log.error("attendance note status failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Attendance note status unavailable") from exc
        if view is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such attendance note")
        return AttendanceNoteStatus(**view)

    @app.get(
        "/client-viewer/attendance-notes/recent",
        response_model=AttendanceNoteRecentResponse,
        dependencies=[Depends(require_token)],
        summary="Attendance notes queued for one matter in the last few hours, newest first",
    )
    def attendance_note_recent(
        matter_id: str = Query(..., min_length=1), hours: int = Query(default=48, ge=1, le=720)
    ) -> AttendanceNoteRecentResponse:
        try:
            items = attendance_note_drafts.list_recent(matter_id, hours=hours)
        except Exception as exc:
            log.error("attendance note recent failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Recent attendance notes unavailable") from exc
        return AttendanceNoteRecentResponse(items=[AttendanceNoteStatus(**item) for item in items])

    @app.post(
        "/client-viewer/attendance-notes/retry",
        response_model=AttendanceNoteStatus,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_token)],
        summary="Queue a failed attendance note again",
    )
    def attendance_note_retry(payload: RetryAttendanceNoteRequest) -> AttendanceNoteStatus:
        try:
            view = attendance_note_drafts.retry(payload.draft_id)
        except attendance_note_drafts.AttendanceNoteDraftError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("attendance note retry failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Attendance note retry unavailable") from exc
        attendance_note_drafts.start_background_commit(payload.draft_id)
        return AttendanceNoteStatus(**view)

    @app.post(
        "/client-viewer/attendance-notes/edit",
        response_model=AttendanceNoteEditResponse,
        dependencies=[Depends(require_token)],
        summary="Take a note that did not file back to change; the robot stops trying it",
    )
    def attendance_note_edit(payload: RetryAttendanceNoteRequest) -> AttendanceNoteEditResponse:
        try:
            taken = attendance_note_drafts.take_for_edit(payload.draft_id)
        except attendance_note_drafts.AttendanceNoteDraftError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("attendance note edit failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Attendance note edit unavailable") from exc
        return AttendanceNoteEditResponse(**taken)

    def _todo_error(exc: Exception, what: str) -> HTTPException:
        if isinstance(exc, todo_store.TodoError):
            return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
        log.error("todo %s failed: %s", what, type(exc).__name__)
        return HTTPException(status.HTTP_502_BAD_GATEWAY, "Tasks unavailable")

    def _todo_owner(request: Request) -> str:
        return client_edits.personal_user(request.headers.get("Remote-User"))

    @app.get(
        "/client-viewer/todos",
        response_model=TodosResponse,
        dependencies=[Depends(require_token)],
        summary="The caller's own tasks for one view (my day, important, planned, tasks, completed, all) or one client",
    )
    def list_todos(
        request: Request,
        view: str = Query(default="all"),
        matter_id: int | None = Query(default=None),
        include_done: bool = Query(default=False),
    ) -> TodosResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        owner = _todo_owner(request)
        try:
            items = todo_store.list_todos(view=view, matter_id=matter_id, include_done=include_done, owner=owner)
            counts = todo_store.summary(owner=owner)
        except Exception as exc:
            raise _todo_error(exc, "list") from exc
        shown = [{"matter_id": item["matter_id"], "client_name": item.get("client_name")} for item in items if item.get("matter_id")]
        if shown:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            _refuse_if_exposure_blocked(enforce_client_exposure_budget(budget_identity(remote_user), shown, source="todos"))
        return TodosResponse(items=[TodoItem(**item) for item in items], summary=counts)

    @app.get(
        "/client-viewer/todos/summary",
        response_model=TodoSummaryResponse,
        dependencies=[Depends(require_token)],
        summary="Task counts for the header badge and the list sidebar",
    )
    def todos_summary(request: Request) -> TodoSummaryResponse:
        try:
            return TodoSummaryResponse(summary=todo_store.summary(owner=_todo_owner(request)))
        except Exception as exc:
            raise _todo_error(exc, "summary") from exc

    @app.post(
        "/client-viewer/todos",
        response_model=TodoItem,
        dependencies=[Depends(require_token)],
        summary="Add a task",
    )
    def create_todo(request: Request, payload: CreateTodoRequest) -> TodoItem:
        try:
            item = todo_store.create(
                payload.title, created_by=payload.created_by, matter_id=payload.matter_id, owner=_todo_owner(request),
                due=payload.due, due_has_time=payload.due_has_time, starred=payload.starred, my_day=payload.my_day,
                notes=payload.notes,
            )
        except Exception as exc:
            raise _todo_error(exc, "create") from exc
        return TodoItem(**item)

    @app.post(
        "/client-viewer/todos/update",
        response_model=TodoItem,
        dependencies=[Depends(require_token)],
        summary="Change one of the caller's own tasks: title, notes, due moment, star, my day or client",
    )
    def update_todo(request: Request, payload: UpdateTodoRequest) -> TodoItem:
        try:
            return TodoItem(**todo_store.update(payload.todo_id, payload.fields, by=payload.by, owner=_todo_owner(request)))
        except Exception as exc:
            raise _todo_error(exc, "update") from exc

    @app.post(
        "/client-viewer/todos/complete",
        response_model=TodoItem,
        dependencies=[Depends(require_token)],
        summary="Tick a task off, or reopen it",
    )
    def complete_todo(request: Request, payload: CompleteTodoRequest) -> TodoItem:
        try:
            return TodoItem(**todo_store.complete(payload.todo_id, payload.done, by=payload.by, owner=_todo_owner(request)))
        except Exception as exc:
            raise _todo_error(exc, "complete") from exc

    @app.post(
        "/client-viewer/todos/delete",
        dependencies=[Depends(require_token)],
        summary="Delete a task for good",
    )
    def delete_todo(request: Request, payload: DeleteTodoRequest) -> dict[str, bool]:
        try:
            todo_store.delete(payload.todo_id, by=payload.by, owner=_todo_owner(request))
        except Exception as exc:
            raise _todo_error(exc, "delete") from exc
        return {"ok": True}

    @app.post(
        "/client-viewer/todos/automatic",
        response_model=TodoSummaryResponse,
        dependencies=[Depends(require_token)],
        summary="Switch the automatic to-do categories on or off for the whole firm (any signed-in login)",
    )
    def set_todo_automatic(request: Request, payload: TodoAutomaticRequest) -> TodoSummaryResponse:
        owner = _todo_owner(request)
        if not owner:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "sign in to change this")
        known = {key for key, _, _ in todo_store.CATEGORIES}
        unknown = sorted(set(payload.hidden) - known)
        if unknown:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown categories: {unknown}")
        try:
            import app_settings

            app_settings.apply_changes(owner, {"todo_show_automatic": payload.show, "todo_hidden_categories": ",".join(sorted(set(payload.hidden)))})
            return TodoSummaryResponse(summary=todo_store.summary(owner=owner))
        except Exception as exc:
            raise _todo_error(exc, "automatic") from exc

    @app.post(
        "/client-viewer/todos/email-client",
        response_model=TodoEmailClientResponse,
        dependencies=[Depends(require_token)],
        summary="Make an AI DRAFTED Outlook draft to the task's client; never sent",
    )
    def email_client_todo(request: Request, payload: DeleteTodoRequest) -> TodoEmailClientResponse:
        try:
            return TodoEmailClientResponse(**todo_email.draft_for_todo(payload.todo_id, by=payload.by, owner=_todo_owner(request)))
        except Exception as exc:
            raise _todo_error(exc, "email-client") from exc

    def _pipeline_error(exc: Exception, what: str) -> HTTPException:
        if isinstance(exc, intake_pipeline.PipelineError):
            return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
        log.error("pipeline %s failed: %s", what, type(exc).__name__)
        return HTTPException(status.HTTP_502_BAD_GATEWAY, "The pipeline is unavailable just now")

    @app.get(
        "/client-viewer/pipeline",
        response_model=PipelineResponse,
        dependencies=[Depends(require_token)],
        summary="The five-step new-client pipeline for one matter: mode, each step as it is now, the activity log",
    )
    def get_pipeline(
        matter_id: str = Query(..., min_length=1), fresh: bool = Query(False), poll: bool = Query(False)
    ) -> PipelineResponse:
        try:
            from onboarding.pipeline import sync_scan

            picture = dict(intake_pipeline.pipeline(matter_id, fresh=fresh, poll=poll, stale_ok=True))
            picture["sync"] = sync_scan.saved([matter_id]).get(str(matter_id))
            return PipelineResponse(**picture)
        except Exception as exc:
            raise _pipeline_error(exc, "read") from exc

    def _note_activity_view(matter_id: str, viewer: str) -> list[dict[str, str]]:
        if not viewer:
            return []
        import ops_db

        from vergil import activity_views

        try:
            with ops_db.connect() as conn:
                activity_views.record(conn, matter_id, viewer)
                return activity_views.recent(conn, matter_id, exclude=viewer)
        except Exception as exc:
            log.warning("activity view not recorded: %s", type(exc).__name__)
            return []

    @app.get(
        "/client-viewer/pipeline/events",
        response_model=PipelineActivityResponse,
        dependencies=[Depends(require_token)],
        summary="The activity log for one matter by itself (a database read; no step is checked)",
    )
    def get_pipeline_events(request: Request, matter_id: str = Query(..., min_length=1)) -> PipelineActivityResponse:
        try:
            view = intake_pipeline.activity(matter_id)
        except Exception as exc:
            raise _pipeline_error(exc, "events") from exc
        view["seen_by"] = _note_activity_view(matter_id, verified_user_email(request))
        return PipelineActivityResponse(**view)

    @app.get(
        "/client-viewer/intro-link",
        response_model=IntroLinkResponse,
        dependencies=[Depends(require_token)],
        summary="The stored link to the client's referrer intro, for the header (a database read; nothing is looked for)",
    )
    def get_intro_link(matter_id: str = Query(..., min_length=1)) -> IntroLinkResponse:
        try:
            return IntroLinkResponse(matter_id=matter_id, url=intake_markers.stored_link(matter_id, "intro"))
        except Exception as exc:
            raise _pipeline_error(exc, "intro link") from exc

    @app.get(
        "/client-viewer/matter-markers",
        response_model=MatterMarkersResponse,
        dependencies=[Depends(require_token)],
        summary="Whether the system filed a signed Letter of Authority, and whether the client's own witness statement and intro are on record, for the Details section (a database read; nothing is looked for)",
    )
    def get_matter_markers(matter_id: str = Query(..., min_length=1)) -> MatterMarkersResponse:
        try:
            return MatterMarkersResponse(**intake_markers.stored_view(matter_id))
        except Exception as exc:
            raise _pipeline_error(exc, "markers") from exc

    @app.get(
        "/client-viewer/matter-milestones",
        dependencies=[Depends(require_token)],
        summary="One matter's five milestone times (contacted, papers signed, filed, legal aid done, invoice paid); live=true also searches Sent Items for the ones not yet recorded",
    )
    def get_matter_milestones(matter_id: str = Query(..., min_length=1, max_length=40), live: bool = Query(default=False)) -> dict[str, Any]:
        try:
            if live:
                matter_milestones.fill_live(matter_id)
            else:
                matter_milestones.fill_cheap([matter_id])
            return {"matter_id": matter_id, "milestones": matter_milestones.stored(matter_id)}
        except matter_milestones.MilestoneError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("matter milestones read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Milestones unavailable") from exc

    @app.post(
        "/client-viewer/matter-milestones",
        dependencies=[Depends(require_token)],
        summary="Record legal aid done or invoice paid on a matter by hand, or clear it, under the verified sign-in",
    )
    def post_matter_milestone(payload: MatterMilestoneRequest, request: Request) -> dict[str, Any]:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            if payload.clear:
                result = matter_milestones.clear_by_hand(payload.matter_id, payload.milestone, by=signin_names.display_name(remote_user))
            else:
                result = matter_milestones.set_by_hand(payload.matter_id, payload.milestone, payload.at, by=signin_names.display_name(remote_user))
        except matter_milestones.MilestoneError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("matter milestone write failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Milestones unavailable") from exc
        return {**result, "milestones": matter_milestones.stored(payload.matter_id)}

    @app.post(
        "/client-viewer/wetransfer-gate",
        dependencies=[Depends(require_token)],
        summary="A person gives permission, for one matter, to download its documents from WeTransfer; refused when nothing is waiting for it",
    )
    def post_wetransfer_gate(payload: WeTransferGateRequest, request: Request) -> dict[str, Any]:
        from onboarding.pipeline import wetransfer_gate

        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            if not wetransfer_gate.pending(payload.matter_id):
                raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for a WeTransfer permission on this matter")
            return wetransfer_gate.grant(payload.matter_id, signin_names.display_name(remote_user))
        except HTTPException:
            raise
        except Exception as exc:
            raise _pipeline_error(exc, "wetransfer gate") from exc

    @app.get(
        "/client-viewer/ws-candidates",
        dependencies=[Depends(require_token)],
        summary="The WS PDFs in a client's Client's Docs folder, each with whether it reads as signed, for a person to record the signed statement (read only)",
    )
    def get_ws_candidates(matter_id: str = Query(..., min_length=1, max_length=40, pattern=r"^\d+$")) -> dict[str, Any]:
        from onboarding.pipeline import markers as pipeline_markers

        try:
            rows = pipeline_markers.ws_candidates(matter_id)
        except Exception as exc:
            log.error("ws candidates read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The client's folder could not be read") from exc
        return {"files": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]}

    @app.post(
        "/client-viewer/record-signed-ws",
        dependencies=[Depends(require_token)],
        summary="A person records which WS PDF is the client's signed witness statement; the file itself is not changed",
    )
    def post_record_signed_ws(payload: RecordSignedWsRequest, request: Request) -> dict[str, Any]:
        from onboarding.pipeline import markers as pipeline_markers

        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            return pipeline_markers.record_ws_by_hand(payload.matter_id, payload.item_id, signin_names.display_name(remote_user))
        except LookupError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except Exception as exc:
            raise _pipeline_error(exc, "record signed statement") from exc

    @app.get(
        "/client-viewer/court-prep",
        dependencies=[Depends(require_token)],
        summary="Court Prep (prototype): each client's next hearing with court replied, client informed, counsel booked, bundle and brief dates (stored state only)",
    )
    def get_court_prep(request: Request) -> dict[str, Any]:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            result = court_prep.board()
        except Exception as exc:
            log.error("court prep read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Court Prep unavailable") from exc
        shown = [{"matter_id": i["matter_id"], "client_name": i["client_name"]} for i in result["items"]]
        if shown:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            _refuse_if_exposure_blocked(enforce_client_exposure_budget(budget_identity(remote_user), shown, source="court_prep"))
        return result

    @app.get(
        "/client-viewer/status-board",
        dependencies=[Depends(require_token)],
        summary="Every open matter with its milestone times, date joined, letter of authority and 1st witness statement (stored state only: no mailbox or folder read)",
    )
    def get_status_board(request: Request) -> dict[str, Any]:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            result = matter_milestones.board()
        except Exception as exc:
            log.error("status board read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Status board unavailable") from exc
        shown = [{"matter_id": i["matter_id"], "client_name": i["client_name"]} for i in result["items"]]
        if shown:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            _refuse_if_exposure_blocked(enforce_client_exposure_budget(budget_identity(remote_user), shown, source="status_board"))
        return result

    @app.post(
        "/client-viewer/nudge",
        dependencies=[Depends(require_token)],
        summary="Make the reminder email for a client who is holding something up, as an Outlook draft (never sent); refused when nothing is waiting",
        response_model=ClientNudgeResponse,
    )
    def post_client_nudge(payload: ClientNudgeRequest, request: Request) -> dict[str, Any]:
        from todos import client_nudge

        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            made = client_nudge.nudge(payload.matter_id, payload.doc, signin_names.display_name(remote_user))
        except client_nudge.NudgeRefused as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        except Exception as exc:
            raise _pipeline_error(exc, "client nudge") from exc
        return {"ok": True, "matter_id": made["matter_id"], "doc": made["doc"], "rule_id": made["rule_id"], "draft_id": made["draft_id"], "armed": bool(made.get("armed"))}

    @app.get(
        "/client-viewer/auto-send",
        dependencies=[Depends(require_token)],
        summary="The emails sent automatically (leaving soon, left, cancelled); empty until the send gate's producer exists",
    )
    def get_auto_send() -> dict[str, Any]:
        from vergil import auto_send_dismissals

        return {"items": auto_send_dismissals.filter_items(auto_send_dismissals.load_items())}

    @app.post(
        "/client-viewer/auto-send/dismiss",
        dependencies=[Depends(require_token)],
        summary="A person dismisses a cancelled Auto Send item: it leaves the Cancelled tab and the count; the draft is untouched",
        response_model=AutoSendDismissResponse,
    )
    def post_auto_send_dismiss(payload: AutoSendDismissRequest, request: Request) -> dict[str, Any]:
        from vergil import auto_send_dismissals

        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            item_id = auto_send_dismissals.clean_id(payload.id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        if auto_send_dismissals.state_of(item_id, auto_send_dismissals.load_items()) == auto_send_dismissals.LEAVING_SOON:
            raise HTTPException(status.HTTP_409_CONFLICT, "Only a cancelled item can be dismissed")
        try:
            return auto_send_dismissals.dismiss(item_id, signin_names.display_name(remote_user) or remote_user)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    @app.get(
        "/client-viewer/case-board",
        dependencies=[Depends(require_token)],
        summary="The Case flow board: each open matter in the column of the step it is waiting at (read only, from stored state)",
    )
    def get_case_board(request: Request) -> dict[str, Any]:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            result = case_board.board()
        except Exception as exc:
            log.error("case board read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Case flow board unavailable") from exc
        shown = [{"matter_id": i["matter_id"], "client_name": i["client_name"]} for i in result["items"]]
        if shown:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            exposure = enforce_client_exposure_budget(budget_identity(remote_user), shown, source="case_board")
            if exposure.get("block"):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    _client_exposure_limit_detail(exposure.get("categories"), verb="window"),
                )
        result["items"] = _same_name_labelled(result["items"])
        return result

    @app.post(
        "/client-viewer/case-board/remove",
        dependencies=[Depends(require_token)],
        summary="Take one matter off the Case flow board for everyone (deletes nothing; it returns when a person runs or marks a step)",
    )
    def remove_from_case_board(payload: CaseBoardRemoveRequest) -> dict[str, Any]:
        try:
            return case_board.remove(payload.matter_id, payload.by)
        except Exception as exc:
            raise _pipeline_error(exc, "board remove") from exc

    @app.post(
        "/client-viewer/clients/remove",
        dependencies=[Depends(require_token)],
        summary="Remove a client: hidden everywhere, folder moved to 000 Removed, unsent envelopes voided, unsent drafts to Deleted Items (nothing deleted)",
    )
    def remove_client(payload: ClientRemoveRequest) -> dict[str, Any]:
        from onboarding import client_removal

        try:
            out = client_removal.remove(payload.matter_id, typed_name=payload.typed_name, reason=payload.reason, by=payload.by)
        except client_removal.RemovalError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("client remove failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The client could not be removed ({type(exc).__name__}).") from exc
        client_rows.clear()
        same_name.clear()
        return out

    @app.post(
        "/client-viewer/clients/undo-remove",
        dependencies=[Depends(require_token)],
        summary="Undo a removal within 30 days: the client shows again and the folder moves back",
    )
    def undo_remove_client(payload: ClientUndoRemoveRequest) -> dict[str, Any]:
        from onboarding import client_removal

        try:
            out = client_removal.undo(payload.matter_id, by=payload.by)
        except client_removal.RemovalError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("client undo-remove failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The removal could not be undone ({type(exc).__name__}).") from exc
        client_rows.clear()
        same_name.clear()
        return out

    def _mail_review_call(fn, *args, **kwargs):
        from vergil import mail_review

        try:
            return fn(*args, **kwargs)
        except mail_review.MailReviewClosed as exc:
            raise HTTPException(status.HTTP_423_LOCKED, str(exc)) from exc
        except mail_review.MailReviewError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "The mail review sheet is not on this server.") from exc
        except Exception as exc:
            log.error("mail review failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Improve mail classifier is unavailable ({type(exc).__name__}).") from exc

    @app.get(
        "/client-viewer/mail-review",
        dependencies=[Depends(require_token)],
        summary="Improve mail classifier: the labelling sheet's list, summary and expiry (no email content)",
    )
    def mail_review_overview() -> dict[str, Any]:
        from vergil import mail_review

        return _mail_review_call(mail_review.overview)

    @app.get(
        "/client-viewer/mail-review/item",
        dependencies=[Depends(require_token)],
        summary="Improve mail classifier: one email as plain text, and its current answer",
    )
    def mail_review_item(n: int = Query(..., ge=1, le=100000)) -> dict[str, Any]:
        from vergil import mail_review

        return _mail_review_call(mail_review.item, n)

    @app.post(
        "/client-viewer/mail-review/answer",
        dependencies=[Depends(require_token)],
        summary="Improve mail classifier: append one answer to labels.jsonl (refused once the sheet has expired)",
    )
    def mail_review_answer(payload: MailReviewAnswerRequest, request: Request) -> dict[str, Any]:
        from vergil import mail_review

        by = (request.headers.get("Remote-User") or "").strip()
        saved = _mail_review_call(mail_review.save, payload.n, payload.model_dump(), by=by)
        return {"saved": True, "n": saved["n"], "route": saved["route"]}

    @app.get(
        "/client-viewer/mail-review/decide",
        dependencies=[Depends(require_token)],
        summary="Improve mail classifier, Review: how many blocked emails wait, the oldest age, and one email",
    )
    def mail_review_decide(offset: int = Query(0, ge=0, le=100000)) -> dict[str, Any]:
        from vergil import mail_review

        return _mail_review_call(mail_review.decide, offset)

    @app.post(
        "/client-viewer/mail-review/decide",
        dependencies=[Depends(require_token)],
        summary="Improve mail classifier, Review: record the person's route (gold label plus a human_resolved event; moves nothing)",
    )
    def mail_review_decide_save(payload: MailReviewDecideRequest, request: Request) -> dict[str, Any]:
        from vergil import mail_review

        by = (request.headers.get("Remote-User") or "").strip()
        return _mail_review_call(mail_review.decide_save, payload.job_id, payload.model_dump(), by=by)

    @app.get(
        "/client-viewer/mail-review/control",
        dependencies=[Depends(require_token)],
        summary="Improve mail classifier, Control: today's small batch with the classifier's answer; one item. pool=control (confident) or pool=review (unsure) narrows it; none is the whole batch",
    )
    def mail_review_control(
        request: Request,
        n: int | None = Query(None, ge=1, le=1000),
        pool: str | None = Query(None, pattern="^(control|review)$"),
    ) -> dict[str, Any]:
        from vergil import mail_review
        from vergil.user_state import budget_identity

        who = budget_identity((request.headers.get("Remote-User") or "").strip())
        return _mail_review_call(mail_review.control, n, claimant=who, pool=pool)

    @app.post(
        "/client-viewer/mail-review/control",
        dependencies=[Depends(require_token)],
        summary="Improve mail classifier, Control: Agree, Disagree plus the right route, or no clean answer (one gold-label line)",
    )
    def mail_review_control_save(payload: MailReviewControlRequest, request: Request) -> dict[str, Any]:
        from vergil import mail_review
        from vergil.user_state import budget_identity

        who = budget_identity((request.headers.get("Remote-User") or "").strip())
        return _mail_review_call(mail_review.control_save, payload.date, payload.job_id, payload.model_dump(), claimant=who)

    @app.post(
        "/client-viewer/mail-review/control/release",
        dependencies=[Depends(require_token)],
        summary="Improve mail classifier, Control: give back the email this person was holding (closed or not today)",
    )
    def mail_review_control_release(payload: MailReviewControlReleaseRequest, request: Request) -> dict[str, Any]:
        from vergil import mail_review
        from vergil.user_state import budget_identity

        who = budget_identity((request.headers.get("Remote-User") or "").strip())
        return _mail_review_call(mail_review.control_release, payload.job_id, who)

    @app.post(
        "/client-viewer/mail-review/extend",
        dependencies=[Depends(require_token)],
        summary="Improve mail classifier: extend the sheet's expiry by 7 or 30 days",
    )
    def mail_review_extend(payload: MailReviewExtendRequest) -> dict[str, Any]:
        from vergil import mail_review

        return _mail_review_call(mail_review.extend, payload.days, payload.by)

    @app.get(
        "/client-viewer/clients/merge-preview",
        dependencies=[Depends(require_token)],
        summary="What merging client A into B would move, what would stay, and any refusal. Read only",
    )
    def merge_preview(
        request: Request,
        from_matter_id: str = Query(..., min_length=1, max_length=20),
        into_matter_id: str = Query(..., min_length=1, max_length=20),
    ) -> dict[str, Any]:
        from onboarding import client_merge

        try:
            out = client_merge.public(client_merge.preview(from_matter_id, into_matter_id), values=True)
        except client_merge.MergeError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("merge preview failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The merge preview could not be made ({type(exc).__name__}).") from exc
        shown = [{"matter_id": c.get("matter_id"), "client_name": c.get("client_name", "")} for c in (out["from"], out["into"]) if c.get("client_name")]
        if shown:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            remote_user = (request.headers.get("Remote-User") or "").strip()
            exposure = enforce_client_exposure_budget(budget_identity(remote_user), shown, source="merge_preview")
            if exposure.get("block"):
                raise HTTPException(status.HTTP_403_FORBIDDEN, _client_exposure_limit_detail(exposure.get("categories"), verb="window"))
        return out

    @app.post(
        "/client-viewer/clients/merge",
        dependencies=[Depends(require_token)],
        summary="Merge duplicate client A into B: A's rows move to B, A becomes a hidden tombstone pointing to B (nothing deleted)",
    )
    def merge_clients(payload: ClientMergeRequest) -> dict[str, Any]:
        from onboarding import client_merge

        try:
            out = client_merge.merge(
                payload.from_matter_id, payload.into_matter_id,
                typed_from=payload.typed_from, typed_into=payload.typed_into, reason=payload.reason, by=payload.by, choices=payload.choices,
            )
        except client_merge.MergeError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("client merge failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The clients could not be merged ({type(exc).__name__}).") from exc
        client_rows.clear()
        same_name.clear()
        return out

    @app.post(
        "/client-viewer/clients/undo-merge",
        dependencies=[Depends(require_token)],
        summary="Undo a merge within 30 days: the moved rows go back and the merged-away client shows again",
    )
    def undo_merge_clients(payload: ClientUndoMergeRequest) -> dict[str, Any]:
        from onboarding import client_merge

        try:
            out = client_merge.undo(payload.matter_id, by=payload.by)
        except client_merge.MergeError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("client undo-merge failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The merge could not be undone ({type(exc).__name__}).") from exc
        client_rows.clear()
        same_name.clear()
        return out

    @app.get(
        "/client-viewer/hidden-matters",
        dependencies=[Depends(require_token)],
        summary="Which of the given matter ids are removed or merged away, so a browser's Recent list can forget them",
    )
    def hidden_matters(ids: str = "") -> dict[str, Any]:
        from onboarding import client_removal

        asked = [part.strip() for part in ids.split(",") if part.strip().isdigit()][:50]
        try:
            hidden = client_removal.hidden_ids()
        except Exception as exc:
            log.error("hidden matters read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Hidden matters unavailable") from exc
        return {"hidden": [mid for mid in asked if mid in hidden]}

    @app.get(
        "/client-viewer/removed-clients",
        dependencies=[Depends(require_token)],
        summary="Every removed, restored and purged client with its reason, for audit",
    )
    def removed_clients(request: Request) -> dict[str, Any]:
        from onboarding import client_removal

        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            rows = client_removal.listing()
        except Exception as exc:
            log.error("removed clients read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Removed clients unavailable") from exc
        shown = [{"matter_id": r["matter_id"], "client_name": r["client_name"]} for r in rows]
        if shown:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            exposure = enforce_client_exposure_budget(budget_identity(remote_user), shown, source="removed_clients")
            if exposure.get("block"):
                raise HTTPException(status.HTTP_403_FORBIDDEN, _client_exposure_limit_detail(exposure.get("categories"), verb="window"))
        return {"items": rows, "undo_days": client_removal.UNDO_DAYS}

    @app.get(
        "/client-viewer/client-duplicates",
        dependencies=[Depends(require_token)],
        summary="Open clients that look like one client filed twice (same name, one name inside the other, same email or phone); read only",
    )
    def client_duplicates(request: Request) -> dict[str, Any]:
        from agwu import duplicate_check

        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            found = duplicate_check.pairs()
        except Exception as exc:
            log.error("client duplicates read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Duplicate clients unavailable") from exc
        items = [
            {
                "reason": str(pair["reason"]),
                "a": {"matter_id": str(pair["a"].get("matter_id")), "client_name": str(pair["a"].get("name") or "")},
                "b": {"matter_id": str(pair["b"].get("matter_id")), "client_name": str(pair["b"].get("name") or "")},
            }
            for pair in found
        ]
        shown = [side for item in items for side in (item["a"], item["b"])]
        if shown:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            exposure = enforce_client_exposure_budget(budget_identity(remote_user), shown, source="client_duplicates")
            if exposure.get("block"):
                raise HTTPException(status.HTTP_403_FORBIDDEN, _client_exposure_limit_detail(exposure.get("categories"), verb="window"))
        return {"items": items}

    @app.post(
        "/client-viewer/new-client",
        dependencies=[Depends(require_token)],
        summary="Open a new client: live folder, a pending entry, and one unsent draft with the New Client Form + Letter of Authority (and any ticked form); the record is made when the signed New Client Form comes back",
    )
    def open_new_client(payload: NewClientRequest) -> dict[str, Any]:
        try:
            return _run_new_client(payload, preview=False)
        finally:
            same_name.clear()

    @app.post(
        "/client-viewer/new-client/preview",
        dependencies=[Depends(require_token)],
        summary="What the new client button would make (folder and book, record, envelopes, drafts), with nothing made",
    )
    def preview_new_client(payload: NewClientRequest) -> dict[str, Any]:
        return _run_new_client(payload, preview=True)

    @app.post(
        "/client-viewer/new-client/manual",
        dependencies=[Depends(require_token)],
        summary="Add a client by hand: folder and record made now, no forms pack, no draft; same duplicate and address checks",
    )
    def add_manual_client(payload: ManualClientRequest) -> dict[str, Any]:
        try:
            return _run_manual_client(payload, preview=False)
        finally:
            same_name.clear()

    @app.post(
        "/client-viewer/new-client/manual/preview",
        dependencies=[Depends(require_token)],
        summary="What adding a client by hand would make (folder and record), with nothing made",
    )
    def preview_manual_client(payload: ManualClientRequest) -> dict[str, Any]:
        return _run_manual_client(payload, preview=True)

    def _run_manual_client(payload: ManualClientRequest, *, preview: bool) -> dict[str, Any]:
        from onboarding import new_client_button

        def run() -> dict[str, Any]:
            return new_client_button.start_manual_client(
                first_name=payload.first_name,
                last_name=payload.last_name,
                category=payload.category,
                by=payload.by,
                email=payload.email,
                phone=payload.phone,
                middle_name=payload.middle_name,
                dob=payload.dob,
                nino=payload.nino,
                address_line1=payload.address_line1,
                address_line2=payload.address_line2,
                address_line3=payload.address_line3,
                address_line4=payload.address_line4,
                postcode=payload.postcode,
                matter_details=payload.matter_details,
                address_checked=payload.address_checked,
                preview=preview,
            )

        try:
            return _new_client_answer(run, preview=preview)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_502_BAD_GATEWAY and not preview:
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    "The client was not finished. The folder may already have been made: look for it, and check the "
                    "client is not on file, before pressing Create again.",
                ) from exc
            raise

    def _run_new_client(payload: NewClientRequest, *, preview: bool) -> dict[str, Any]:
        from onboarding import new_client_button

        return _new_client_answer(
            lambda: new_client_button.start_new_client(
                first_name=payload.first_name,
                last_name=payload.last_name,
                email=payload.email,
                category=payload.category,
                send_rif=payload.send_rif,
                send_laif=payload.send_laif,
                address_checked=payload.address_checked,
                preview=preview,
                by=payload.by,
                request_id=payload.request_id,
                phone=payload.phone,
            ),
            preview=preview,
        )

    def _new_client_answer(run: Any, *, preview: bool) -> dict[str, Any]:
        from onboarding import new_client_button
        from vergil import access_identity

        try:
            return run()
        except access_identity.AccessIdentityError as exc:
            log.warning("new client test mark refused: %s", exc)
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"A test client can only be made by a person signed in to the CRM. {exc} Nothing was made."
            ) from exc
        except new_client_button.NewClientError as exc:
            prefix = "[address-check] " if exc.needs_address_check else ""
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{prefix}{exc}") from exc
        except Exception as exc:
            log.error("new client %s failed: %s", "preview" if preview else "open", type(exc).__name__)
            if preview:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The preview could not be made ({type(exc).__name__}). Nothing was made.") from exc
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"The new client was not finished ({type(exc).__name__}). Press Create again to carry on: "
                "what is already made is used, and nothing is made twice.",
            ) from exc

    @app.post(
        "/client-viewer/new-client/pending/resume",
        dependencies=[Depends(require_token)],
        summary="Finish a new client whose press stopped part-way: the folder, envelopes and draft already made are used, nothing is made twice",
    )
    def pending_new_client_resume(payload: PendingNewClientResumeRequest) -> dict[str, Any]:
        from onboarding import new_client_button

        try:
            return _new_client_answer(lambda: new_client_button.resume_new_client(payload.pending_id, by=payload.by), preview=False)
        finally:
            same_name.clear()

    @app.get(
        "/client-viewer/new-client/categories",
        dependencies=[Depends(require_token)],
        summary="The matters a new client can be opened under",
    )
    def new_client_categories() -> dict[str, Any]:
        from onboarding import new_client_categories as nc

        return {"categories": [{"key": c.key, "label": c.label} for c in nc.CATEGORIES]}

    def _pending_listing_shown(request: Request, out: dict[str, Any]) -> dict[str, Any]:
        shown = [{"matter_id": f"pending:{i['pending_id']}", "client_name": i["full_name"]} for i in out["items"]]
        if shown:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            remote_user = (request.headers.get("Remote-User") or "").strip()
            exposure = enforce_client_exposure_budget(budget_identity(remote_user), shown, source="pending_new_clients")
            if exposure.get("block"):
                raise HTTPException(status.HTTP_403_FORBIDDEN, _client_exposure_limit_detail(exposure.get("categories"), verb="window"))
        request.state.result_count = len(shown)
        return out

    @app.get(
        "/client-viewer/new-client/pending",
        dependencies=[Depends(require_token)],
        summary="New clients waiting for their signed New Client Form: whether the email has gone, which forms are back",
    )
    def pending_new_clients_list(request: Request) -> dict[str, Any]:
        from onboarding import pending_new_clients as pending

        try:
            out = pending.listing()
        except Exception as exc:
            log.error("pending new clients read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Pending new clients unavailable") from exc
        return _pending_listing_shown(request, out)

    @app.post(
        "/client-viewer/new-client/pending/cancel",
        dependencies=[Depends(require_token)],
        summary="Drop a new client still waiting for their forms; the folder, envelopes and draft are left as they are",
    )
    def pending_new_client_cancel(payload: PendingNewClientCancelRequest, request: Request) -> dict[str, Any]:
        from onboarding import pending_new_clients as pending

        try:
            pending.cancel(payload.pending_id, payload.by)
            out = pending.listing()
        except pending.PendingNewClientError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("pending new client cancel failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Pending new clients unavailable") from exc
        return _pending_listing_shown(request, out)

    @app.post(
        "/client-viewer/pipeline/run",
        response_model=PipelineRunResponse,
        dependencies=[Depends(require_token)],
        summary="Run one pipeline step for one matter, on a person's button press",
    )
    def run_pipeline_step(payload: PipelineRunRequest) -> PipelineRunResponse:
        try:
            intake_pipeline.person_pressed(payload.matter_id, payload.by, payload.step)
            return PipelineRunResponse(
                **intake_pipeline.run_step(payload.matter_id, payload.step, payload.by, variant=payload.variant or "")
            )
        except Exception as exc:
            raise _pipeline_error(exc, "run") from exc

    @app.post(
        "/client-viewer/pipeline/mark-done",
        response_model=PipelineResponse,
        dependencies=[Depends(require_token)],
        summary="Record one step as done outside Case flow, by a named person (refused while the client is locked)",
    )
    def mark_pipeline_step_done(payload: PipelineMarkDoneRequest) -> PipelineResponse:
        try:
            intake_pipeline.person_pressed(payload.matter_id, payload.by)
            return PipelineResponse(
                **intake_pipeline.mark_done(payload.matter_id, payload.step, payload.by, payload.note or "")
            )
        except Exception as exc:
            raise _pipeline_error(exc, "mark done") from exc

    @app.post(
        "/client-viewer/pipeline/confirm-court",
        response_model=PipelineResponse,
        dependencies=[Depends(require_token)],
        summary=f"{intake_pipeline.step_ref('court_email').capitalize()}: record the court a person confirmed for the court email (nothing is drafted here)",
    )
    def confirm_pipeline_court(payload: PipelineConfirmCourtRequest) -> PipelineResponse:
        try:
            intake_pipeline.person_pressed(payload.matter_id, payload.by)
            return PipelineResponse(
                **intake_pipeline.confirm_court(payload.matter_id, payload.by, payload.court, payload.email)
            )
        except Exception as exc:
            raise _pipeline_error(exc, "confirm court") from exc

    @app.post(
        "/client-viewer/pipeline/service-recipient",
        response_model=PipelineResponse,
        dependencies=[Depends(require_token)],
        summary=f"{intake_pipeline.step_ref('serve_other').capitalize()}: add a law firm, hospital or school to serve ({intake_pipeline.step_ref('serve_other')} then drafts their email)",
    )
    def add_pipeline_service_recipient(payload: PipelineServiceRecipientRequest) -> PipelineResponse:
        try:
            intake_pipeline.person_pressed(payload.matter_id, payload.by)
            return PipelineResponse(
                **intake_pipeline.add_service_recipient(payload.matter_id, payload.by, payload.kind, payload.name, payload.email)
            )
        except Exception as exc:
            raise _pipeline_error(exc, "service recipient") from exc

    @app.post(
        "/client-viewer/pipeline/amend/prepare",
        response_model=PipelineResponse,
        dependencies=[Depends(require_token)],
        summary=f"{intake_pipeline.step_ref('amend').capitalize()}: prepare an amendment round from the client's email, for the owner to review (nothing saved or sent)",
    )
    def prepare_pipeline_amend(payload: PipelineAmendPrepareRequest) -> PipelineResponse:
        from onboarding.pipeline import step_amend

        try:
            intake_pipeline.person_pressed(payload.matter_id, payload.by)
            return PipelineResponse(**step_amend.prepare(payload.matter_id, payload.by, payload.email_text))
        except Exception as exc:
            raise _pipeline_error(exc, "amend prepare") from exc

    @app.post(
        "/client-viewer/pipeline/amend/approve",
        response_model=PipelineRunResponse,
        dependencies=[Depends(require_token)],
        summary=f"{intake_pipeline.step_ref('amend').capitalize()}: the owner approves a round: the amended statement is saved and the email drafted (never sent)",
    )
    def approve_pipeline_amend(payload: PipelineAmendApproveRequest) -> PipelineRunResponse:
        from onboarding.pipeline import step_amend

        try:
            intake_pipeline.person_pressed(payload.matter_id, payload.by)
            return PipelineRunResponse(
                **step_amend.approve(payload.matter_id, payload.by, payload.round, answers=payload.answers, keep_original=payload.keep_original, client_questions=payload.client_questions, edits=payload.edits)
            )
        except Exception as exc:
            raise _pipeline_error(exc, "amend approve") from exc

    @app.post(
        "/client-viewer/pipeline/amend/discard",
        response_model=PipelineResponse,
        dependencies=[Depends(require_token)],
        summary=f"{intake_pipeline.step_ref('amend').capitalize()}: discard a prepared round (it does not count; nothing was saved or sent)",
    )
    def discard_pipeline_amend(payload: PipelineAmendDiscardRequest) -> PipelineResponse:
        from onboarding.pipeline import step_amend

        try:
            intake_pipeline.person_pressed(payload.matter_id, payload.by)
            return PipelineResponse(**step_amend.discard(payload.matter_id, payload.by, payload.round))
        except Exception as exc:
            raise _pipeline_error(exc, "amend discard") from exc

    @app.post(
        "/client-viewer/pipeline/personal-service",
        response_model=PipelineResponse,
        dependencies=[Depends(require_token)],
        summary=f"{intake_pipeline.step_ref('serve').capitalize()}: mark that the respondent is to be served personally (the step then reads as any other)",
    )
    def require_pipeline_personal_service(payload: PipelineResetRequest) -> PipelineResponse:
        try:
            intake_pipeline.person_pressed(payload.matter_id, payload.by)
            return PipelineResponse(**intake_pipeline.require_personal_service(payload.matter_id, payload.by))
        except Exception as exc:
            raise _pipeline_error(exc, "personal service") from exc

    @app.post(
        "/client-viewer/pipeline/mode",
        response_model=PipelineModeResponse,
        dependencies=[Depends(require_token)],
        summary="Switch the pipeline between manual and auto",
    )
    def set_pipeline_mode(payload: PipelineModeRequest) -> PipelineModeResponse:
        try:
            mode = intake_pipeline.set_mode(payload.mode, payload.by)
            if mode == "auto" and payload.matter_id:
                intake_pipeline.start_auto_pass(payload.matter_id)
            return PipelineModeResponse(mode=mode)
        except Exception as exc:
            raise _pipeline_error(exc, "mode") from exc

    def _matter_mode(matter_id: str, own: dict[str, str]) -> PipelineMatterModeResponse:
        return PipelineMatterModeResponse(
            matter_id=matter_id,
            setting=own["setting"],
            by=own["by"],
            at=own["at"],
            mode=intake_pipeline.get_mode(),
            effective_mode=intake_pipeline.effective_mode(matter_id, own=own["setting"]),
        )

    @app.get(
        "/client-viewer/pipeline/matter-mode",
        response_model=PipelineMatterModeResponse,
        dependencies=[Depends(require_token)],
        summary="One matter's own Manual/Auto setting, the firm-wide mode, and the mode the matter is in",
    )
    def get_pipeline_matter_mode(matter_id: str = Query(..., min_length=1, max_length=20)) -> PipelineMatterModeResponse:
        try:
            if not matter_id.strip().isdigit():
                raise intake_pipeline.PipelineError("matter_id must be a matter number")
            return _matter_mode(matter_id.strip(), intake_pipeline.matter_setting(matter_id))
        except Exception as exc:
            raise _pipeline_error(exc, "matter mode read") from exc

    @app.post(
        "/client-viewer/pipeline/matter-mode",
        response_model=PipelineMatterModeResponse,
        dependencies=[Depends(require_token)],
        summary="Set one matter to follow the firm-wide mode, or to Auto or Manual by itself",
    )
    def set_pipeline_matter_mode(payload: PipelineMatterModeRequest) -> PipelineMatterModeResponse:
        try:
            own = intake_pipeline.set_matter_setting(payload.matter_id, payload.setting, payload.by)
            out = _matter_mode(payload.matter_id.strip(), own)
            if out.effective_mode == "auto":
                intake_pipeline.start_auto_pass(out.matter_id)
            return out
        except Exception as exc:
            raise _pipeline_error(exc, "matter mode") from exc

    @app.post(
        "/client-viewer/pipeline/reset",
        response_model=PipelineResponse,
        dependencies=[Depends(require_token)],
        summary="Forget earlier runs for one matter so the pipeline can be shown again from the start",
    )
    def reset_pipeline(payload: PipelineResetRequest) -> PipelineResponse:
        try:
            intake_pipeline.person_pressed(payload.matter_id, payload.by)
            intake_pipeline.reset(payload.matter_id, payload.by)
            return PipelineResponse(**intake_pipeline.pipeline(payload.matter_id))
        except Exception as exc:
            raise _pipeline_error(exc, "reset") from exc

    @app.post(
        "/client-viewer/pipeline/reset-step",
        response_model=PipelineResponse,
        dependencies=[Depends(require_token)],
        summary="Forget one step's mark for one matter (files, folders, drafts and envelopes are not touched)",
    )
    def reset_pipeline_step(payload: PipelineResetStepRequest) -> PipelineResponse:
        try:
            intake_pipeline.person_pressed(payload.matter_id, payload.by)
            return PipelineResponse(**intake_pipeline.reset_step(payload.matter_id, payload.step, payload.by))
        except Exception as exc:
            raise _pipeline_error(exc, "reset step") from exc

    @app.get(
        "/client-viewer/lexcel",
        response_model=LexcelResponse,
        dependencies=[Depends(require_token)],
        summary="Lexcel: which of the opening, mid-case and closing letters were made, from the activity log only",
    )
    def get_lexcel(matter_id: str = Query(..., min_length=1), advice: bool = Query(True)) -> LexcelResponse:
        from onboarding.pipeline import lexcel

        try:
            return LexcelResponse(**lexcel.state(matter_id, advice=advice))
        except Exception as exc:
            raise _pipeline_error(exc, "lexcel read") from exc

    @app.post(
        "/client-viewer/lexcel/make",
        response_model=LexcelMakeResponse,
        dependencies=[Depends(require_token)],
        summary="Lexcel: make one of the three letters on a person's request, through its own Case flow step (never sent)",
    )
    def make_lexcel_letter(payload: LexcelMakeRequest) -> LexcelMakeResponse:
        from onboarding.pipeline import lexcel

        try:
            return LexcelMakeResponse(**lexcel.make(payload.matter_id, payload.kind, payload.by, variant=payload.variant or ""))
        except Exception as exc:
            raise _pipeline_error(exc, "lexcel make") from exc

    @app.post(
        "/client-viewer/lexcel/auto",
        dependencies=[Depends(require_token)],
        summary="Lexcel: cancel, or switch back on, the opening letter Case flow would make by itself",
    )
    def lexcel_auto(payload: LexcelAutoRequest) -> dict[str, Any]:
        from onboarding.pipeline import forget_cached, step_ccl

        out = step_ccl.auto_cancel(payload.matter_id, payload.by, resume=payload.resume)
        forget_cached(payload.matter_id)
        return out

    @app.get(
        "/client-viewer/case-review",
        response_model=CaseReviewResponse,
        dependencies=[Depends(require_token)],
        summary="The Case review tab: one review of a matter (File Review Form and File Summary Sheet), prefilled only from what the system holds",
    )
    def get_case_review(matter_id: str = Query(..., min_length=1), review_date: str = Query("", max_length=10)) -> CaseReviewResponse:
        from onboarding.pipeline import case_review

        try:
            return CaseReviewResponse(**case_review.view(matter_id, review_date))
        except Exception as exc:
            raise _pipeline_error(exc, "audit read") from exc

    @app.post(
        "/client-viewer/case-review/save",
        response_model=CaseReviewResponse,
        dependencies=[Depends(require_token)],
        summary="The Case review tab: save one review under its review date, by a named person (no Case flow step is run or changed)",
    )
    def save_case_review(payload: CaseReviewSaveRequest) -> CaseReviewResponse:
        from onboarding.pipeline import case_review

        try:
            return CaseReviewResponse(**case_review.save(payload.matter_id, payload.review_date, payload.answers, payload.by))
        except Exception as exc:
            raise _pipeline_error(exc, "audit save") from exc

    def _conflict_exposure(request: Request, result: dict) -> None:
        rows = [{"matter_id": m.get("other_matter_id"), "client_name": m.get("other_client")} for m in result.get("matches") or []]
        if not rows:
            return
        from vergil.user_state import budget_identity, enforce_client_exposure_budget

        _refuse_if_exposure_blocked(enforce_client_exposure_budget(
            budget_identity((request.headers.get("Remote-User") or "").strip()), rows, source="conflict_check"
        ))

    @app.get(
        "/client-viewer/court-route",
        response_model=CourtRouteResponse,
        dependencies=[Depends(require_token)],
        summary="The Client tab's call-first court notice: the court's number and rules, until a hearing date and case number are known",
    )
    def get_court_route(matter_id: str = Query(..., min_length=1)) -> CourtRouteResponse:
        from onboarding.pipeline import portal_courts

        try:
            return CourtRouteResponse(matter_id=matter_id, **portal_courts.court_route_view(matter_id))
        except Exception as exc:
            raise _pipeline_error(exc, "court route read") from exc

    @app.get(
        "/client-viewer/conflict-check",
        response_model=ConflictCheckResponse,
        dependencies=[Depends(require_token)],
        summary="The Case review tab's conflict of interest check: the newest run for a matter, and whether the matter has changed since",
    )
    def get_conflict_check(request: Request, matter_id: str = Query(..., min_length=1)) -> ConflictCheckResponse:
        from onboarding.pipeline import conflict_check

        try:
            result = conflict_check.latest(matter_id)
        except Exception as exc:
            raise _pipeline_error(exc, "conflict check read") from exc
        _conflict_exposure(request, result)
        return ConflictCheckResponse(**result)

    @app.post(
        "/client-viewer/conflict-check/run",
        response_model=ConflictCheckResponse,
        dependencies=[Depends(require_token)],
        summary="The Case review tab: run the conflict of interest check for a matter, by a named person (answers nothing on the forms)",
    )
    def run_conflict_check(request: Request, payload: ConflictCheckRunRequest) -> ConflictCheckResponse:
        from onboarding.pipeline import conflict_check

        try:
            result = conflict_check.run(payload.matter_id, payload.by)
        except Exception as exc:
            raise _pipeline_error(exc, "conflict check run") from exc
        _conflict_exposure(request, result)
        return ConflictCheckResponse(**result)

    @app.get(
        "/client-viewer/case-review/export.docx",
        dependencies=[Depends(require_token)],
        summary="The Case review tab: one form of one review as a Word download; writes nothing to OneDrive",
    )
    def export_case_review_docx(
        matter_id: str = Query(..., min_length=1), form: str = Query(..., min_length=1, max_length=10), review_date: str = Query("", max_length=10)
    ) -> Response:
        from onboarding.pipeline import case_review

        try:
            filename, content = case_review.export_docx(matter_id, form, review_date)
        except Exception as exc:
            raise _pipeline_error(exc, "audit export") from exc
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": content_disposition("attachment", filename)},
        )

    @app.get(
        "/client-viewer/robot-notices",
        response_model=RobotNoticesResponse,
        dependencies=[Depends(require_token)],
        summary="Things the automation needs a person for, newest first, with the open count",
    )
    def robot_notices_list() -> RobotNoticesResponse:
        try:
            items = robot_notices.list_open()
        except Exception as exc:
            log.error("robot notices list failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Robot notices unavailable") from exc
        return RobotNoticesResponse(count=len(items), items=[RobotNotice(**{k: v for k, v in item.items() if k != "dedupe_key"}) for item in items])


    def _notification_sources(attention: dict[str, Any] | None, replies: dict[str, Any] | None) -> dict[str, Any]:
        recent: list[dict[str, Any]] = []
        try:
            recent = _same_name_labelled(intake_tray.list_recent(days=notification_feed.AUTO_DISMISS_DAYS, limit=100)["items"])
        except Exception as exc:
            log.warning("notifications: recent intakes unreadable: %s", type(exc).__name__)
        have: set[str] = set()
        try:
            have = {m for m in (str(i["matter_id"]) for i in recent) if attention_store.existing_keys([f"new-client:{m}"])}
        except Exception as exc:
            log.warning("notifications: new client items unreadable: %s", type(exc).__name__)
        return {"attention": attention, "replies": replies, "recent_intakes": recent, "new_client_matters": have}

    @app.get(
        "/client-viewer/notifications",
        dependencies=[Depends(require_token)],
        summary="The Notification board: the bell's list plus the older, dismissed and hidden notifications for this person",
    )
    def get_notifications(request: Request, scope: str = Query(default="board", max_length=8)) -> dict[str, Any]:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            attention = matter_tasks.attention(limit=notification_feed.BOARD_LIMIT)
            replies = statement_replies.list_replies(limit=notification_feed.BOARD_LIMIT)
            for bucket in ("red", "yellow", "green", "scope_creep", "counsel_accepted", "counsel_rejected", "court_order", "court_rejected", "obligations"):
                if isinstance(attention.get(bucket), list):
                    attention[bucket] = _same_name_labelled(attention[bucket])
            replies["items"] = _same_name_labelled(replies["items"])
            result = notification_feed.view(
                remote_user, _notification_sources(attention, replies), scope="bell" if scope == "bell" else "board",
            )
        except Exception as exc:
            log.error("notifications read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Notifications unavailable") from exc
        from vergil.user_state import budget_identity, enforce_client_exposure_budget

        shown = [{"matter_id": n["matter_id"], "client_name": n["client"]} for key in ("bell", "board", "dismissed", "hidden") for n in result.get(key, []) if n["matter_id"]]
        if shown:
            _refuse_if_exposure_blocked(enforce_client_exposure_budget(budget_identity(remote_user), shown, source="notifications"))
        return result

    @app.post(
        "/client-viewer/notifications/state",
        dependencies=[Depends(require_token)],
        summary="Dismiss, hide or put back one notification for the signed-in person (a row is updated, never deleted)",
    )
    def set_notification_state(payload: NotificationStateRequest, request: Request) -> dict[str, Any]:
        remote_user = (request.headers.get("Remote-User") or "").strip() or payload.by
        try:
            return notification_feed.set_state(remote_user, payload.nid, payload.state, by=payload.by or remote_user)
        except notification_feed.NotificationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("notification state write failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Notifications unavailable") from exc

    @app.get(
        "/client-viewer/notifications/robot",
        dependencies=[Depends(require_token)],
        summary="The Notification board's Robot face: open and closed robot notices, and the ops supervisor's alerts (administrators only)",
    )
    def get_robot_board(request: Request) -> dict[str, Any]:
        from vergil import ops_health, runtime_control

        remote_user = (request.headers.get("Remote-User") or "").strip()
        is_admin = bool(verified_admin_email(request))
        is_dev = is_admin or bool(dev_identity(request))
        if not is_admin and runtime_control.is_env_admin(remote_user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
        try:
            open_rows = [{k: v for k, v in r.items() if k != "dedupe_key"} for r in robot_notices.list_open(limit=200)]
            closed = [{k: v for k, v in r.items() if k != "dedupe_key"} for r in robot_notices.list_resolved(limit=100)]
        except Exception as exc:
            log.error("robot board read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Robot notices unavailable") from exc
        out = notification_feed.robot_view(notices=open_rows, resolved=closed, ops=ops_health.load() if is_dev else None)
        out["ops"]["admin"] = is_dev
        return out

    @app.get(
        "/client-viewer/role",
        dependencies=[Depends(require_token)],
        summary="The caller's CRM role: dev, admin or worker, from a verified Access assertion only",
    )
    def get_caller_role(request: Request) -> dict[str, str]:
        return {"role": caller_role(request)}

    @app.get(
        "/client-viewer/ops-health",
        response_model=OpsHealthResponse,
        dependencies=[Depends(require_token)],
        summary="The ops supervisor's last snapshot: every alert, administrators only",
    )
    def ops_health_view(request: Request) -> OpsHealthResponse:
        from vergil import ops_health

        is_dev = bool(dev_identity(request))
        if not is_dev:
            require_verified_admin(request)
        view = ops_health.load()
        alerts = view["alerts"]
        return OpsHealthResponse(
            **{k: v for k, v in view.items() if k != "alerts"},
            alerts=[OpsHealthAlert(**a) for a in alerts],
        )

    @app.get(
        "/client-viewer/system-status",
        response_model=SystemStatusResponse,
        dependencies=[Depends(require_token)],
        summary="Boxes and outside-service status for the CRM's System health page (developers only)",
    )
    def system_status_view(_dev: str = Depends(require_verified_dev)) -> SystemStatusResponse:
        from vergil import system_status

        return SystemStatusResponse(
            boxes=[SystemBox(**b) for b in system_status.load_boxes()],
            providers=SystemProviders(**system_status.load_providers()),
            spend=SystemSpend(**system_status.spend_view()),
            workers=SystemWorkers(**system_status.workers_view()),
            backups=SystemRows(**system_status.backups_view()),
            expiries=SystemRows(**system_status.expiries_view()),
            functions=[SystemFunction(**f) for f in system_status.functions_view()],
            services=SystemServices(**system_status.services_view()),
        )

    @app.get(
        "/client-viewer/storage-status",
        response_model=StorageStatusResponse,
        dependencies=[Depends(require_token)],
        summary="Where the firm's storage goes, for the CRM Storage tab (developers only)",
    )
    def storage_status_view(_dev: str = Depends(require_verified_dev)) -> StorageStatusResponse:
        from vergil import storage_status_view as view

        return StorageStatusResponse(**view.storage_view())

    @app.get(
        "/monitor/boxes",
        response_model=list[SystemBox],
        dependencies=[Depends(require_token)],
        summary="Last-reported stats for the dev and production boxes (read-only)",
    )
    def monitor_boxes() -> list[SystemBox]:
        from vergil import system_status

        return [SystemBox(**b) for b in system_status.load_boxes()]

    @app.get(
        "/monitor/providers",
        response_model=SystemProviders,
        dependencies=[Depends(require_token)],
        summary="Outside-service state from each provider's own status page (read-only)",
    )
    def monitor_providers() -> SystemProviders:
        from vergil import system_status

        return SystemProviders(**system_status.load_providers())

    @app.post(
        "/monitor/box-stats",
        dependencies=[Depends(require_box_push_token)],
        summary="The dev box pushes its stats snapshot here",
    )
    def monitor_box_stats_push(body: BoxStatsPush) -> dict:
        from monitoring.box_stats import snapshot_path

        from atomic_json import atomic_write_json
        from vergil import system_status

        cleaned = system_status.clean_box(body.model_dump())
        if cleaned is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unreadable box stats")
        atomic_write_json(snapshot_path(body.box, system_status.telemetry_root()), {"box": body.box, **cleaned})
        return {"stored": True}

    @app.post(
        "/monitor/box-extras",
        dependencies=[Depends(require_box_push_token)],
        summary="The dev box pushes its user timers and Healthchecks list here",
    )
    def monitor_box_extras_push(body: BoxExtrasPush) -> dict:
        from atomic_json import atomic_write_json
        from vergil import system_status

        hc = body.healthchecks if isinstance(body.healthchecks, dict) else {}
        atomic_write_json(
            system_status.telemetry_root() / "dev-extras.json",
            {
                "box": "dev",
                "generated_at": body.generated_at,
                "schedules": [system_status._clean_row(r) for r in body.schedules],
                "healthchecks": {
                    "available": bool(hc.get("available")),
                    "note": str(hc.get("note") or "")[:120],
                    "checks": [c for c in (hc.get("checks") or [])[:400] if isinstance(c, dict)],
                },
            },
        )
        return {"stored": True}

    @app.get(
        "/client-viewer/audit-trail",
        dependencies=[Depends(require_token)],
        summary="What changed and who did it, for the CRM's audit page (any signed-in user)",
    )
    def audit_trail_view(
        kind: str = Query("all", pattern="^(all|person|agent|automation)$"),
        days: int = Query(7, ge=1, le=90),
        q: str = Query("", max_length=120),
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0, le=100000),
        _admin: str = Depends(require_verified_user),
    ) -> dict:
        import ops_db

        from vergil import audit_trail

        try:
            with ops_db.connect() as conn:
                return audit_trail.trail(conn, kind=kind, days=days, q=q, limit=limit, offset=offset, request_log=_request_log_path())
        except Exception as exc:
            log.error("audit trail read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Audit trail unavailable") from exc

    @app.get(
        "/client-viewer/audit-folders",
        dependencies=[Depends(require_token)],
        summary="The audit page's folder view: one client folder as a tree, with who made and who placed each file (any signed-in user)",
    )
    def audit_folders_view(
        folder: str = Query("", max_length=200),
        days: int = Query(90, ge=1, le=90),
        _admin: str = Depends(require_verified_user),
    ) -> dict:
        import ops_db

        from vergil import audit_folder_view

        try:
            with ops_db.connect() as conn:
                return audit_folder_view.folder_view(conn, folder=folder, days=days, request_log=_request_log_path())
        except Exception as exc:
            log.error("audit folder view read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Audit folder view unavailable") from exc

    @app.post(
        "/client-viewer/audit-folders/flag",
        dependencies=[Depends(require_token)],
        summary="Flag a file or folder in the audit page's folder view as wrong, or clear the flag (any signed-in user)",
    )
    def audit_folders_flag(payload: AuditFolderFlagRequest, admin: str = Depends(require_verified_user)) -> dict:
        import ops_db

        from vergil import audit_folder_view

        try:
            with ops_db.connect() as conn:
                return audit_folder_view.set_flag(conn, client=payload.client, path=payload.path, item_type=payload.type, flagged=payload.flagged, by=admin, kind="person", note=payload.note)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("audit folder flag failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Audit folder flags unavailable") from exc

    @app.get(
        "/client-viewer/audit-folders/link",
        dependencies=[Depends(require_token)],
        summary="The SharePoint link to one file or folder of the audit page's folder view (any signed-in user)",
    )
    def audit_folders_link(
        client: str = Query(..., min_length=1, max_length=200),
        path: str = Query(..., min_length=1, max_length=500),
        _user: str = Depends(require_verified_user),
    ) -> dict:
        import ops_db

        from vergil import audit_folder_view

        try:
            with ops_db.connect() as conn:
                return {"url": audit_folder_view.share_link(conn, client, path)}
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not in the file index") from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("audit folder link failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "SharePoint link unavailable") from exc

    @app.get(
        "/client-viewer/form-drafts/backup",
        response_model=FormDraftBackupResponse,
        dependencies=[Depends(require_token)],
        summary="The server copy of one client's unsaved Client-tab or hearing edit draft",
    )
    def get_form_draft_backup(matter_id: str = Query(..., min_length=1), form_id: str = Query(..., min_length=1)) -> FormDraftBackupResponse:
        try:
            saved = form_draft_backup.get(matter_id, form_id)
        except Exception as exc:
            log.error("form draft backup read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Form draft backup unavailable") from exc
        return FormDraftBackupResponse(saved_at=(saved or {}).get("savedAt"), data=(saved or {}).get("data"))

    @app.post(
        "/client-viewer/form-drafts/backup",
        response_model=FormDraftBackupResponse,
        dependencies=[Depends(require_token)],
        summary="Save (or, with null data, remove) the server copy of one unsaved form draft",
    )
    def put_form_draft_backup(payload: FormDraftBackupRequest) -> FormDraftBackupResponse:
        if payload.data is not None:
            _require_known_matter(payload.matter_id)
        try:
            form_draft_backup.put(payload.matter_id, payload.form_id, payload.saved_at, payload.data)
        except form_draft_backup.DraftError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("form draft backup write failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Form draft backup unavailable") from exc
        return FormDraftBackupResponse(saved_at=payload.saved_at if payload.data is not None else None, data=payload.data)

    @app.get(
        "/client-viewer/attendance-notes/backup",
        response_model=AnBackupResponse,
        dependencies=[Depends(require_token)],
        summary="The server copy of one client's attendance-note typing box and drafts",
    )
    def get_an_backup(matter_id: str = Query(..., min_length=1)) -> AnBackupResponse:
        try:
            saved = an_backup.get(matter_id)
        except Exception as exc:
            log.error("attendance note backup read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Attendance note backup unavailable") from exc
        return AnBackupResponse(**(saved or {}))

    @app.post(
        "/client-viewer/attendance-notes/backup",
        response_model=AnBackupResponse,
        dependencies=[Depends(require_token)],
        summary="Save (or, when empty, remove) the server copy of one client's attendance-note typing box and drafts",
    )
    def put_an_backup(payload: AnBackupRequest) -> AnBackupResponse:
        if payload.working is not None or payload.drafts:
            _require_known_matter(payload.matter_id)
        try:
            an_backup.put(payload.matter_id, payload.working, payload.drafts)
            saved = an_backup.get(payload.matter_id)
        except an_backup.BackupError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("attendance note backup write failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Attendance note backup unavailable") from exc
        return AnBackupResponse(**(saved or {}))

    @app.post(
        "/client-viewer/robot-notices/dismiss",
        response_model=RobotNoticesResponse,
        dependencies=[Depends(require_token)],
        summary="A person has seen a notice; it leaves the list",
    )
    def robot_notice_dismiss(payload: DismissRobotNoticeRequest) -> RobotNoticesResponse:
        try:
            robot_notices.dismiss(payload.notice_id, payload.by)
            auto_flags.on_notice_dismissed(payload.notice_id)
            items = robot_notices.list_open()
        except Exception as exc:
            log.error("robot notice dismiss failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Robot notices unavailable") from exc
        return RobotNoticesResponse(count=len(items), items=[RobotNotice(**{k: v for k, v in item.items() if k != "dedupe_key"}) for item in items])

    @app.post(
        "/client-viewer/attendance-notes/delete-billing",
        response_model=AttendanceNoteStatus,
        dependencies=[Depends(require_token)],
        summary="Take a filed attendance note's charge off the bill; the document is never touched",
    )
    def attendance_note_delete_billing(payload: DeleteAttendanceNoteBillingRequest, request: Request) -> AttendanceNoteStatus:
        by = (request.headers.get("Remote-User") or "").strip() or "client-viewer"
        try:
            attendance_note_drafts.delete_billing(payload.draft_id, by=by)
            view = attendance_note_drafts.status_of(payload.draft_id)
        except attendance_note_drafts.AttendanceNoteDraftError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("attendance note billing removal failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Billing removal unavailable") from exc
        if view is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such attendance note")
        return AttendanceNoteStatus(**view)

    @app.post(
        "/client-viewer/billing/restore-item",
        response_model=RestoreBillingItemResponse,
        dependencies=[Depends(require_token)],
        summary="Undo a 'Remove from bill': the item goes back on the bill, with who and when recorded",
    )
    def billing_restore_item(payload: RestoreBillingItemRequest, request: Request) -> RestoreBillingItemResponse:
        by = (request.headers.get("Remote-User") or "").strip() or "client-viewer"
        try:
            item = attendance_note_drafts.restore_billing_item(payload.item_id, by=by)
        except attendance_note_drafts.AttendanceNoteDraftError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("billing restore failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Billing restore unavailable") from exc
        return RestoreBillingItemResponse(
            item_id=item["item_id"],
            on_bill=not item.get("removed_utc"),
            restored_utc=item.get("restored_utc") or "",
            restored_by=item.get("restored_by") or "",
        )

    @app.get(
        "/client-viewer/frequent-callers",
        response_model=FrequentCallersResponse,
        dependencies=[Depends(require_token)],
        summary="Matters with a recent attendance note, plus every persistent-caller pin -- AppDrawer's standalone quick list",
    )
    def frequent_callers(request: Request, days: int = Query(default=7, ge=1, le=90)) -> FrequentCallersResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            import clientdb_sql

            recent = billing_items.list_frequent_callers(days=days)
            pinned_by_matter = client_edits.list_matters_with_flags(
                ["persistent_caller", "persistent_caller_respondent"]
            )
            an_counts = {str(row["matter_id"]): int(row.get("an_count") or 0) for row in recent}
            matter_ids = set(an_counts) | set(pinned_by_matter)
            rows = client_rows.rows_for(sorted(matter_ids))
        except Exception as exc:
            log.error("frequent callers lookup failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Frequent callers unavailable") from exc

        if rows:
            from vergil.user_state import (
                budget_identity,
                enforce_client_exposure_budget,
            )

            exposure = enforce_client_exposure_budget(
                budget_identity(remote_user), rows, source="frequent_callers"
            )
            if exposure.get("block"):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    _client_exposure_limit_detail(exposure.get("categories"), verb="window"),
                )

        results = _client_matches(rows)
        results.sort(key=lambda m: (str(m.matter_id) not in pinned_by_matter, -an_counts.get(str(m.matter_id), 0)))
        return FrequentCallersResponse(
            results=results, an_counts=an_counts, pinned_matters=sorted(pinned_by_matter)
        )

    @app.get(
        "/retrieve",
        response_model=RetrievalResponse,
        dependencies=[Depends(require_token)],
        summary="Search structured data and matter document content together",
    )
    def retrieve(
        request: Request,
        q: str = Query(min_length=2, description="A question, name, or phrase."),
    ) -> RetrievalResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            context = retrieval.retrieve(q)
        except Exception as exc:
            log.error("retrieval failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Retrieval backend unavailable"
            ) from exc

        if context.sql_hits:
            from vergil.user_state import (
                budget_identity,
                enforce_client_exposure_budget,
            )

            _refuse_if_exposure_blocked(enforce_client_exposure_budget(
                budget_identity(remote_user), context.sql_hits, source="retrieve"
            ), verb="search")

        return RetrievalResponse(
            query=q,
            matter_id=context.matter_id,
            sql_matches=[ClientMatch.from_row(row) for row in context.sql_hits],
            rag_hits=[RetrievalHit.from_hit(hit) for hit in context.prompt_rag_hits],
            graph_child_names=_graph_child_names(context.graph_listing),
            sources_checked=context.sources_checked,
            gaps=context.gaps,
            steps=[RetrievalStepModel(**vars(step)) for step in context.steps],
            resolved_via_rag=context.resolved_via_rag,
        )

    @app.get(
        "/matters/{matter_id}/work",
        response_model=MatterWorkResponse,
        dependencies=[Depends(require_token)],
        summary="What casework has already been done for a matter",
    )
    def matter_work(
        matter_id: str,
        include_superseded: bool = Query(default=False),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> MatterWorkResponse:
        try:
            entries = work_log.list_work(
                matter_id, include_superseded=include_superseded, limit=limit
            )
            summary = work_log.work_summary(matter_id)
        except Exception as exc:
            log.error("work log read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Work log unavailable") from exc
        return MatterWorkResponse(
            matter_id=matter_id,
            summary={key: WorkSummaryItem(**value) for key, value in summary.items()},
            entries=[WorkLogEntry.from_row(row) for row in entries],
        )

    @app.post(
        "/matters/{matter_id}/work",
        response_model=WorkLogEntry,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_token)],
        summary="Record a completed piece of casework",
    )
    def record_matter_work(
        matter_id: str,
        payload: RecordWorkRequest = Body(...),
    ) -> WorkLogEntry:
        try:
            row = work_log.record_work(
                matter_id=matter_id,
                work_type=payload.work_type,
                status=payload.status,
                performed_by=payload.performed_by,
                performed_on_host=payload.performed_on_host,
                reference=payload.reference,
                artefact_url=payload.artefact_url,
                notes=payload.notes,
                occurred_at=payload.occurred_at,
            )
        except work_log.WorkLogError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("work log write failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Work log unavailable") from exc
        return WorkLogEntry.from_row(row)

    @app.get(
        "/work/recent",
        response_model=list[WorkLogEntry],
        dependencies=[Depends(require_token)],
        summary="Work across all matters, most recent first (the billing-register read)",
    )
    def recent_work(
        request: Request,
        since: str = Query(default="", description="ISO-8601 lower bound on occurred_at."),
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> list[WorkLogEntry]:
        try:
            rows = work_log.recent_work(since=since, limit=limit)
        except Exception as exc:
            log.error("recent work read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Work log unavailable") from exc
        if rows:
            from vergil.user_state import (
                budget_identity,
                enforce_client_exposure_budget,
            )

            remote_user = (request.headers.get("Remote-User") or "").strip()
            _refuse_if_exposure_blocked(enforce_client_exposure_budget(
                budget_identity(remote_user), rows, source="work_recent"
            ))
        return [WorkLogEntry.from_row(row) for row in rows]

    @app.get(
        "/work/types",
        response_model=list[str],
        dependencies=[Depends(require_token)],
        summary="The accepted work_type vocabulary",
    )
    def work_types() -> list[str]:
        return list(work_log.WORK_TYPES)

    @app.get(
        "/monitor/summary",
        response_model=MonitorSummaryResponse,
        dependencies=[Depends(require_token)],
        summary="PII-safe ops-supervisor state: severity, alerts, quick metrics",
    )
    def monitor_summary() -> MonitorSummaryResponse:
        import monitoring.ops_supervisor as ops_supervisor_lib
        from vergil import briefing_render

        try:
            payload = ops_supervisor_lib.evaluate_supervisor(
                hours=briefing_render.OPS_SUPERVISOR_LOOKBACK_HOURS,
                startup_days=briefing_render.OPS_SUPERVISOR_STARTUP_DAYS,
            )
        except Exception as exc:
            log.error("ops supervisor read failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Ops supervisor unavailable"
            ) from exc

        rows = briefing_render.ops_supervisor_alert_rows(list(payload.get("alerts") or []))
        return MonitorSummaryResponse(
            generated_at=str(payload.get("generated_at") or ""),
            overall_severity=str(payload.get("overall_severity") or "unknown"),
            summary=str(payload.get("summary") or ""),
            alerts=[
                MonitorAlert(severity=row["Severity"], title=row["Issue"])
                for row in rows
            ],
            metrics=_supervisor_quick_metrics(payload),
        )

    @app.get(
        "/monitor/obligations",
        response_model=ObligationsResponse,
        dependencies=[Depends(require_token)],
        summary="The CaseForge Monitor aging board: every open obligation, most urgent first",
    )
    def monitor_obligations(request: Request) -> ObligationsResponse:
        from vergil import monitor_store

        obligations, error = monitor_store.load_monitor_obligations()
        if error:
            log.error("obligation aging read failed")
        if obligations:
            from vergil.user_state import (
                budget_identity,
                enforce_client_exposure_budget,
            )

            remote_user = (request.headers.get("Remote-User") or "").strip()
            _refuse_if_exposure_blocked(enforce_client_exposure_budget(
                budget_identity(remote_user), obligations, source="monitor_obligations"
            ))
        overdue = obligation_aging.overdue_obligations(obligations)
        return ObligationsResponse(
            count=len(obligations),
            overdue_count=len(overdue),
            error="obligations backend unavailable" if error else "",
            obligations=[ObligationItem.from_row(row) for row in obligations],
        )

    @app.get(
        "/matters/{matter_id}/document-checklist",
        response_model=DocumentChecklistResponse,
        dependencies=[Depends(require_token)],
        summary="Onboarding document checklist: LoA/witness statement drafted?",
    )
    def document_checklist(matter_id: str) -> DocumentChecklistResponse:
        import clientdb_sql
        from agents import onboarding_loa

        row = clientdb_sql.get_client_by_matter_id(matter_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Matter not found")
        client_name = str(row.get("name") or row.get("client_name") or "")
        try:
            files = onboarding_loa.matter_files(matter_id, client_name)
        except Exception as exc:
            log.error("document checklist file read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Document checklist unavailable") from exc

        loa_pair = onboarding_loa.find_loa_pair(files, client_name)
        ws_check = onboarding_loa.find_ws_pair(files, client_name)
        return DocumentChecklistResponse(
            matter_id=matter_id,
            loa_drafted=loa_pair is not None,
            witness_statement_drafted=ws_check.ok,
            witness_statement_issue=ws_check.issue,
        )

    @app.get(
        "/monitor/radar",
        response_model=RadarSummaryResponse,
        dependencies=[Depends(require_token)],
        summary="Tier-1 inbound radar: new referrer referrals worth a look",
    )
    def monitor_radar() -> RadarSummaryResponse:
        import datetime as dt
        import monitoring.inbound_radar as inbound_radar_lib
        from vergil import crn

        try:
            payload = inbound_radar_lib.radar_summary()
            now = dt.datetime.now(dt.timezone.utc)
            recent = inbound_radar_lib.recent_referrals(now, window_hours=payload["window_hours"])
            alert = inbound_radar_lib.classify(recent)["alert"]
            caseforge_references = crn.company_references_by_matter_id(
                [str(rec.get("matter_id") or "") for rec in alert]
            )
        except Exception as exc:
            log.error("inbound radar read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Inbound radar unavailable") from exc
        items = [
            RadarItem(
                ts=str(rec.get("ts") or ""),
                status=str(rec.get("status") or ""),
                status_label=inbound_radar_lib.status_label(rec.get("status")),
                name=str(rec.get("name") or ""),
                person_id=str(rec.get("person_id") or ""),
                matter_id=str(rec.get("matter_id") or ""),
                caseforge_reference=caseforge_references.get(str(rec.get("matter_id") or ""), ""),
                web_link=str(rec.get("web_url") or rec.get("webLink") or ""),
            )
            for rec in sorted(alert, key=lambda r: str(r.get("ts")), reverse=True)
        ]
        return RadarSummaryResponse(**payload, items=items)


    @app.post(
        GOOSE_ASK_PATH,
        dependencies=[Depends(require_token)],
        summary="Ask Vergil a question; SSE stream of the Goose-backed pipeline's events",
    )
    def goose_ask_endpoint(payload: GooseAskRequest, request: Request) -> StreamingResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        session_id = payload.session_id or None
        state = conversation_state_store.get_or_create(session_id)
        canceller = goose_ask.TurnCanceller()

        released = threading.Event()

        def _release_turn_slot() -> None:
            if not released.is_set():
                released.set()
                goose_ask.TURN_LIMITER.release(remote_user)

        turn_memory: dict = {"session_id": None, "client_hint": "", "parts": []}

        def _stream():
            try:
                yield from _stream_turn()
            finally:
                _release_turn_slot()
                conversation_log.append_turn(
                    turn_memory["session_id"],
                    payload.question,
                    "".join(turn_memory["parts"]),
                    client_hint=turn_memory["client_hint"],
                )

        def _stream_turn():
            try:
                result = goose_turn.handle_turn(
                    payload.question,
                    state=state,
                    session_id=session_id,
                    remote_user=remote_user or None,
                    matter_id=payload.matter_id or None,
                )
                conversation_state_store.save(result.session_id or session_id, state)

                if result.action == "goose":
                    canceller.bind(result.session_id)
                    yield _sse_event("session", {"session_id": result.session_id})
                    turn_sources = getattr(result, "sources", None)
                    if turn_sources:
                        yield _sse_event("sources", turn_sources)
                    stream = goose_ask.stream_vergil_answer_goose(result.session_id)
                    saw_text = False
                    saw_done = False
                    saw_error = False
                    last_tool = ""
                    last_call_signature = None
                    repeat_count = 0
                    result_seen_since_last_call = True
                    reply_text_parts: list[str] = []
                    turn_memory["session_id"] = result.session_id
                    turn_memory["client_hint"] = getattr(result, "client_hint", "") or ""
                    for event_name, data in stream:
                        if event_name == "delta":
                            turn_memory["parts"].append(str(data.get("text", "")))
                        if event_name == "delta" and str(data.get("text", "")).strip():
                            saw_text = True
                            reply_text_parts.append(str(data.get("text", "")))
                            repeat_count = 0
                        if event_name == "error":
                            saw_error = True
                            request.state.stream_error = True
                        if event_name in ("tool_result", "tool_error"):
                            result_seen_since_last_call = True
                        if event_name == "tool_call":
                            last_tool = str(data.get("tool") or "").split("__")[-1]
                            signature = (data.get("tool"), data.get("input_digest") or _stable_tool_input_repr(data.get("input")))
                            if signature == last_call_signature and not result_seen_since_last_call:
                                repeat_count += 1
                            else:
                                last_call_signature = signature
                                repeat_count = 1
                            result_seen_since_last_call = False
                        if event_name == "done":
                            saw_done = True
                            stalled_on_repeat = repeat_count >= _REPEAT_TOOL_CALL_STALL_THRESHOLD
                            if not saw_text or stalled_on_repeat:
                                yield _sse_event(
                                    "delta",
                                    {"text": _stall_fallback_text(last_tool, repeat_count if stalled_on_repeat else 0)},
                                )
                            _check_probing_contradiction(
                                "".join(reply_text_parts),
                                client_resolved=result.client_resolved,
                                remote_user=remote_user,
                            )
                        yield _sse_event(event_name, data)
                    if not saw_done and not saw_error:
                        stalled_on_repeat = repeat_count >= _REPEAT_TOOL_CALL_STALL_THRESHOLD
                        yield _sse_event(
                            "delta",
                            {"text": _stall_fallback_text(last_tool, repeat_count if stalled_on_repeat else 0)},
                        )
                        yield _sse_event("done", {})
                    return

                if result.action == "rejected":
                    yield _sse_event("error", {"message": result.text})
                    return

                yield _sse_event("delta", {"text": result.text})
                yield _sse_event("done", {})
            except Exception as exc:
                log.error("vergil/ask failed: %s", type(exc).__name__)
                request.state.stream_error = True
                yield _sse_event("error", {"message": "Vergil backend unavailable"})

        if not goose_ask.TURN_LIMITER.acquire(remote_user):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many chat turns in progress; try again shortly")
        return StreamingResponse(
            goose_ask.cancellable_stream(_stream(), request.receive, canceller),
            media_type="text/event-stream",
            background=BackgroundTask(_release_turn_slot),
        )

    @app.post(
        "/retrieval/feedback",
        response_model=RetrievalFeedbackResponse,
        dependencies=[Depends(require_token)],
        summary="Record thumbs up/down on a completed /retrieval/ask answer",
    )
    def retrieval_feedback(payload: RetrievalFeedbackRequest, request: Request) -> RetrievalFeedbackResponse:
        if not (payload.id or payload.ts_of_answer):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "id or ts_of_answer is required"
            )
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            from vergil.feedback import record_feedback

            record_feedback(
                verdict=payload.verdict,
                answer_id=payload.id,
                ts_of_answer=payload.ts_of_answer,
                comment=payload.comment,
                remote_user=remote_user,
                path=_intern_qa_feedback_path(),
            )
        except Exception as exc:
            log.error("intern/feedback write failed: %s", type(exc).__name__)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Feedback storage unavailable"
            ) from exc
        return RetrievalFeedbackResponse(ok=True)

    @app.get(
        "/retrieval/audit",
        response_model=InternAuditResponse,
        dependencies=[Depends(require_token)],
        summary="Recent /retrieval/ask Q&A audit records, newest first (authenticated, full PII)",
    )
    def intern_audit(
        limit: int = Query(default=INTERN_AUDIT_DEFAULT_LIMIT, ge=1, le=INTERN_AUDIT_MAX_LIMIT),
        since: str = Query(
            default="",
            description=(
                "ISO-8601 lower bound on `ts`, e.g. 2026-08-01T00:00:00Z -- the exact "
                "format the audit log itself writes. Compared as plain text, so a "
                "different (but still sortable) ISO representation still works; a "
                "non-ISO string simply never matches and returns no rows."
            ),
        ),
    ) -> InternAuditResponse:
        path = _intern_ask_audit_path()
        if not path.exists() or path.stat().st_size == 0:
            return InternAuditResponse(count=0, entries=[], note="no audit records yet")
        try:
            from graph_mail_safe_ops import _read_jsonl_tail

            rows = _read_jsonl_tail(path, limit=limit, since=since)
        except Exception as exc:
            log.error("intern/audit read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Audit log unavailable") from exc
        return InternAuditResponse(
            count=len(rows), entries=[InternAuditEntry.from_row(row) for row in rows], note=""
        )


    @app.get(
        "/client-viewer/scans",
        response_model=ScansResponse,
        dependencies=[Depends(require_token)],
        summary="The scans waiting in the Scanned Docs intake folder, newest scan date first (read only, listed when asked)",
    )
    def get_scans() -> ScansResponse:
        try:
            return ScansResponse(**scan_rows.list_scans())
        except scan_rows.ScansFolderUnreadable as exc:
            log.error("scans folder read failed: %s", exc)
            return ScansResponse(**scan_rows.unreadable(scan_rows.scanned_docs_path()))
        except Exception as exc:
            log.error("scans table failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Scans unavailable") from exc

    @app.get(
        "/client-viewer/scans/count",
        response_model=ScansCountResponse,
        dependencies=[Depends(require_token)],
        summary="How many files the Scanned Docs monitor last saw waiting (saved listing only, no folder read), for the Scans badge",
    )
    def get_scans_count() -> ScansCountResponse:
        from scanned_docs import scan_setting

        try:
            listing = scan_setting.cached_waiting()
        except Exception as exc:
            log.warning("scans count unavailable: %s", type(exc).__name__)
            return ScansCountResponse(known=False)
        return ScansCountResponse(known=True, count=len(listing["files"]), checked_utc=str(listing.get("checked_utc") or ""))


    def _folder_locks_payload() -> dict[str, Any]:
        import folder_locks

        import firm_profile

        books = list(firm_profile.load_profile().folder_books)
        return {"fixed": [], "locked": folder_locks.listing(), "books": books, "children": _book_children(books)}

    book_children_memo: dict[str, Any] = {}

    def _book_children(books: list[str]) -> dict[str, list[str]]:
        try:
            import graph_index

            stat = graph_index.INDEX_PATH.stat() if graph_index.INDEX_PATH.exists() else None
            key = (tuple(books), stat.st_mtime_ns if stat else 0, stat.st_size if stat else 0)
            if book_children_memo.get("key") == key:
                return book_children_memo["value"]
            out: dict[str, list[str]] = {b: [] for b in books}
            for item in graph_index._top_level_live_folders(graph_index._load_index().get("items", [])):
                book, name = graph_index._root_from_path(str(item["path"])), str(item.get("name") or "")
                if book in out and name:
                    out[book].append(name)
            value = {b: sorted(set(v), key=str.lower) for b, v in out.items()}
            book_children_memo.update(key=key, value=value)
            return value
        except Exception as exc:
            log.warning("folder index unreadable for the folder picker: %s", type(exc).__name__)
            return {}

    @app.get(
        "/client-viewer/folder-locks",
        dependencies=[Depends(require_token)],
        summary="The folders that are read-only to automation",
    )
    def get_folder_locks() -> dict[str, Any]:
        return _folder_locks_payload()

    @app.post(
        "/client-viewer/folder-locks",
        dependencies=[Depends(require_token)],
        summary="Make one folder read-only to automation, or lift it",
    )
    def set_folder_lock(payload: FolderLockRequest) -> dict[str, Any]:
        import folder_locks
        folder = payload.folder.strip()
        parts = [p.strip() for p in folder.replace("\\", "/").split("/") if p.strip()]
        if not parts or any(p.startswith(".") for p in parts):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "folder must be a book, or a folder inside one, with no dot segments")
        folder = "/".join(parts)
        try:
            if payload.locked:
                folder_locks.lock(folder, payload.by, "set on the assignment board")
            else:
                folder_locks.unlock(folder, payload.by)
        except folder_locks.FolderLockError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("folder lock change failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Folder locks unavailable") from exc
        return _folder_locks_payload()


    @app.get(
        "/client-viewer/statement-replies",
        response_model=StatementRepliesResponse,
        dependencies=[Depends(require_token)],
        summary="Clients who approved the witness statement, or want changes to it",
    )
    def get_statement_replies(request: Request, state: str = Query(default="")) -> StatementRepliesResponse:
        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            result = statement_replies.list_replies(state)
        except statement_replies.StatementReplyError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("statement replies read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Statement replies unavailable") from exc
        shown = [{"matter_id": i["matter_id"], "client_name": i["client_name"]} for i in result["items"]]
        if shown:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            _refuse_if_exposure_blocked(enforce_client_exposure_budget(budget_identity(remote_user), shown, source="statement_replies"))
        return StatementRepliesResponse(**result)

    @app.get(
        "/client-viewer/nearest",
        dependencies=[Depends(require_token)],
        summary="The nearest court and the 5 nearest chambers to the client's postcode (read only, cached; the postcode is never logged)",
    )
    def get_nearest(matter_id: str = Query(..., min_length=1, max_length=20)) -> dict[str, Any]:
        from vergil import nearest_help

        try:
            return nearest_help.for_matter(matter_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("nearest court/chambers failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Nearest court and chambers unavailable") from exc

    @app.get(
        "/client-viewer/matter-court",
        dependencies=[Depends(require_token)],
        summary="The matter's court (the first court emailed), read only",
    )
    def get_matter_court(matter_id: str = Query(..., min_length=1, max_length=20)) -> dict[str, Any]:
        from onboarding import matter_court

        try:
            return matter_court.court_summary(matter_id)
        except Exception as exc:
            log.error("matter court read failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Court unavailable") from exc

    @app.get(
        "/client-viewer/portal-courts",
        dependencies=[Depends(require_token)],
        summary="The portal-only courts' names, and the one this matter's court is (blank when it is none or not known), read only",
    )
    def get_portal_courts(matter_id: str = Query("", max_length=20)) -> dict[str, Any]:
        from onboarding.pipeline import portal_courts

        court = ""
        if matter_id.strip().isdigit():
            from onboarding import matter_court

            try:
                court = portal_courts.portal_court(str(matter_court.court_summary(matter_id.strip()).get("court") or ""))
            except Exception as exc:
                log.error("portal court read failed: %s", type(exc).__name__)
        return {"courts": [c["name"] for c in portal_courts.load()], "court": court}

    @app.get(
        "/client-viewer/whats-new",
        dependencies=[Depends(require_token)],
        summary="What's new in the CRM: the Shown-to-users notes of the deployed checkout's commits, newest first",
    )
    def get_whats_new() -> dict[str, Any]:
        from vergil import whats_new

        return whats_new.notes()

    @app.get(
        "/client-viewer/today",
        dependencies=[Depends(require_token)],
        summary="The Today board: drafts, Case flow steps waiting on a person (new clients included) and matters waiting on others, read only",
    )
    def get_today(request: Request) -> dict[str, Any]:
        from vergil import today_board

        remote_user = (request.headers.get("Remote-User") or "").strip()
        try:
            out = today_board.board()
        except Exception as exc:
            log.error("today board failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Today board unavailable") from exc
        shown = [
            {"matter_id": item.get("matter_id"), "client_name": item.get("client_name")}
            for section in out["sections"]
            for item in section["items"]
            if item.get("matter_id")
        ]
        if shown:
            from vergil.user_state import budget_identity, enforce_client_exposure_budget

            exposure = enforce_client_exposure_budget(budget_identity(remote_user), shown, source="today_board")
            if exposure.get("block"):
                raise HTTPException(status.HTTP_403_FORBIDDEN, _client_exposure_limit_detail(exposure.get("categories"), verb="window"))
        request.state.result_count = len(shown)
        for section in out["sections"]:
            section["items"] = _same_name_labelled(section["items"])
        return out


    def _pending_new_clients_summary() -> dict[str, int]:
        from onboarding import pending_new_clients as pending

        return pending.summary()

    @app.get(
        "/client-viewer/pulse",
        dependencies=[Depends(require_token)],
        summary="The bell, flag counts, robot notices, statement replies and pending new clients in one answer (what the header polls)",
    )
    def get_pulse(request: Request) -> dict[str, Any]:
        from concurrent.futures import ThreadPoolExecutor

        from fastapi.encoders import jsonable_encoder

        parts: dict[str, Any] = {
            "attention": lambda: get_attention(request),
            "flag_counts": lambda: flag_counts(request, "flagged,starred"),
            "robot_notices": lambda: robot_notices_list(),
            "statement_replies": lambda: get_statement_replies(request, ""),
            "pending_new_clients": lambda: _pending_new_clients_summary(),
        }

        def run(name: str) -> tuple[str, Any, bool]:
            try:
                return name, jsonable_encoder(parts[name]()), True
            except HTTPException as exc:
                log.warning("pulse part %s failed: %s", name, exc.status_code)
            except Exception as exc:
                log.warning("pulse part %s failed: %s", name, type(exc).__name__)
            return name, None, False

        with ThreadPoolExecutor(max_workers=len(parts)) as pool:
            futures = [pool.submit(contextvars.copy_context().run, run, name) for name in parts]
            results = [future.result() for future in futures]
        out: dict[str, Any] = {name: value for name, value, _ok in results}
        out["errors"] = [name for name, _value, ok in results if not ok]
        if out.get("attention") is not None:
            try:
                out["notifications"] = jsonable_encoder(
                    notification_feed.view(
                        (request.headers.get("Remote-User") or "").strip(),
                        _notification_sources(out.get("attention"), out.get("statement_replies")),
                        scope="bell",
                    )
                )
            except Exception as exc:
                log.warning("pulse part notifications failed: %s", type(exc).__name__)
                out["notifications"] = None
                out["errors"].append("notifications")
        return out

    @app.post(
        "/client-viewer/statement-replies",
        response_model=StatementReplyResponse,
        dependencies=[Depends(require_token)],
        summary="Record a client's reply to the witness statement (approved or amend), or clear it",
    )
    def set_statement_reply(payload: StatementReplyRequest) -> StatementReplyResponse:
        try:
            return StatementReplyResponse(**statement_replies.set_reply(payload.matter_id, payload.state, payload.note, payload.by))
        except statement_replies.StatementReplyError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("statement reply write failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Statement replies unavailable") from exc

    @app.post(
        "/client-viewer/statement-replies/hide",
        response_model=StatementReplyResponse,
        dependencies=[Depends(require_token)],
        summary="Hide a statement reply a person has dealt with: it leaves the smiley lists and stays on record",
    )
    def hide_statement_reply(payload: StatementReplyHideRequest) -> StatementReplyResponse:
        try:
            out = statement_replies.hide_reply(payload.matter_id, payload.by)
            return StatementReplyResponse(matter_id=out["matter_id"], state=out["state"])
        except statement_replies.StatementReplyError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        except Exception as exc:
            log.error("statement reply hide failed: %s", type(exc).__name__)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Statement replies unavailable") from exc

    return app


def run() -> int:
    import uvicorn

    missing = preflight()
    if missing and str(os.getenv("CASEFORGE_HUB_API_ALLOW_DEGRADED", "")).strip().lower() not in {"1", "true", "yes", "on"}:
        for name in missing:
            log.error("%s is not set -- %s", name, REQUIRED_ENV[name])
        log.error(
            "Refusing to start without the above. If this is deliberate, set "
            "CASEFORGE_HUB_API_ALLOW_DEGRADED=1. A service that refuses to start is a "
            "page; a service that starts and answers nothing is a week (gh#174)."
        )
        return 2
    for name, why in OPTIONAL_ENV.items():
        if not os.getenv(name, "").strip():
            log.warning("%s is not set -- %s", name, why)

    host = os.getenv("CASEFORGE_CHAT_API_HOST", "127.0.0.1")
    port = int(os.getenv("CASEFORGE_CHAT_API_PORT", str(DEFAULT_PORT)))
    if host not in {"127.0.0.1", "localhost", "::1"}:
        log.warning(
            "Binding %s rather than localhost. This service returns client PII -- "
            "make sure something in front of it is doing access control.", host
        )
    try:
        import monitoring.healthchecks_ping as healthchecks_ping

        healthchecks_ping.start_heartbeat("caseforge-hub-api")
    except Exception:
        pass
    uvicorn.run(create_app(), host=host, port=port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
