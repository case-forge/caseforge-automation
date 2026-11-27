from __future__ import annotations

import datetime as dt
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

STRONG_RAG_SCORE = 0.72

_REFERENCE_TOKEN_RE = re.compile(
    r"\b(?=[A-Za-z0-9/\-]*[A-Za-z])(?=[A-Za-z0-9/\-]*\d)[A-Za-z0-9][A-Za-z0-9/\-]{4,}\b"
)


def question_names_a_reference(question: str) -> bool:
    return bool(_REFERENCE_TOKEN_RE.search(question or ""))

GAP_NO_MATTER_DOCS = "no matching matter documents found"
GAP_MATTER_DOCS_UNREADABLE = (
    "matching matter documents exist in the index but their text "
    "could not be read on this box, so they were not quoted; the "
    "live folder listing was used instead"
)
GAP_RESOLVED_VIA_RAG = (
    "the matter was found by matching the document search results, not the "
    "original search text"
)
GAP_CARRIED_SCOPE_KEPT_OVER_RAG_GUESS = (
    "a document search match for a different matter than the one "
    "already established in this conversation was found and set "
    "aside -- the established matter was kept; ask explicitly if "
    "this question is actually about someone else"
)
GAP_STALE_CORRESPONDENCE = (
    "the most recent correspondence found significantly predates today and no live "
    "OneDrive folder or matter documents were found either -- this matter may be "
    "concluded or inactive. Do not draft present-tense time-sensitive content (an "
    "upcoming hearing, a \"you must attend\" instruction) from these dates without "
    "first confirming the case is still live -- check mail_hits' own sent_at dates"
)

STEP_VERBS = {
    "sql": "Searching the case database",
    "rag": "Reading matter documents",
    "sql_retry": "Re-checking the case database against the document match",
    "graph": "Listing the live OneDrive folder",
    "mail": "Searching the mailbox",
}

SOURCE_LABELS = {
    "sql": "the case database",
    "rag": "the matter documents",
    "graph": "the live OneDrive folder",
    "mail": "the mailbox",
}


@dataclass
class RetrievalStep:

    source: str
    verb: str
    status: str
    detail: str = ""
    count: int = 0
    elapsed_ms: int = 0


@dataclass
class CarriedScope:

    matter_id: Optional[str] = None
    client_name: str = ""
    client_email: str = ""
    hard: bool = False


@dataclass
class RetrievalContext:

    question: str
    matter_id: Optional[str] = None
    sql_hits: list[dict] = field(default_factory=list)
    rag_hits: list[dict] = field(default_factory=list)
    graph_listing: Optional[dict] = None
    matched_folder_name: str = ""
    mail_hits: list[dict] = field(default_factory=list)
    sources_checked: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    steps: list[RetrievalStep] = field(default_factory=list)
    resolved_via_rag: bool = False
    carried_over: bool = False
    carried_client_name: str = ""
    carried_client_email: str = ""
    person_aliases: list[dict] = field(default_factory=list)

    @property
    def found_anything(self) -> bool:
        return bool(self.sql_hits or self.strong_rag_hits or self.graph_listing or self.mail_hits)

    @property
    def strong_rag_hits(self) -> list[dict]:
        return [h for h in self.rag_hits if h.get("score", 0) >= STRONG_RAG_SCORE]

    @property
    def resolved_a_client(self) -> bool:
        return bool(self.matter_id or self.matched_folder_name)

    @property
    def client_name(self) -> str:
        for row in self.sql_hits:
            name = str(row.get("client_name") or "").strip()
            if name:
                return name
        if self.matched_folder_name:
            name = self.matched_folder_name
            try:
                from sql import client_name_resolver

                name = client_name_resolver.strip_c8_tag(name)
            except Exception:
                pass
            name = name.rsplit(" - ", 1)[0]
            try:
                from sql import client_name_resolver

                name = str(client_name_resolver.strip_matter_suffixes(name))
            except Exception:
                pass
            return name.strip()
        return self.carried_client_name

    @property
    def client_email(self) -> str:
        for row in self.sql_hits:
            email = str(row.get("client_email") or "").strip()
            if email:
                return email
        if self.matched_folder_name:
            return ""
        return self.carried_client_email

    @property
    def prompt_rag_hits(self) -> list[dict]:
        filtered = [h for h in self.rag_hits if h.get("score", 0) >= STRONG_RAG_SCORE]
        if self.matter_id:
            filtered = [
                h for h in filtered
                if str(h.get("matter_id", self.matter_id)) == self.matter_id
            ]
        return [h for h in filtered if _hit_text_resolved(h)]

    @property
    def readable_strong_rag_hits(self) -> list[dict]:
        return [h for h in self.strong_rag_hits if _hit_text_resolved(h)]


def _hit_text_resolved(hit: dict) -> bool:
    if "text_resolved" in hit:
        return bool(hit["text_resolved"])
    return bool(str(hit.get("text") or "").strip())


STALE_CORRESPONDENCE_DAYS = 120


def _flag_stale_correspondence(context: RetrievalContext) -> None:
    if context.graph_listing or context.rag_hits or not context.mail_hits:
        return

    from vergil.formatting import parse_iso_dt

    newest: dt.datetime | None = None
    for hit in context.mail_hits:
        parsed = parse_iso_dt(str(hit.get("sent_at", "")))
        if parsed and (newest is None or parsed > newest):
            newest = parsed
    if newest is None:
        return

    age_days = (dt.datetime.now(dt.timezone.utc) - newest).days
    if age_days >= STALE_CORRESPONDENCE_DAYS:
        context.gaps.append(GAP_STALE_CORRESPONDENCE)


StepCallback = Callable[[RetrievalStep], None]


def _noop(step: RetrievalStep) -> None:
    del step


class _Reporter:

    def __init__(self, context: RetrievalContext, on_step: StepCallback) -> None:
        self._context = context
        self._on_step = on_step

    def emit(self, step: RetrievalStep) -> None:
        self._context.steps.append(step)
        try:
            self._on_step(step)
        except Exception:
            pass

    def start(self, source: str) -> float:
        self.emit(RetrievalStep(source, STEP_VERBS.get(source, source), "running"))
        return time.monotonic()

    def done(
        self, source: str, started: float, status: str, *, detail: str = "", count: int = 0
    ) -> None:
        self.emit(
            RetrievalStep(
                source=source,
                verb=STEP_VERBS.get(source, source),
                status=status,
                detail=detail,
                count=count,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        )


def _person_aliases_for(sql_hits: list[dict]) -> list[dict]:
    ids = sorted({str(h.get("primary_person_id")) for h in sql_hits if h.get("primary_person_id")})
    if not ids:
        return []
    try:
        import clientdb_sql

        marks = ",".join("?" for _ in ids)
        with clientdb_sql.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT alias_text, alias_kind, note FROM dbo.person_aliases WHERE person_id IN ({marks})",
                tuple(ids),
            )
            rows = cursor.fetchall()
    except Exception as exc:
        print(f"[retrieval] person_aliases lookup failed ({type(exc).__name__}, {len(ids)} person id(s)); answering without aliases", file=sys.stderr)
        return []
    return [
        {"alias_text": str(r[0] or ""), "alias_kind": str(r[1] or ""), "note": str(r[2] or "")[:300]}
        for r in rows
        if r[0]
    ]


def _mail_of_anchored_matter(hits: list[dict], context: "RetrievalContext") -> tuple[list[dict], int]:
    addresses = {context.client_email.strip().lower()} - {""}
    references = {
        str(row.get("company_reference") or "").strip().lower() for row in context.sql_hits if isinstance(row, dict)
    } - {""}

    def belongs(hit: dict) -> bool:
        people = " ".join(
            str(v) if not isinstance(v, (list, tuple)) else " ".join(map(str, v))
            for v in (hit.get("correspondent"), hit.get("from"), hit.get("to"), hit.get("cc"))
            if v
        ).lower()
        text = f"{hit.get('subject') or ''} {hit.get('body') or ''}".lower()
        return any(a in people for a in addresses) or any(r in text for r in references)

    kept = [h for h in hits if isinstance(h, dict) and belongs(h)]
    return kept, len(hits) - len(kept)


def retrieve(
    question: str,
    *,
    on_step: Optional[StepCallback] = None,
    engine: Any = None,
    carried_scope: Optional[Any] = None,
) -> RetrievalContext:
    context = RetrievalContext(question=question)
    report = _Reporter(context, on_step or _noop)
    if engine is None:
        from retrieval_engine import engine as default_engine

        engine = default_engine

    hard_scope = carried_scope if isinstance(carried_scope, CarriedScope) and carried_scope.hard else None
    if hard_scope and hard_scope.matter_id:
        context.sources_checked.append(SOURCE_LABELS["sql"])
        started = report.start("sql")
        import clientdb_sql

        try:
            row = clientdb_sql.get_client_by_matter_id(hard_scope.matter_id)
        except Exception:
            row = None
        context.sql_hits = [row] if row else []
        context.matter_id = hard_scope.matter_id
        context.carried_client_name = hard_scope.client_name
        context.carried_client_email = hard_scope.client_email
        report.done("sql", started, "hit" if row else "empty", count=len(context.sql_hits))
        if not row:
            context.gaps.append(
                "no matter record matches the anchored client id -- this is not a "
                "confirmed absence; the record may be temporarily unreachable"
            )
        sql_error = None
    else:
        context.sources_checked.append(SOURCE_LABELS["sql"])
        started = report.start("sql")
        sql_error = None
        try:
            context.sql_hits, sql_error = engine.sql_lookup(question)
        except Exception as exc:
            sql_error = str(exc)[:200]
            context.sql_hits = []
    is_ambiguous_sql = len({str(h.get("matter_id") or "") for h in context.sql_hits}) > 1
    if context.sql_hits:
        context.matter_id = str(context.sql_hits[0].get("matter_id") or "") or None
        report.done("sql", started, "hit", count=len(context.sql_hits))
    elif sql_error:
        report.done("sql", started, "error", detail="lookup failed this turn")
    else:
        report.done("sql", started, "empty")

    context.sources_checked.append(SOURCE_LABELS["rag"])
    started = report.start("rag")
    try:
        context.rag_hits = engine.rag_search(question, matter_id=context.matter_id)
    except Exception:
        context.rag_hits = []
        report.done("rag", started, "error", detail="document search unavailable")
    else:
        strong = context.strong_rag_hits
        report.done("rag", started, "hit" if strong else "empty", count=len(strong))
    rag_matter_signal = bool(context.strong_rag_hits)
    weak_rag = not context.readable_strong_rag_hits

    asked_by_reference = question_names_a_reference(question)
    if not context.sql_hits and rag_matter_signal and asked_by_reference and not hard_scope:
        context.gaps.append(
            "the reference in this question was not found in the case database, and "
            "document matches for other matters were not used to guess a different one"
        )
    if not context.sql_hits and rag_matter_signal and not asked_by_reference and not hard_scope:
        started = report.start("sql_retry")
        try:
            retried, retry_error = engine.sql_lookup_via_rag_matter(context.rag_hits)
        except Exception as exc:
            retried, retry_error = [], str(exc)[:200]
        if retried:
            context.sql_hits = retried
            context.matter_id = str(retried[0].get("matter_id") or "") or None
            context.resolved_via_rag = True
            sql_error = None
            report.done("sql_retry", started, "hit", count=len(retried))
        else:
            if retry_error:
                print(f"[retrieval] sql_lookup_via_rag_matter failed: {retry_error}", file=sys.stderr)
            report.done(
                "sql_retry", started, "error" if retry_error else "empty",
                detail="retry failed" if retry_error else "",
            )

    if context.resolved_via_rag:
        context.gaps.append(GAP_RESOLVED_VIA_RAG)
    elif sql_error:
        print(f"[retrieval] sql_lookup failed: {sql_error}", file=sys.stderr)
        context.gaps.append(
            "the case database lookup could not be completed this turn -- this is not "
            "a confirmed absence; the client or matter may still exist"
        )
    elif not context.sql_hits:
        context.gaps.append("no matching matter in the case database for this question")

    if weak_rag:
        if context.strong_rag_hits:
            context.gaps.append(GAP_MATTER_DOCS_UNREADABLE)
        else:
            context.gaps.append(GAP_NO_MATTER_DOCS)

    weak_sql_resolution = context.resolved_via_rag or is_ambiguous_sql
    if (not context.resolved_a_client or weak_sql_resolution) and carried_scope:
        resolved_scope = carried_scope() if callable(carried_scope) else carried_scope
        if resolved_scope and resolved_scope.client_name:
            context.carried_client_name = resolved_scope.client_name
            context.carried_client_email = resolved_scope.client_email
            if resolved_scope.matter_id:
                if weak_sql_resolution and context.matter_id != resolved_scope.matter_id:
                    context.sql_hits = []
                    context.resolved_via_rag = False
                    if GAP_RESOLVED_VIA_RAG in context.gaps:
                        context.gaps.remove(GAP_RESOLVED_VIA_RAG)
                    context.gaps.append(GAP_CARRIED_SCOPE_KEPT_OVER_RAG_GUESS)
                context.matter_id = resolved_scope.matter_id
                if weak_rag:
                    try:
                        carried_rag_hits = engine.rag_search(question, matter_id=context.matter_id)
                    except Exception:
                        carried_rag_hits = []
                    if carried_rag_hits:
                        context.rag_hits = carried_rag_hits
                        if context.prompt_rag_hits:
                            for stale_gap in (GAP_NO_MATTER_DOCS, GAP_MATTER_DOCS_UNREADABLE):
                                if stale_gap in context.gaps:
                                    context.gaps.remove(stale_gap)
                        else:
                            if GAP_NO_MATTER_DOCS in context.gaps:
                                context.gaps.remove(GAP_NO_MATTER_DOCS)
                            if GAP_MATTER_DOCS_UNREADABLE not in context.gaps:
                                context.gaps.append(GAP_MATTER_DOCS_UNREADABLE)
                elif context.strong_rag_hits:
                    context.gaps.append(
                        "matching matter documents were found for a different, "
                        "unconfirmed matter this turn and were not shown, to avoid "
                        "quoting the wrong client's documents"
                    )

    if not context.sql_hits or weak_rag:
        started = report.start("graph")
        graph_failed = False
        searched_but_no_match = False
        try:
            if context.matter_id:
                context.graph_listing = engine.graph_fallback_listing(context.matter_id)
            else:
                found = engine.folder_search_by_name(context.client_name or question)
                if found is not None and found.get("listing") is not None:
                    context.graph_listing = found["listing"]
                    context.matched_folder_name = found["folder_name"]
                elif found is not None:
                    searched_but_no_match = True
        except Exception:
            context.graph_listing = None
            graph_failed = True
        if graph_failed:
            context.sources_checked.append(SOURCE_LABELS["graph"])
            report.done("graph", started, "error", detail="could not be checked this turn")
            context.gaps.append(
                "the live OneDrive folder could not be checked this turn -- this is "
                "not a confirmed absence; documents may still exist"
            )
        elif searched_but_no_match:
            context.sources_checked.append(SOURCE_LABELS["graph"])
            report.done("graph", started, "empty", detail="no folder matched that name")
            context.gaps.append(
                "no live matter folder matched that name. the client may be "
                "recorded under a different spelling, or may have no folder yet"
            )
        elif context.graph_listing is None and not context.matter_id:
            report.done("graph", started, "declined", detail="no client folder to list")
            context.gaps.append(
                "the live OneDrive folder was not checked because this question did "
                "not identify a client"
            )
        elif context.graph_listing is None:
            context.sources_checked.append(SOURCE_LABELS["graph"])
            report.done("graph", started, "empty")
            context.gaps.append("the live OneDrive folder listing returned nothing")
        else:
            context.sources_checked.append(SOURCE_LABELS["graph"])
            children = context.graph_listing.get("value") or []
            report.done("graph", started, "hit", count=len(children))
    else:
        report.emit(
            RetrievalStep("graph", STEP_VERBS["graph"], "skipped", detail="not needed")
        )

    if not context.client_name:
        report.emit(
            RetrievalStep("mail", STEP_VERBS["mail"], "declined", detail="no client to search for")
        )
        context.gaps.append(
            "the mailbox was not searched because this question did not identify a client"
        )
    else:
        context.sources_checked.append(SOURCE_LABELS["mail"])
        started = report.start("mail")
        scope = context.client_name
        try:
            context.mail_hits = engine.mail_search(
                scope, top=5, address=context.client_email
            )
            if hard_scope:
                context.mail_hits, dropped = _mail_of_anchored_matter(context.mail_hits, context)
                if dropped:
                    context.gaps.append(
                        f"{dropped} mailbox match(es) for the client's name were not used, because they were neither "
                        "to or from the client's recorded address nor carried the matter's case reference"
                    )
        except Exception:
            context.mail_hits = []
            report.done("mail", started, "error", detail="mailbox unavailable")
            context.gaps.append(
                "the mailbox could not be searched this turn -- this is not a confirmed "
                "absence; correspondence may still exist"
            )
        else:
            report.done(
                "mail", started, "hit" if context.mail_hits else "empty",
                count=len(context.mail_hits),
            )
            if not context.mail_hits:
                context.gaps.append("no matching messages found in the mailbox")

    context.carried_over = bool(
        context.carried_client_name and not context.sql_hits and not context.matched_folder_name
    )

    _flag_stale_correspondence(context)
    context.person_aliases = _person_aliases_for(context.sql_hits)

    return context
