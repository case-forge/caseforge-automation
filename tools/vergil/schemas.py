from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SameNameLabel(BaseModel):

    same_name_index: int | None = None
    same_name_count: int | None = None
    same_name_birth_year: int | None = None
    same_name_ref: str | None = None


class ClientMatch(SameNameLabel):

    model_config = ConfigDict(extra="ignore")

    matter_id: str | int | None = None
    client_name: str | None = None
    matter_name: str | None = None
    client_role: str | None = None
    case_reference: str | None = None
    reference_summary: str | None = None
    email_primary: str | None = None
    phone_primary: str | None = None
    dob_iso: str | None = None
    sex: str | None = None
    sex_other: str | None = None
    address_summary: str | None = Field(
        default=None,
        description="Non-C8 matter-party address only; C8-withheld addresses never reach this field.",
    )
    party_summary: str | None = None
    matched_party_summary: str | None = None
    order_requested_text: str | None = None
    live_matter_folder: str | None = None
    legal_aid_tracker_status: str | None = None
    closed_at: str | None = None

    @field_validator("dob_iso", "closed_at", mode="before")
    @classmethod
    def _stringify_date(cls, value: Any) -> Any:
        if isinstance(value, dt.date):
            return value.isoformat()
        return value

    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Columns returned by the query but not declared above, kept rather than dropped.",
    )

    @classmethod
    def from_row(cls, row: dict) -> "ClientMatch":
        declared = set(cls.model_fields) - {"extra"}
        known = {key: value for key, value in row.items() if key in declared}
        rest = {key: value for key, value in row.items() if key not in declared}
        return cls(**known, extra=rest)


class ClientSearchResponse(BaseModel):

    query: str
    resolved_query: str = Field(
        description="What was actually searched for. Differs from `query` when a court "
                    "reference was normalised or a name resolved through an alias, and "
                    "carries the ' -> ' trail when it does."
    )
    source: str = Field(
        description="Which source answered: 'sql', 'resolver', 'cache' or 'none'."
    )
    count: int
    results: list[ClientMatch]


class HealthResponse(BaseModel):
    status: str
    sql_available: bool = Field(
        description="False while the client database is unavailable and no local fallback is configured. "
                    "The service still answers from the caches when this is False."
    )
    sql_cooldown_until: str = Field(default="", description="Empty when no cooldown is active.")


class RetrievalStepModel(BaseModel):

    source: str = Field(
        description="Stable key: 'sql', 'rag', 'sql_retry', 'graph' or 'mail'."
    )
    verb: str = Field(description="Display label, e.g. 'Reading matter documents'.")
    status: str = Field(
        description="'running', 'hit', 'empty', 'error', 'skipped' or 'declined'."
    )
    detail: str = ""
    count: int = 0
    elapsed_ms: int = 0


class RetrievalHit(BaseModel):

    matter_id: str | int | None = None
    score: float | None = None
    doc_type: str | None = None
    path: str | None = None
    text: str = Field(default="", description="Untrusted excerpt of client content.")

    @classmethod
    def from_hit(cls, hit: dict, *, text_limit: int = 2000) -> "RetrievalHit":
        return cls(
            matter_id=hit.get("matter_id"),
            score=hit.get("score"),
            doc_type=hit.get("doc_type"),
            path=hit.get("path"),
            text=str(hit.get("text") or "")[:text_limit],
        )


class RetrievalResponse(BaseModel):

    query: str
    matter_id: str | None = None
    sql_matches: list[ClientMatch] = Field(default_factory=list)
    rag_hits: list[RetrievalHit] = Field(default_factory=list)
    graph_child_names: list[str] = Field(
        default_factory=list,
        description="Names only from the live OneDrive listing -- not full item metadata.",
    )
    sources_checked: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    steps: list[RetrievalStepModel] = Field(default_factory=list)
    resolved_via_rag: bool = Field(
        default=False,
        description="True when the SQL match came from the RAG-resolved matter_id rather "
                    "than the question text, which is a weaker provenance.",
    )


class WorkLogEntry(BaseModel):

    work_id: str
    matter_id: str
    work_type: str
    status: str
    performed_by: str = ""
    performed_on_host: str = Field(
        default="",
        description="Which machine produced it. The point of recording it: with a "
                    "Streamlit server per PC, this is how you tell where work happened.",
    )
    occurred_at: str
    reference: str = ""
    artefact_url: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "WorkLogEntry":
        return cls(**{key: (row.get(key) or "") for key in cls.model_fields})


class WorkSummaryItem(BaseModel):
    count: int = 0
    latest: str = ""
    status: str = ""
    by: str = ""


class MatterWorkResponse(BaseModel):

    matter_id: str
    summary: dict[str, WorkSummaryItem] = Field(default_factory=dict)
    entries: list[WorkLogEntry] = Field(default_factory=list)


class RecordWorkRequest(BaseModel):

    matter_id: str = Field(min_length=1)
    work_type: str = Field(min_length=1)
    status: str = "completed"
    performed_by: str = ""
    performed_on_host: str = ""
    reference: str = ""
    artefact_url: str = ""
    notes: str = ""
    occurred_at: str = ""


class MonitorAlert(BaseModel):

    severity: str = ""
    title: str = ""
    summary: str = ""
    next_action: str = ""


class MonitorSummaryResponse(BaseModel):

    generated_at: str = ""
    overall_severity: str = "unknown"
    summary: str = ""
    alerts: list[MonitorAlert] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ObligationItem(BaseModel):

    matter_id: str | int | None = None
    matter_ref: str = ""
    client: str = ""
    order_type: str = ""
    has_c8: bool = False
    obligation: str = ""
    label: str = ""
    age_working_days: int | None = None
    hearing_date: str = ""
    hearing_working_days: int | None = None
    court: str = ""
    urgency: str = ""
    reason: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ObligationItem":
        declared = set(cls.model_fields)
        return cls(**{key: value for key, value in row.items() if key in declared})


class ObligationsResponse(BaseModel):

    count: int = 0
    overdue_count: int = 0
    error: str = Field(
        default="", description="Set when the underlying SQL/aging read failed; obligations is [] when non-empty."
    )
    obligations: list[ObligationItem] = Field(default_factory=list)


class RadarItem(BaseModel):

    ts: str = ""
    status: str = ""
    status_label: str = ""
    name: str = ""
    person_id: str = ""
    matter_id: str = ""
    caseforge_reference: str = ""
    web_link: str = ""


class RadarSummaryResponse(BaseModel):

    window_hours: int = 168
    alert_count: int = 0
    quiet_count: int = 0
    alert_lines: list[str] = Field(default_factory=list)
    items: list[RadarItem] = Field(default_factory=list)


class DocumentChecklistResponse(BaseModel):

    matter_id: str = ""
    loa_drafted: bool = False
    witness_statement_drafted: bool = False
    witness_statement_issue: str = ""


class GooseAskRequest(BaseModel):

    question: str = Field(min_length=1, max_length=20000)
    session_id: str = Field(default="", pattern=r"^(|goose_[A-Za-z0-9_]*)$")
    matter_id: str = Field(default="", pattern=r"^[0-9]*$")


class InternAuditEntry(BaseModel):

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    ts: str = ""
    remote_user: str | None = None
    question: str = ""
    matter_id: str | int | None = None
    carried: bool = False
    sources_summary: dict[str, Any] | None = None
    prior_turns_count: int = 0
    answer: str | None = None
    served_by: str | None = None
    model: str | None = None
    usage: dict[str, Any] | None = None
    error: str | None = None

    @classmethod
    def from_row(cls, row: dict) -> "InternAuditEntry":
        declared = set(cls.model_fields)
        return cls(**{key: value for key, value in row.items() if key in declared})


class InternAuditResponse(BaseModel):

    count: int = 0
    entries: list[InternAuditEntry] = Field(default_factory=list)
    note: str = Field(
        default="",
        description="'no audit records yet' when the audit file is missing or empty; otherwise empty.",
    )


INTERN_FEEDBACK_COMMENT_MAX_CHARS = 2000


class RetrievalFeedbackRequest(BaseModel):

    id: str | None = None
    ts_of_answer: str | None = None
    verdict: Literal["up", "down"]
    comment: str | None = Field(
        default=None,
        max_length=INTERN_FEEDBACK_COMMENT_MAX_CHARS,
        description=f"Optional free text, capped at {INTERN_FEEDBACK_COMMENT_MAX_CHARS} "
        "characters. No assistant-ui primitive collects this today (thumbs up/down "
        "only) -- accepted here for a future UI and for direct API use.",
    )


class RetrievalFeedbackResponse(BaseModel):

    ok: bool = True


class CreateCclRequest(BaseModel):

    client_name: str = Field(min_length=1)


class ClientEdit(BaseModel):

    edit_id: str
    matter_id: str
    field_name: str
    field_label: str = ""
    old_value: str | None = None
    new_value: str
    note: str = ""
    edited_by: str = ""
    created_at: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ClientEdit":
        from vergil import client_edits

        return cls(
            **{key: (row.get(key) or "") for key in cls.model_fields if key != "field_label"},
            field_label=client_edits.field_label(row.get("field_name", "")),
        )


class RecordEditRequest(BaseModel):

    matter_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    new_value: str = ""
    note: str = ""
    edited_by: str = Field(min_length=1)


class MatterFlagsResponse(BaseModel):

    matter_id: str
    flags: dict[str, bool] = Field(default_factory=dict)
    reasons: dict[str, str] = Field(default_factory=dict)
    shared: dict[str, bool] = Field(default_factory=dict)
    personal: dict[str, bool] = Field(default_factory=dict)
    personal_reasons: dict[str, str] = Field(default_factory=dict)


class SetFlagRequest(BaseModel):

    matter_id: str = Field(min_length=1)
    flag_name: str = Field(min_length=1)
    is_set: bool
    set_by: str = Field(min_length=1)
    reason: str = Field(default="", max_length=200)
    only_if_reason: str = Field(default="", max_length=200)
    scope: str = Field(default="personal", max_length=10)


class FieldReviewFlag(BaseModel):

    review_id: str
    matter_id: str
    client_name: str = ""
    field_name: str
    field_label: str = ""
    value_snapshot: str = ""
    note: str = ""
    flagged_by: str = ""
    flagged_at: str = ""
    resolved_by: str | None = None
    resolved_at: str | None = None

    @classmethod
    def from_row(cls, row: dict) -> "FieldReviewFlag":
        return cls(**row)


class ResolveFieldReviewRequest(BaseModel):

    review_id: str = Field(min_length=1)
    resolved_by: str = Field(min_length=1)


class FieldReviewQueueResponse(BaseModel):

    results: list[ClientMatch] = Field(default_factory=list)
    flags_by_matter: dict[str, list[FieldReviewFlag]] = Field(default_factory=dict)


class PersonMattersResponse(BaseModel):

    matter_id: str
    matters: list[ClientMatch] = Field(default_factory=list)


class MatterParty(BaseModel):

    party_id: str
    matter_id: str
    role: str = ""
    display_name: str = ""
    name_first: str = ""
    name_middle: str = ""
    name_last: str = ""
    aka_name: str = ""
    dob_iso: str = ""
    sex: str = ""
    sex_other: str = ""
    address_text: str = ""
    address_line1: str = ""
    address_line2: str = ""
    address_line3: str = ""
    address_line4: str = ""
    address_postcode: str = ""
    address_owner: str = ""
    work_address_line1: str = ""
    work_address_line2: str = ""
    work_address_line3: str = ""
    work_address_line4: str = ""
    work_address_postcode: str = ""
    phone_primary: str = ""
    phone_owner: str = ""
    email_primary: str = ""
    email_owner: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "MatterParty":
        return cls(**{k: ("" if v is None else str(v)) for k, v in row.items()})


class MatterPartiesResponse(BaseModel):

    matter_id: str
    parties: list[MatterParty] = Field(default_factory=list)


class AddPartyRequest(BaseModel):

    matter_id: str = Field(min_length=1)
    role: str = ""
    display_name: str = ""
    name_first: str = ""
    name_middle: str = ""
    name_last: str = ""
    aka_name: str = ""
    dob_iso: str = ""
    sex: str = ""
    sex_other: str = ""
    address_text: str = ""
    address_line1: str = ""
    address_line2: str = ""
    address_line3: str = ""
    address_line4: str = ""
    address_postcode: str = ""
    address_owner: str = ""
    work_address_line1: str = ""
    work_address_line2: str = ""
    work_address_line3: str = ""
    work_address_line4: str = ""
    work_address_postcode: str = ""
    phone_primary: str = ""
    phone_owner: str = ""
    email_primary: str = ""
    email_owner: str = ""
    edited_by: str = Field(min_length=1)
    note: str = ""


class UpdatePartyRequest(BaseModel):

    matter_id: str = Field(min_length=1)
    party_id: str = Field(min_length=1)
    role: str | None = None
    display_name: str | None = None
    name_first: str | None = None
    name_middle: str | None = None
    name_last: str | None = None
    aka_name: str | None = None
    dob_iso: str | None = None
    sex: str | None = None
    sex_other: str | None = None
    address_text: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    address_line3: str | None = None
    address_line4: str | None = None
    address_postcode: str | None = None
    address_owner: str | None = None
    work_address_line1: str | None = None
    work_address_line2: str | None = None
    work_address_line3: str | None = None
    work_address_line4: str | None = None
    work_address_postcode: str | None = None
    phone_primary: str | None = None
    phone_owner: str | None = None
    email_primary: str | None = None
    email_owner: str | None = None
    edited_by: str = Field(min_length=1)
    note: str = ""


class RemovePartyRequest(BaseModel):

    matter_id: str = Field(min_length=1)
    party_id: str = Field(min_length=1)
    edited_by: str = Field(min_length=1)
    note: str = ""


class SosStatusItem(BaseModel):

    name: str
    modified_utc: str = ""
    web_url: str = ""
    is_draft: bool = False


class SosStatusResponse(BaseModel):

    matter_id: str
    count: int
    draft_count: int = 0
    items: list[SosStatusItem] = Field(default_factory=list)
    folder_found: bool = True


class CaseFlowStage(BaseModel):
    id: str
    state: str
    evidence: str = ""


class CaseFlowResponse(BaseModel):

    matter_id: str
    track: str
    track_reason: str = ""
    stages: list[CaseFlowStage] = Field(default_factory=list)
    suggested_stage: str | None = None
    manual_stage: str | None = None
    manual_stage_set_by: str | None = None
    manual_stage_set_utc: str | None = None


class SetCaseStageRequest(BaseModel):

    matter_id: str = Field(min_length=1)
    stage: str | None = None
    set_by: str = Field(min_length=1)


class BillOfCostsItem(BaseModel):

    item_date: str
    description: str
    net_amount: str
    vat_amount: str
    party: str | None = None
    document_url: str | None = None
    schedule: int | None = None
    attendance_draft_id: str | None = None
    possible_double_bill: bool = False


class BillOfCostsCategory(BaseModel):

    category: str
    label: str
    items: list[BillOfCostsItem] = Field(default_factory=list)
    subtotal_net: str
    subtotal_vat: str


class BillOfCostsPartyLine(BaseModel):

    label: str
    count: int
    net: str
    vat: str


class BillOfCostsParty(BaseModel):

    party: str
    label: str
    lines: list[BillOfCostsPartyLine] = Field(default_factory=list)


class BillOfCostsRate(BaseModel):

    category: str
    label: str
    rate: str
    unit: str


class BillOfCostsRemovedItem(BaseModel):

    item_id: str
    item_date: str
    description: str
    category_label: str
    net_amount: str
    vat_amount: str
    removed_utc: str
    removed_by: str = ""


class BillOfCostsRateTbc(BaseModel):

    item_id: str
    item_date: str
    description: str


class BillOfCostsResponse(BaseModel):

    matter_id: str
    client_name: str = ""
    categories: list[BillOfCostsCategory] = Field(default_factory=list)
    parties: list[BillOfCostsParty] = Field(default_factory=list)
    billing_basis: str = "legal_aid"
    rates: list[BillOfCostsRate] = Field(default_factory=list)
    rate_tbc: list[BillOfCostsRateTbc] = Field(default_factory=list)
    total_net: str = "0.00"
    total_vat: str = "0.00"
    total_gross: str = "0.00"
    item_count: int = 0
    removed: list[BillOfCostsRemovedItem] = Field(default_factory=list)


class RestoreBillingItemRequest(BaseModel):

    item_id: str = Field(min_length=1, max_length=64)


class RestoreBillingItemResponse(BaseModel):
    item_id: str
    on_bill: bool
    restored_utc: str = ""
    restored_by: str = ""


class LegalAidBenefits(BaseModel):
    text: str = ""
    decision: str = ""
    todos: str = "none"


class LegalAidApplication(BaseModel):
    status: str
    date: str = ""
    name: str = ""
    url: str = ""


class LegalAidSignature(BaseModel):
    status: str
    date: str = ""
    by: str = ""
    url: str = ""


class LegalAidSectionResponse(BaseModel):

    matter_id: str
    assigned: bool = False
    benefits: LegalAidBenefits
    application: LegalAidApplication
    signature: LegalAidSignature
    can_send: bool = False
    problem: str = ""


class LegalAidSendRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)
    address_checked: bool = False


class LegalAidSendResponse(BaseModel):
    ok: bool
    code: str = ""
    message: str = ""
    section: LegalAidSectionResponse


class ConcludedMattersResponse(BaseModel):

    results: list[ClientMatch] = Field(default_factory=list)
    total: int = 0
    next_offset: int | None = None


class FlaggedMattersResponse(BaseModel):

    results: list[ClientMatch] = Field(default_factory=list)
    flags_by_matter: dict[str, list[str]] = Field(default_factory=dict)
    flag_reasons_by_matter: dict[str, str] = Field(default_factory=dict)


class CreateAttendanceNoteRequest(BaseModel):

    matter_id: str = Field(min_length=1)
    caller: Literal["court", "counsel", "client", "respondent", "other"] | None = None
    caller_other: str = ""
    note_text: str = Field(min_length=1)
    time_minutes: int | None = Field(default=None, ge=1, le=5999)
    kind: Literal["call", "perusal", "preparation"] = "call"
    pages: int | None = Field(default=None, ge=1, le=5000)
    doc_kind: str | None = None
    doc_other: str | None = Field(default=None, max_length=500)
    attendance_folder: str | None = None


class MinutesPerPageRequest(BaseModel):

    minutes_per_page: int = Field(ge=1, le=60)
    by: str = ""


class MinutesPerPageResponse(BaseModel):
    minutes_per_page: int


class ModelRolesResponse(BaseModel):

    can_edit: bool
    stats_days: int
    stats_available: bool
    anthropic_key_configured: bool
    models_in_use: list[str]
    roles: list[dict[str, Any]]


class ModelRoleSwapRequest(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    expected_old: str = Field(default="", max_length=120)


class ModelRoleChangeResponse(BaseModel):
    role: str
    old: str
    new: str


class ScannedFolderRequest(BaseModel):

    path: str = Field(default="", max_length=200)
    by: str = ""


class ScannedFolderResponse(BaseModel):
    path: str
    default: str


class EmailClassifierRequest(BaseModel):

    add: dict[str, list[str]] = Field(default_factory=dict)
    remove: dict[str, list[str]] = Field(default_factory=dict)


class EmailClassifierList(BaseModel):
    default: list[str]
    added: list[str]
    removed: list[str]
    effective: list[str]


class EmailClassifierResponse(BaseModel):
    lists: dict[str, EmailClassifierList]
    audit: list[dict[str, str]]


class CreateAttendanceNoteResponse(BaseModel):

    draft_id: str
    matter_id: str
    status: str
    an_url: str | None = None
    billing_item_id: str | None = None


class AttendanceNoteStatus(BaseModel):

    draft_id: str
    matter_id: str
    state: Literal["filing", "filed", "failed"]
    an_url: str | None = None
    unsorted: bool = False
    filed_folder: str = ""
    billing_item_id: str | None = None
    billing_removed: bool = False
    error: str | None = None
    created_utc: str
    kind: Literal["call", "letter_out", "letter_in", "perusal", "preparation", "bundle"] = "call"
    bundle_pages: int | None = None
    billing_note: str = ""


class AttendanceNoteRecentResponse(BaseModel):
    items: list[AttendanceNoteStatus] = Field(default_factory=list)


class RetryAttendanceNoteRequest(BaseModel):
    draft_id: str = Field(min_length=1)


class AttendanceNoteEditResponse(BaseModel):

    draft_id: str
    matter_id: str
    caller: str = ""
    caller_other: str = ""
    note_text: str
    time_minutes: int | None = None
    kind: Literal["call", "letter_out", "letter_in", "perusal", "preparation", "bundle"] = "call"
    pages: int | None = None


class TodoItem(BaseModel):

    todo_id: str
    title: str
    notes: str = ""
    matter_id: int | None = None
    client_name: str | None = None
    created_by: str = ""
    due_utc: str | None = None
    due_has_time: bool = False
    starred: bool = False
    my_day_date: str | None = None
    on_my_day_today: bool = False
    is_done: bool = False
    is_overdue: bool = False
    source: str = "manual"
    created_utc: str
    updated_utc: str
    done_utc: str | None = None
    done_by: str = ""
    draft_link: str = ""


class TodosResponse(BaseModel):
    items: list[TodoItem] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class TodoSummaryResponse(BaseModel):
    summary: dict[str, int] = Field(default_factory=dict)


class CreateTodoRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    created_by: str = Field(default="", max_length=60)
    matter_id: int | None = None
    due: str | None = None
    due_has_time: bool = False
    starred: bool = False
    my_day: bool = False
    notes: str = Field(default="", max_length=4000)


class UpdateTodoRequest(BaseModel):
    todo_id: str = Field(min_length=1)
    by: str = Field(default="", max_length=60)
    fields: dict[str, Any] = Field(default_factory=dict)


class CompleteTodoRequest(BaseModel):
    todo_id: str = Field(min_length=1)
    by: str = Field(default="", max_length=60)
    done: bool = True


class TodoAutomaticRequest(BaseModel):

    show: bool = True
    hidden: list[str] = Field(default_factory=list, max_length=20)


class DeleteTodoRequest(BaseModel):
    todo_id: str = Field(min_length=1)
    by: str = Field(default="", max_length=60)


class TodoEmailClientResponse(BaseModel):

    todo: TodoItem
    draft_link: str = ""
    warning: str = ""
    created: bool = True


class RobotNotice(BaseModel):

    notice_id: str
    kind: str
    title: str
    detail: str = ""
    matter_id: str = ""
    client_name: str = ""
    created_utc: str


class RobotNoticesResponse(BaseModel):
    count: int
    items: list[RobotNotice] = Field(default_factory=list)


class OpsHealthAlert(BaseModel):

    severity: str
    category: str
    title: str
    next_action: str = ""
    kind: str = "state"
    age_minutes: int | None = None


class OpsHealthResponse(BaseModel):

    available: bool
    generated_at: str = ""
    snapshot_age_minutes: int | None = None
    stale: bool = True
    overall_severity: str = "unknown"
    housekeeping_severity: str = "unknown"
    alerts: list[OpsHealthAlert] = Field(default_factory=list)


class SystemBox(BaseModel):

    box: str
    label: str
    host: str
    available: bool
    generated_at: str = ""
    age_minutes: int | None = None
    stale: bool = True
    cpu: dict[str, float | None] = Field(default_factory=dict)
    ram: dict[str, float | None] = Field(default_factory=dict)
    storage: dict[str, float | None] = Field(default_factory=dict)
    swap: dict[str, float | None] = Field(default_factory=dict)
    zram: list[dict[str, str | float | None]] = Field(default_factory=list)


class SystemProvider(BaseModel):

    key: str
    name: str
    state: str
    title: str = ""
    note: str = ""
    checked_at: str = ""
    flagged: bool = False


class SystemProviders(BaseModel):
    available: bool
    generated_at: str = ""
    age_minutes: int | None = None
    stale: bool = True
    providers: list[SystemProvider] = Field(default_factory=list)


class SystemSpend(BaseModel):

    available: bool
    note: str = ""
    generated_at: str = ""
    usage: float | None = None
    usage_daily: float | None = None
    limit: float | None = None
    limit_remaining: float | None = None
    remaining_fraction: float | None = None
    tone: str = "grey"


class SystemWorkerBox(BaseModel):

    box: str
    label: str
    available: bool
    generated_at: str = ""
    age_minutes: int | None = None
    stale: bool = True
    rows: list[dict[str, Any]] = Field(default_factory=list)


class SystemHealthchecks(BaseModel):
    available: bool
    note: str = ""
    checks: list[dict[str, Any]] = Field(default_factory=list)
    orphan_checks: list[dict[str, Any]] = Field(default_factory=list)


class SystemWorkers(BaseModel):
    boxes: list[SystemWorkerBox] = Field(default_factory=list)
    healthchecks: SystemHealthchecks


class SystemRows(BaseModel):

    available: bool
    note: str = ""
    rows: list[dict[str, Any]] = Field(default_factory=list)


class SystemFunction(BaseModel):
    key: str
    name: str
    last_event: str = ""
    state: str = "no_data"


class SystemServiceState(BaseModel):
    key: str
    state: str = "unknown"
    reason: str = ""
    since: str = ""


class SystemServices(BaseModel):

    available: bool = False
    generated_at: str = ""
    age_minutes: int | None = None
    stale: bool = True
    services: list[SystemServiceState] = Field(default_factory=list)


class StorageStatusResponse(BaseModel):

    available: bool
    note: str = ""
    generated_at: str = ""
    age_minutes: int | None = None
    stale: bool = True
    target_backup_bytes: int = 0
    rows: list[dict[str, Any]] = Field(default_factory=list)


class SystemStatusResponse(BaseModel):

    boxes: list[SystemBox] = Field(default_factory=list)
    providers: SystemProviders
    spend: SystemSpend
    workers: SystemWorkers
    backups: SystemRows
    expiries: SystemRows
    functions: list[SystemFunction] = Field(default_factory=list)
    services: SystemServices = Field(default_factory=SystemServices)


class BoxExtrasPush(BaseModel):

    box: str = Field(pattern="^dev$")
    generated_at: str = Field(min_length=1, max_length=40)
    schedules: list[dict[str, Any]] = Field(default_factory=list, max_length=400)
    healthchecks: dict[str, Any] = Field(default_factory=dict)


class BoxStatsPush(BaseModel):

    box: str = Field(pattern="^dev$")
    host: str = Field(default="", max_length=40)
    host: str = Field(default="", max_length=40)
    generated_at: str = Field(min_length=1, max_length=40)
    cpu: dict[str, float | None]
    ram: dict[str, float | None]
    storage: dict[str, float | None]
    swap: dict[str, float | None]
    zram: list[dict[str, str | float | None]] = Field(default_factory=list, max_length=8)


class AnBackupRequest(BaseModel):

    matter_id: str = Field(min_length=1)
    working: dict[str, Any] | None = None
    drafts: list[dict[str, Any]] = Field(default_factory=list)


class AnBackupResponse(BaseModel):
    working: dict[str, Any] | None = None
    drafts: list[dict[str, Any]] = Field(default_factory=list)


class FormDraftBackupRequest(BaseModel):

    matter_id: str = Field(min_length=1)
    form_id: str = Field(min_length=1)
    saved_at: float | None = None
    data: Any | None = None


class FormDraftBackupResponse(BaseModel):
    saved_at: float | None = None
    data: Any | None = None


class DismissRobotNoticeRequest(BaseModel):
    notice_id: str = Field(min_length=1)
    by: str = Field(default="", max_length=80)


class DeleteAttendanceNoteBillingRequest(BaseModel):
    draft_id: str = Field(min_length=1)


class FrequentCallersResponse(BaseModel):

    results: list[ClientMatch] = Field(default_factory=list)
    an_counts: dict[str, int] = Field(default_factory=dict)
    pinned_matters: list[str] = Field(default_factory=list)


class MatterTaskItem(BaseModel):

    task_id: str
    kind: str
    complaint_domain: str = ""
    settlement_stage: str = ""
    subject: str = ""
    summary: str = ""
    deadline: str = ""
    importance: str = "normal"
    status: str = ""
    created: str = ""
    web_link: str = ""
    can_complete: bool = False


class HearingModel(BaseModel):

    hearing_id: int
    matter_id: int | None = None
    client_name: str | None = None
    case_ref: str = ""
    hearing_date: str
    hearing_end_date: str = ""
    hearing_dates: str = ""
    multi_day: bool = False
    notice: str = ""
    not_before_date: str = ""
    hearing_label: str = ""
    hearing_time: str | None = None
    duration_minutes: int = 60
    duration_stated: bool = True
    hearing_type: str = ""
    order_types: str = ""
    is_final: bool = False
    court: str = ""
    mode: str = ""
    join_url: str = ""
    applicant: str = ""
    respondent: str = ""
    counsel: str = ""
    chambers: str = ""
    counsel_booked: bool = False
    bundle_done: bool | None = None
    bundle_why: str = ""
    overridden: dict[str, dict[str, object]] | None = None
    human_edited: bool = False
    status: str = "scheduled"
    vacate_kind: str = ""
    request_state: str = ""
    request_reason: str = ""
    replaced_by: dict[str, object] | None = None
    replaces_hearing_id: int | None = None
    review_state: str = "ok"
    review_reason: str = ""
    confidence: float | None = None
    source_kind: str = "manual"
    source_subject: str = ""
    source_received_utc: str = ""
    source_web_link: str = ""
    notes: str = ""
    created_utc: str = ""
    updated_utc: str = ""
    updated_by: str = ""


class HearingsResponse(BaseModel):

    hearings: list[HearingModel] = Field(default_factory=list)
    needs_review_count: int = 0
    open_leads_count: int = 0
    bank_holidays: dict[str, str] = Field(default_factory=dict)


class HearingLeadModel(BaseModel):

    lead_id: int
    source_subject: str = ""
    source_received_utc: str = ""
    source_web_link: str = ""
    reason: str = ""
    state: str = "open"
    created_utc: str = ""


class HearingLeadsResponse(BaseModel):
    leads: list[HearingLeadModel] = Field(default_factory=list)


class HearingLeadResolveRequest(BaseModel):
    lead_id: int
    action: str
    edited_by: str = Field(min_length=1)


class HearingLeadResponse(BaseModel):
    lead: HearingLeadModel


class HearingResponse(BaseModel):
    hearing: HearingModel


class HearingCreateRequest(BaseModel):

    case_ref: str = ""
    matter_id: int | None = None
    hearing_date: str = Field(min_length=1)
    hearing_end_date: str = ""
    hearing_dates: str = ""
    notice: str = ""
    hearing_time: str | None = None
    duration_minutes: int | None = None
    hearing_type: str = ""
    order_types: str = ""
    is_final: bool = False
    court: str = ""
    mode: str = ""
    join_url: str = ""
    applicant: str = ""
    respondent: str = ""
    counsel: str = ""
    chambers: str = ""
    notes: str = ""
    edited_by: str = Field(min_length=1)


class HearingUpdateRequest(BaseModel):
    hearing_id: int
    edits: dict[str, object]
    edited_by: str = Field(min_length=1)


class HearingStatusRequest(BaseModel):
    hearing_id: int
    status: str
    edited_by: str = Field(min_length=1)
    note: str = ""


class HearingVacateRequest(BaseModel):

    hearing_id: int
    kind: str
    edited_by: str = Field(min_length=1)
    reason: str = ""
    replacement: dict[str, object] | None = None


class HearingVacateResponse(BaseModel):
    hearing: HearingModel
    replacement: HearingModel | None = None


class HearingRequestOptionsResponse(BaseModel):
    hearing_id: int
    form: str = ""
    form_known: bool = False
    forms: list[str] = Field(default_factory=list)
    vacation_reasons: list[dict[str, str]] = Field(default_factory=list)
    hybrid_reasons: list[dict[str, str]] = Field(default_factory=list)


class HearingCourtRequest(BaseModel):

    hearing_id: int
    kind: str
    reasons: list[str] = Field(default_factory=list)
    form: str = ""
    draft: bool = True
    edited_by: str = Field(min_length=1)


class HearingCourtRequestResponse(BaseModel):
    hearing: HearingModel
    form: str = ""
    draft: dict[str, str] | None = None
    summary: str = ""


class HearingCourtDecisionRequest(BaseModel):
    hearing_id: int
    agreed: bool
    edited_by: str = Field(min_length=1)


class VergilTitleRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(default="", max_length=20000)


class VergilTitleResponse(BaseModel):
    title: str | None = None


class HearingReviewResolveRequest(BaseModel):
    hearing_id: int
    action: str
    edits: dict[str, object] | None = None
    edited_by: str = Field(min_length=1)


class HearingLinkRequest(BaseModel):
    hearing_id: int
    matter_id: int
    edited_by: str = Field(min_length=1)


class HearingUnlinkRequest(BaseModel):
    hearing_id: int
    edited_by: str = Field(min_length=1)


class HearingLinkResponse(BaseModel):
    hearing: HearingModel
    reference: str


class HearingSuggestion(BaseModel):
    matter_id: int
    client_name: str = ""
    matched_on: str = ""
    exact: bool = False


class HearingSuggestionsResponse(BaseModel):
    suggestions: list[HearingSuggestion] = Field(default_factory=list)


class HearingEventModel(BaseModel):
    event_id: int
    hearing_id: int
    at: str
    actor: str
    action: str
    before: object | None = None
    after: object | None = None
    source_message_id: str = ""


class HearingHistoryResponse(BaseModel):
    events: list[HearingEventModel] = Field(default_factory=list)


class MatterTasksResponse(BaseModel):

    matter_id: str
    configured: bool = True
    open_complaints: int = 0
    open_updates: int = 0
    open_settlements: int = 0
    items: list[MatterTaskItem] = Field(default_factory=list)


class AttentionItem(SameNameLabel):

    task_id: str
    matter_id: str = ""
    who: str = ""
    kind: str
    label: str = ""
    complaint_domain: str = ""
    severity: str = ""
    settlement_stage: str = ""
    subject: str = ""
    summary: str = ""
    deadline: str = ""
    importance: str = "normal"
    created: str = ""
    web_link: str = ""
    sender_domain: str = ""
    can_complete: bool = False


class AttentionObligation(SameNameLabel):

    matter_id: str = ""
    matter_ref: str = ""
    client: str = ""
    label: str = ""
    urgency: str = ""
    reason: str = ""
    hearing_date: str = ""
    age_working_days: int | None = None
    court: str = ""
    has_c8: bool = False


class AttentionResponse(BaseModel):

    configured: bool = True
    red_count: int = 0
    yellow_count: int = 0
    green_count: int = 0
    red: list[AttentionItem] = Field(default_factory=list)
    yellow: list[AttentionItem] = Field(default_factory=list)
    green: list[AttentionItem] = Field(default_factory=list)
    scope_creep_count: int = 0
    scope_creep: list[AttentionItem] = Field(default_factory=list)
    counsel_accepted_count: int = 0
    counsel_accepted: list[AttentionItem] = Field(default_factory=list)
    counsel_rejected_count: int = 0
    counsel_rejected: list[AttentionItem] = Field(default_factory=list)
    court_order_count: int = 0
    court_order: list[AttentionItem] = Field(default_factory=list)
    court_rejected_count: int = 0
    court_rejected: list[AttentionItem] = Field(default_factory=list)
    obligations_count: int = 0
    obligations: list[AttentionObligation] = Field(default_factory=list)
    obligations_error: str = ""


class AttentionCompleteRequest(BaseModel):

    task_id: str = ""
    by: str = Field(default="", max_length=60)



class MatterChild(BaseModel):

    child_id: str
    matter_id: str
    child_name: str = ""
    name_first: str = ""
    name_middle: str = ""
    name_last: str = ""
    dob_iso: str = ""
    gender: str = ""
    parental_responsibility: str = ""
    lives_with: str = ""
    notes: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "MatterChild":
        return cls(**{k: ("" if v is None else str(v)) for k, v in row.items()})


class MatterChildrenResponse(BaseModel):
    matter_id: str
    children: list[MatterChild] = Field(default_factory=list)


class AddChildRequest(BaseModel):
    matter_id: str = Field(min_length=1)
    name_first: str = ""
    name_middle: str = ""
    name_last: str = ""
    dob_iso: str = ""
    gender: str = ""
    parental_responsibility: str = ""
    lives_with: str = ""
    notes: str = ""
    edited_by: str = Field(min_length=1)
    note: str = ""


class UpdateChildRequest(BaseModel):

    matter_id: str = Field(min_length=1)
    child_id: str = Field(min_length=1)
    name_first: str | None = None
    name_middle: str | None = None
    name_last: str | None = None
    dob_iso: str | None = None
    gender: str | None = None
    parental_responsibility: str | None = None
    lives_with: str | None = None
    notes: str | None = None
    edited_by: str = Field(min_length=1)
    note: str = ""


class RemoveChildRequest(BaseModel):
    matter_id: str = Field(min_length=1)
    child_id: str = Field(min_length=1)
    edited_by: str = Field(min_length=1)
    note: str = ""


class HearingExtractRequest(BaseModel):

    text: str = Field(max_length=4000)
    today: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class HearingExtractResponse(BaseModel):

    court: str = ""
    hearing_type: str = ""
    counsel: str = ""
    chambers: str = ""
    mode: str = ""
    time: str | None = None
    without_notice: bool = False
    notes: str = ""


class PipelineStepView(BaseModel):
    key: str
    number: int | None = None
    label: str
    status: str
    summary: str
    detail: list[str] = Field(default_factory=list)
    can_run: bool = False
    run_label: str = "Run"
    variants: list[dict[str, str]] = Field(default_factory=list)
    outside: str = ""
    actor: str = ""
    court_suggestions: list[dict[str, str]] = Field(default_factory=list)
    links: list[dict[str, str]] = Field(default_factory=list)
    resettable: bool = False
    checked_utc: str = ""
    auto_tries: int = 0
    auto_max: int = 0
    amend: dict[str, Any] | None = None


class PipelineEventView(BaseModel):
    event_id: str
    step: str
    status: str
    summary: str
    by: str
    mode: str
    created_utc: str
    instance: str = ""
    links: list[dict[str, str]] = Field(default_factory=list)
    actor_kind: str = ""



class PipelineResponse(BaseModel):
    matter_id: str
    client_name: str
    mode: str
    matter_mode: str = "inherit"
    matter_mode_by: str = ""
    matter_mode_at: str = ""
    effective_mode: str = ""
    auto_reason: str = ""
    locked: bool = False
    lock_reason: str = ""
    sync: dict[str, Any] | None = None
    steps: list[PipelineStepView]
    events: list[PipelineEventView]


class ActivityViewer(BaseModel):

    who: str
    at: str


class PipelineActivityResponse(BaseModel):

    matter_id: str
    events: list[PipelineEventView]
    seen_by: list[ActivityViewer] = []


class IntroLinkResponse(BaseModel):

    matter_id: str
    url: str = ""


class MatterMarkerView(BaseModel):
    status: str
    reason: str = ""
    date: str = ""
    url: str = ""


class MatterMarkersResponse(BaseModel):

    matter_id: str
    loa: MatterMarkerView
    initial_ws: MatterMarkerView
    intro: MatterMarkerView = MatterMarkerView(status="unknown")


class PipelineRunRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=20)
    step: str = Field(min_length=1, max_length=30)
    by: str = Field(min_length=1, max_length=60)
    variant: str | None = Field(default=None, max_length=40)


class PipelineRunResponse(BaseModel):
    ok: bool
    message: str
    links: list[dict[str, str]] = Field(default_factory=list)
    pipeline: PipelineResponse


class PipelineResetStepRequest(BaseModel):

    matter_id: str = Field(min_length=1, max_length=20)
    step: str = Field(min_length=1, max_length=30)
    by: str = Field(min_length=1, max_length=60)


class NewClientRequest(BaseModel):

    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=200)
    category: str = Field(min_length=1, max_length=40)
    send_rif: bool = False
    send_laif: bool = False
    address_checked: bool = False
    by: str = Field(min_length=1, max_length=60)
    request_id: str = Field(default="", max_length=64)
    phone: str = Field(default="", max_length=30)


class ManualClientRequest(BaseModel):

    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=40)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=30)
    middle_name: str = Field(default="", max_length=80)
    dob: str = Field(default="", max_length=40)
    nino: str = Field(default="", max_length=20)
    address_line1: str = Field(default="", max_length=120)
    address_line2: str = Field(default="", max_length=120)
    address_line3: str = Field(default="", max_length=120)
    address_line4: str = Field(default="", max_length=120)
    postcode: str = Field(default="", max_length=12)
    matter_details: str = Field(default="", max_length=1000)
    address_checked: bool = False
    by: str = Field(min_length=1, max_length=60)


class PendingNewClientResumeRequest(BaseModel):

    pending_id: int = Field(ge=1)
    by: str = Field(min_length=1, max_length=60)


class PendingNewClientCancelRequest(BaseModel):

    pending_id: int = Field(ge=1)
    by: str = Field(min_length=1, max_length=60)


class ClientRemoveRequest(BaseModel):

    matter_id: str = Field(min_length=1, max_length=20)
    typed_name: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=3, max_length=500)
    by: str = Field(min_length=1, max_length=60)


class ClientUndoRemoveRequest(BaseModel):

    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)


class MailReviewAnswerRequest(BaseModel):

    n: int = Field(ge=1, le=100000)
    route: str = Field(default="", max_length=200)
    also: str = Field(default="", max_length=200)
    no_clean_answer: bool = False
    matter: str = Field(default="", max_length=5000)
    logic: str = Field(default="", max_length=20000)


class MailReviewDecideRequest(BaseModel):

    job_id: str = Field(min_length=1, max_length=80)
    route: str = Field(default="", max_length=200)
    also: str = Field(default="", max_length=200)
    logic: str = Field(default="", max_length=20000)
    other_text: str = Field(default="", max_length=200)


class MailReviewControlRequest(BaseModel):

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    job_id: str = Field(min_length=1, max_length=80)
    verdict: Literal["agree", "disagree"]
    route: str = Field(default="", max_length=200)
    also: str = Field(default="", max_length=200)
    logic: str = Field(default="", max_length=20000)
    other_text: str = Field(default="", max_length=200)


class MailReviewControlReleaseRequest(BaseModel):

    job_id: str = Field(min_length=1, max_length=80)


class MailReviewExtendRequest(BaseModel):
    days: int
    by: str = Field(min_length=1, max_length=60)


class ClientMergeRequest(BaseModel):

    from_matter_id: str = Field(min_length=1, max_length=20)
    into_matter_id: str = Field(min_length=1, max_length=20)
    typed_from: str = Field(min_length=1, max_length=160)
    typed_into: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=3, max_length=500)
    by: str = Field(min_length=1, max_length=60)
    choices: dict[str, str] = Field(default_factory=dict, max_length=40)


class ClientUndoMergeRequest(BaseModel):

    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)


class CaseBoardRemoveRequest(BaseModel):

    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)


class LexcelLetterView(BaseModel):
    kind: str
    label: str
    button: str
    made: bool = False
    made_utc: str = ""
    made_by: str = ""
    made_via: str = ""
    times: int = 0
    summary: str = ""
    links: list[dict[str, str]] = Field(default_factory=list)
    can_make: bool = True
    note: str = ""
    checklist: list[dict[str, Any]] = Field(default_factory=list)
    file_present: bool = False
    hearings: list[dict[str, str]] = Field(default_factory=list)
    auto: dict[str, Any] | None = None
    locked: str = ""


class LexcelResponse(BaseModel):

    matter_id: str
    letters: list[LexcelLetterView]


class LexcelMakeRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=20)
    kind: str = Field(min_length=1, max_length=10)
    by: str = Field(min_length=1, max_length=60)
    variant: str | None = Field(default=None, max_length=40)


class LexcelAutoRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)
    resume: bool = False


class LexcelMakeResponse(BaseModel):
    ok: bool
    message: str
    offers: list[dict[str, str]] = Field(default_factory=list)
    links: list[dict[str, str]] = Field(default_factory=list)
    lexcel: LexcelResponse


class CaseReviewVersionView(BaseModel):
    review_date: str
    saved_by: str
    saved_utc: str
    counts: dict[str, dict[str, int]] = Field(default_factory=dict)


class CaseReviewResponse(BaseModel):

    matter_id: str
    review_date: str
    today: str
    saved: bool = False
    saved_by: str = ""
    saved_utc: str = ""
    first_saved_by: str = ""
    first_saved_utc: str = ""
    forms: list[dict[str, Any]]
    answers: dict[str, dict[str, str]] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    versions: list[CaseReviewVersionView] = Field(default_factory=list)


class CaseReviewSaveRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=20)
    review_date: str = Field(min_length=10, max_length=10)
    by: str = Field(min_length=1, max_length=60)
    answers: dict[str, dict[str, str]] = Field(default_factory=dict)


class ConflictMatchView(BaseModel):

    direction: str
    strength: str
    reasons: list[str] = Field(default_factory=list)
    this_is: str = ""
    that_is: str = ""
    other_name: str = ""
    other_matter_id: str = ""
    other_reference: str = ""
    other_client: str = ""
    other_closed: bool = False


class CourtRouteCallFirst(BaseModel):
    name: str
    phone: str
    note: str = ""


class CourtRouteResponse(BaseModel):

    matter_id: str
    show: bool = False
    call_first: CourtRouteCallFirst | None = None


class ConflictCheckResponse(BaseModel):

    matter_id: str
    run: bool = False
    run_utc: str = ""
    run_by: str = ""
    stale: bool = False
    verdict: str = ""
    matches: list[ConflictMatchView] = Field(default_factory=list)
    held_back: int = 0
    parties_checked: int = 0
    compared: dict[str, int] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)


class ConflictCheckRunRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)


class PipelineModeRequest(BaseModel):
    mode: str = Field(min_length=1, max_length=10)
    by: str = Field(min_length=1, max_length=60)
    matter_id: str | None = Field(default=None, max_length=20)


class PipelineResetRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)


class PipelineMarkDoneRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=20)
    step: str = Field(min_length=1, max_length=30)
    by: str = Field(min_length=1, max_length=60)
    note: str | None = Field(default=None, max_length=300)


class PipelineConfirmCourtRequest(BaseModel):

    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)
    court: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=200)


class PipelineServiceRecipientRequest(BaseModel):

    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)
    kind: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200)


class PipelineAmendPrepareRequest(BaseModel):

    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)
    email_text: str = Field(min_length=1, max_length=60000)


class PipelineAmendApproveRequest(BaseModel):

    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)
    round: int = Field(ge=1, le=999)
    answers: str = Field(default="", max_length=5000)
    keep_original: list[str] = Field(default_factory=list, max_length=200)
    client_questions: list[str] | None = Field(default=None, max_length=8)
    edits: dict[str, str] = Field(default_factory=dict, max_length=200)


class PipelineAmendDiscardRequest(BaseModel):

    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)
    round: int = Field(ge=1, le=999)


class PipelineModeResponse(BaseModel):
    mode: str


class PipelineMatterModeRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=20)
    setting: str = Field(min_length=1, max_length=10)
    by: str = Field(min_length=1, max_length=60)


class PipelineMatterModeResponse(BaseModel):

    matter_id: str
    setting: str
    by: str = ""
    at: str = ""
    mode: str
    effective_mode: str


class ScanRow(BaseModel):

    id: str = ""
    name: str
    scan_date: str = ""
    date_source: Literal["filename", "uploaded", "modified", "unknown"] = "unknown"
    uploaded_utc: str = ""
    modified_utc: str = ""
    pages: int | None = None
    possible_client: str = ""
    folder: str = ""
    web_url: str = ""
    size_bytes: int = 0
    same_contents_as: list[str] = Field(default_factory=list)


class ScansCountResponse(BaseModel):

    known: bool
    count: int = 0
    checked_utc: str = ""


class ScansResponse(BaseModel):

    folder: str
    readable: bool
    total: int
    folders_not_listed: int = 0
    read_utc: str
    rows: list[ScanRow]


class FolderLockRequest(BaseModel):

    folder: str = Field(min_length=1, max_length=120)
    locked: bool
    by: str = Field(min_length=1, max_length=60)


class AuditFolderFlagRequest(BaseModel):

    client: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=500)
    type: Literal["file", "folder"] = "file"
    flagged: bool
    note: str = Field(default="", max_length=300)


class MatterMilestoneRequest(BaseModel):

    matter_id: str = Field(min_length=1, max_length=40)
    milestone: str = Field(min_length=1, max_length=30)
    at: str = Field(default="", max_length=40)
    clear: bool = False


class WeTransferGateRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    matter_id: str = Field(min_length=1, max_length=40, pattern=r"^\d+$")


class RecordSignedWsRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    matter_id: str = Field(min_length=1, max_length=40, pattern=r"^\d+$")
    item_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9!_-]+$")


class ClientNudgeRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    matter_id: str = Field(min_length=1, max_length=40, pattern=r"^\d+$")
    doc: Literal["client_docs", "witness_statement"]


class ClientNudgeResponse(BaseModel):
    ok: bool
    matter_id: str
    doc: str
    rule_id: str
    draft_id: str


class AutoSendDismissRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=300)


class AutoSendDismissResponse(BaseModel):
    ok: bool
    id: str
    dismissed_by: str
    dismissed_utc: str


class StatementReplyItem(BaseModel):
    matter_id: str
    client_name: str = ""
    state: str
    note: str = ""
    by: str = ""
    recorded_utc: str = ""


class DraftItem(BaseModel):

    id: str
    subject: str
    recipients: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    matter_id: str = ""
    client_name: str = ""
    created_utc: str = ""
    attachment_count: int = 0
    web_link: str = ""
    scheduled_utc: str = ""
    human_touched: bool = False


class DraftsResponse(BaseModel):

    configured: bool = True
    count: int = 0
    scheduled_count: int = 0
    items: list[DraftItem] = Field(default_factory=list)


class StatementRepliesResponse(BaseModel):
    approved_count: int
    amend_count: int
    items: list[StatementReplyItem]


class StatementReplyRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=20)
    state: str = Field(default="", max_length=10)
    note: str = Field(default="", max_length=60000)
    by: str = Field(min_length=1, max_length=60)


class NotificationStateRequest(BaseModel):

    nid: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=12)
    by: str = Field(default="", max_length=60)


class StatementReplyHideRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=20)
    by: str = Field(min_length=1, max_length=60)


class StatementReplyResponse(BaseModel):
    matter_id: str
    state: str


class AppSettingsResponse(BaseModel):

    can_edit: bool
    secrets_note: str
    groups: list[dict[str, Any]]
    settings: list[dict[str, Any]]
    status: list[dict[str, Any]]


class LogoResponse(BaseModel):
    logo: str


class SpecialSenderMark(BaseModel):

    text: str = ""
    colours: list[str] = Field(default_factory=list)
    background: str = ""


class SpecialSenderIn(BaseModel):

    id: str = ""
    name: str = ""
    domains: list[str] = Field(default_factory=list)
    new_clients: bool = False
    mark: SpecialSenderMark | None = None


class SpecialSendersRequest(BaseModel):

    senders: list[SpecialSenderIn] = Field(default_factory=list)


class SpecialSenderOut(BaseModel):
    id: str
    name: str
    domains: list[str]
    new_clients: bool
    logo: str
    mark: SpecialSenderMark | None = None


class SpecialSendersResponse(BaseModel):
    items: list[SpecialSenderOut]
