#!/usr/bin/env python3

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

TOOLS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LONDON = ZoneInfo("Europe/London")
SOURCE = "nudge"
BY = "Nudge engine"
RULES_PATH = REPO_ROOT / "runtime-data" / "nudge-rules.json"
REPORT_NAME = "nudges.json"
SCHEMA = "caseforge.nudges.v1"
KINDS = ("statement_reply", "envelope", "court_reply", "statement_first", "final_hearing_bundle", "draft_unsent", "after_hearing")
HEARING_RULE_KIND = "final_hearing_bundle"
CHASE_DOCS = ("client_docs", "witness_statement")
HEARING_LOOKAHEAD_DAYS = 21


@dataclasses.dataclass(frozen=True)
class Rule:
    id: str
    kind: str
    working_days: int
    label: str
    detail: str = ""
    closes_when: str = ""
    chase_subject: str = ""
    chase_body: str = ""
    title_keywords: tuple[str, ...] = ()
    calendar_days: int = 0
    draft_chaser: str = ""
    no_new_hearing: bool = False
    chase_variants: tuple[tuple[str, str, str], ...] = ()
    closed_note: str = ""


@dataclasses.dataclass(frozen=True)
class Waiting:

    rule_id: str
    matter_id: int
    anchor: str
    since: dt.date
    threshold_days: int = 0
    court: str = ""


def ref_of(waiting: Waiting) -> str:
    return f"{waiting.rule_id}|{waiting.matter_id}|{waiting.anchor}"


def _expand(text: str) -> str:
    from onboarding.pipeline import expand_steps

    return expand_steps(text)


def _firm_name() -> str:
    try:
        import firm_profile

        return firm_profile.load_profile().firm_name
    except Exception:
        return "[firm name]"


def load_rules(path: Path = RULES_PATH) -> tuple[list[Rule], dict[str, Any]]:
    cfg = json.loads(path.read_text(encoding="utf-8").replace("[firm name]", json.dumps(_firm_name())[1:-1]))
    rules = [
        Rule(
            id=str(r["id"]), kind=str(r["kind"]), working_days=int(r["working_days"]), label=str(r["label"]),
            detail=_expand(str(r.get("detail", ""))), closes_when=_expand(str(r.get("closes_when", ""))),
            chase_subject=str(r.get("chase_subject", "")), chase_body=str(r.get("chase_body", "")),
            title_keywords=tuple(str(k).lower() for k in r.get("title_keywords", [])),
            calendar_days=int(r.get("calendar_days", 0)), draft_chaser=str(r.get("draft_chaser", "")),
            no_new_hearing=bool(r.get("no_new_hearing", False)),
            chase_variants=tuple(
                (doc, str(r[f"chase_subject_{doc}"]), str(r.get(f"chase_body_{doc}", "")))
                for doc in CHASE_DOCS if f"chase_subject_{doc}" in r
            ),
            closed_note=str(r.get("closed_note", "")),
        )
        for r in cfg["rules"]
    ]
    for rule in rules:
        if rule.kind not in KINDS:
            raise ValueError(f"rule {rule.id}: unknown kind {rule.kind!r}")
    return rules, cfg


def _instant(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        moment = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def london_date(value: Any) -> dt.date | None:
    moment = _instant(value)
    return moment.astimezone(LONDON).date() if moment else None




@dataclasses.dataclass
class Plan:
    create: list[tuple[Waiting, Rule, int]]
    close: list[dict[str, Any]]
    waiting: Counter
    due: Counter
    over_cap: int


def build_plan(
    waiting: list[Waiting],
    open_nudges: list[dict[str, Any]],
    known_refs: set[str],
    rules: list[Rule],
    today: dt.date,
    sources_ok: dict[str, bool],
    *,
    lookback_days: int,
    max_new: int,
) -> Plan:
    from vergil.hearings import working_days_between

    by_id = {r.id: r for r in rules}
    current = {ref_of(w) for w in waiting}
    due: list[tuple[Waiting, Rule, int]] = []
    for w in waiting:
        rule = by_id.get(w.rule_id)
        if rule is None or ref_of(w) in known_refs:
            continue
        if rule.kind == HEARING_RULE_KIND:
            days = working_days_between(today, w.since)
            if 1 <= days <= rule.working_days:
                due.append((w, rule, days))
            continue
        if w.threshold_days:
            days = working_days_between(w.since, today)
            if days >= w.threshold_days and (today - w.since).days <= lookback_days:
                due.append((w, rule, days))
            continue
        days = (today - w.since).days if rule.calendar_days else working_days_between(w.since, today)
        if days >= (rule.calendar_days or rule.working_days) and (today - w.since).days <= lookback_days:
            due.append((w, rule, days))
    due.sort(key=lambda item: (item[0].since, item[0].matter_id))
    create = due[: max(0, max_new)]
    close = []
    for todo in open_nudges:
        rule = by_id.get(str(todo.get("source_ref", "")).split("|", 1)[0])
        if rule is not None and sources_ok.get(rule.kind) and todo.get("source_ref") not in current:
            close.append(todo)
    return Plan(
        create=create,
        close=close,
        waiting=Counter(w.rule_id for w in waiting),
        due=Counter(rule.id for _, rule, _ in due),
        over_cap=len(due) - len(create),
    )


def is_working_day(day: dt.date) -> bool:
    from vergil.hearings import working_days_between

    return working_days_between(day - dt.timedelta(days=1), day) == 1


def post_by(hearing: dt.date, today: dt.date) -> dt.date:
    day = hearing - dt.timedelta(days=1)
    while not is_working_day(day):
        day -= dt.timedelta(days=1)
    return max(day, today)


def bundle_todo_content(waiting: Waiting, rule: Rule, days: int, today: dt.date) -> dict[str, str]:
    last = post_by(waiting.since, today)
    notes = (
        f"A final hearing is on {waiting.since:%d/%m/%Y}, {days} working day{'s' if days != 1 else ''} away. "
        "Print 2 copies of the bundle and post them for next-day delivery. "
        f"The last day to post them is {last:%d/%m/%Y}. Nothing is printed or sent by this to-do.\n"
        + (f"{rule.detail}\n" if rule.detail else "")
        + (f"This to-do closes itself when {rule.closes_when}.\n" if rule.closes_when else "")
    )
    return {"title": f"Print 2 copies of the bundle and post next-day delivery (final hearing {waiting.since:%d/%m/%Y})", "notes": notes}


def todo_content(waiting: Waiting, rule: Rule, days: int, today: dt.date | None = None) -> dict[str, str]:
    if rule.kind == HEARING_RULE_KIND:
        return bundle_todo_content(waiting, rule, days, today or dt.datetime.now(LONDON).date())
    chases = bool(rule.chase_body or rule.chase_subject or rule.draft_chaser)
    if rule.kind == "draft_unsent":
        step = waiting.anchor.split(":", 1)[0].replace("_", " ")
        return {
            "title": f"Waiting on us: send the {step} draft",
            "notes": f"Case flow drafted the {step} email on {waiting.since:%d/%m/%Y} and it has not been sent. It is in Drafts, marked AI DRAFTED. "
            "Review it and send it; nothing goes out until you do. This to-do closes itself when the email is sent.\n",
        }
    if waiting.threshold_days:
        unit, after = "working days", waiting.threshold_days
    else:
        unit, after = ("days" if rule.calendar_days else "working days"), rule.calendar_days or rule.working_days
    notes = (
        f"{rule.label[:1].upper()}{rule.label[1:]}. Waiting since {waiting.since:%d/%m/%Y}: {days} {unit} "
        f"({'this chases' if chases else 'this is flagged'} after {after}).\n"
        + (f"{waiting.court} is a slow court: it rarely answers without a nudge, so it is chased after {after} working days.\n" if waiting.court else "")
        + (f"{rule.detail}\n" if rule.detail else "")
        + (f"This to-do closes itself when {rule.closes_when}.\n" if rule.closes_when else "")
        + (
            "\nSuggested chase email, a draft for you to edit. Nothing is sent.\n"
            f"Subject: {rule.chase_subject}\n\n{rule.chase_body}"
            if rule.chase_body or rule.chase_subject else ""
        )
    )
    return {"title": f"Chase: {rule.label}" if chases else f"Overdue: {rule.label}", "notes": notes.rstrip() + "\n" if not chases else notes}


_SIGN_OFF_RE = re.compile(r"\s*\n(?:kind regards|best regards|regards|yours sincerely|yours faithfully|best wishes)\b[\s\S]*$", re.IGNORECASE)
_BRACKET_RE = re.compile(r"\[[^\]\n]*\]")


def chase_text(rule: Rule, first_name: str, since: dt.date, doc: str = "") -> tuple[str, str]:
    subject_raw, body_raw = rule.chase_subject, rule.chase_body
    for variant_doc, variant_subject, variant_body in rule.chase_variants:
        if variant_doc == doc:
            subject_raw, body_raw = variant_subject, variant_body
    if not (subject_raw and body_raw):
        raise ValueError(f"rule {rule.id} has no chase email")
    name = " ".join(str(first_name or "").split())
    if not name:
        raise ValueError("the client's first name is not on record")
    day = f"{since.day} {since:%B %Y}"
    body = _SIGN_OFF_RE.sub("", body_raw).replace("[first name]", name).replace("[date]", day)
    subject = subject_raw.replace("[first name]", name).replace("[date]", day)
    if _BRACKET_RE.search(subject) or _BRACKET_RE.search(body):
        raise ValueError("a placeholder was left in the chase email")
    return subject, body.rstrip()




def statement_first_waiting(conn: Any, rule: Rule) -> list[Waiting]:
    opened: dict[str, dt.datetime] = {}
    for matter_id, created in conn.execute(
        "SELECT matter_id, created_utc FROM pipeline_events WHERE step IN ('fetch', 'folder', 'record') "
        "AND status IN ('ok', 'outside') ORDER BY created_utc"
    ).fetchall():
        moment = _instant(created)
        if moment and str(matter_id).isdigit():
            opened.setdefault(str(matter_id), moment)
    have = {
        str(r[0])
        for r in conn.execute("SELECT matter_id FROM pipeline_events WHERE step = 'email' AND status IN ('ok', 'outside')").fetchall()
    } | {str(r[0]) for r in conn.execute("SELECT matter_id FROM statement_replies").fetchall()}
    out = []
    for matter_id, moment in opened.items():
        if matter_id in have:
            continue
        day = moment.astimezone(LONDON).date()
        out.append(Waiting(rule.id, int(matter_id), f"opened:{day.isoformat()}", day))
    return out


def draft_unsent_waiting(conn: Any, rule: Rule) -> list[Waiting]:
    from onboarding.pipeline import DRAFT_STEPS, REPEAT_STEPS

    steps = [s for s in DRAFT_STEPS if s not in REPEAT_STEPS]
    marks = ",".join("?" for _ in steps)
    done = {(str(m), str(st)) for m, st in conn.execute(f"SELECT matter_id, step FROM pipeline_step_done WHERE step IN ({marks})", steps).fetchall()}
    newest: dict[tuple[str, str], tuple[dt.date, str]] = {}
    for event_id, matter_id, step, status, created in conn.execute(
        f"SELECT event_id, matter_id, step, status, created_utc FROM pipeline_events WHERE step = 'reset' OR (step IN ({marks}) AND status = 'ok') ORDER BY created_utc",
        steps,
    ).fetchall():
        if step == "reset":
            for key in [k for k in newest if k[0] == str(matter_id)]:
                del newest[key]
            continue
        day = london_date(created)
        if day and str(matter_id).isdigit():
            newest[(str(matter_id), str(step))] = (day, str(event_id))
    return [
        Waiting(rule.id, int(m), f"{step}:{event_id}", day)
        for (m, step), (day, event_id) in newest.items()
        if (m, step) not in done
    ]


def final_hearing_waiting(rows: list[dict[str, Any]], rule: Rule, today: dt.date, skipped: Counter | None = None) -> list[Waiting]:
    out = []
    for row in rows:
        if not row.get("is_final") or str(row.get("status") or "") != "scheduled":
            continue
        if str(row.get("review_state") or "ok") in ("needs_review", "dismissed"):
            continue
        try:
            day = dt.date.fromisoformat(str(row.get("hearing_date") or "")[:10])
        except ValueError:
            continue
        if day <= today:
            continue
        matter = row.get("matter_id")
        if matter is None or not str(matter).isdigit():
            if skipped is not None:
                skipped["hearing_no_matter"] += 1
            continue
        out.append(Waiting(rule.id, int(matter), f"hearing:{row.get('hearing_id')}", day))
    return out


def hearings_around_today(today: dt.date) -> list[dict[str, Any]]:
    from hearing_calendar import hearing_store

    return hearing_store.list_hearings((today - dt.timedelta(days=60)).isoformat(), (today + dt.timedelta(days=730)).isoformat())


def hearings_from_store(today: dt.date) -> list[dict[str, Any]]:
    from hearing_calendar import hearing_store

    return hearing_store.list_hearings(today.isoformat(), (today + dt.timedelta(days=HEARING_LOOKAHEAD_DAYS)).isoformat())


def statement_waiting(conn: Any, rule: Rule) -> list[Waiting]:
    latest: dict[str, tuple[str, dt.datetime]] = {}
    for event_id, matter_id, created in conn.execute(
        "SELECT event_id, matter_id, created_utc FROM pipeline_events WHERE step = 'email' AND status = 'ok' ORDER BY created_utc"
    ).fetchall():
        moment = _instant(created)
        if moment and str(matter_id).isdigit():
            latest[str(matter_id)] = (str(event_id), moment)
    replies = {str(m): _instant(r) for m, r in conn.execute("SELECT matter_id, recorded_utc FROM statement_replies").fetchall()}
    out = []
    for matter_id, (event_id, drafted) in latest.items():
        reply = replies.get(matter_id)
        if reply is not None and reply >= drafted:
            continue
        out.append(Waiting(rule.id, int(matter_id), f"email:{event_id}", drafted.astimezone(LONDON).date()))
    return out


_ISO_DAY_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def court_replies(conn: Any) -> dict[str, list[dt.date]]:
    replies: dict[str, list[dt.date]] = {}
    for matter_id, received, created in conn.execute(
        "SELECT matter_id, received_utc, created_utc FROM pipeline_triggers WHERE kind = 'court_reply'"
    ).fetchall():
        day = london_date(received) or london_date(created)
        if day:
            replies.setdefault(str(matter_id), []).append(day)
    return replies


def after_hearing_waiting(conn: Any, rule: Rule, rows: list[dict[str, Any]], today: dt.date) -> list[Waiting]:
    by_matter: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        matter = row.get("matter_id")
        if matter is None or not str(matter).isdigit() or str(row.get("status") or "") != "scheduled":
            continue
        if str(row.get("review_state") or "ok") in ("needs_review", "dismissed"):
            continue
        by_matter.setdefault(str(matter), []).append(row)
    replies = court_replies(conn) if not rule.no_new_hearing else {}
    out = []
    for matter, hearings in by_matter.items():
        dated = []
        for row in hearings:
            try:
                dated.append((dt.date.fromisoformat(str(row.get("hearing_date") or "")[:10]), row))
            except ValueError:
                continue
        past = [item for item in dated if item[0] < today]
        if not past:
            continue
        day, last = max(past, key=lambda item: item[0])
        if rule.no_new_hearing:
            if last.get("is_final") or any(d >= today for d, _ in dated):
                continue
        elif any(r >= day for r in replies.get(matter, [])):
            continue
        out.append(Waiting(rule.id, int(matter), f"hearing:{last.get('hearing_id')}", day))
    return out


def court_reply_waiting(
    conn: Any,
    rule: Rule,
    *,
    slow_of: Callable[[int], dict[str, Any] | None] | None = None,
    details_known: Callable[[int], bool] | None = None,
) -> list[Waiting]:
    if slow_of is None or details_known is None:
        from onboarding.pipeline import portal_courts

        slow_of = slow_of or (lambda m: portal_courts.slow_court(portal_courts.recorded_court(str(m))))
        details_known = details_known or (lambda m: portal_courts.hearing_and_case_number_known(str(m)))
    replied_steps = {str(r[0]) for r in conn.execute("SELECT matter_id FROM pipeline_step_done WHERE step = 'court_reply'").fetchall()}
    replies = court_replies(conn)
    out = []
    for matter_id, view_json, checked in conn.execute(
        "SELECT matter_id, view_json, checked_utc FROM pipeline_step_done WHERE step = 'court_email'"
    ).fetchall():
        if not str(matter_id).isdigit() or str(matter_id) in replied_steps:
            continue
        try:
            view = json.loads(view_json)
        except ValueError:
            continue
        if view.get("status") != "done":
            continue
        found = _ISO_DAY_RE.search(str(view.get("summary") or ""))
        try:
            since = dt.date.fromisoformat(found.group(1)) if found else london_date(checked)
        except ValueError:
            since = london_date(checked)
        if since is None or any(day >= since for day in replies.get(str(matter_id), [])):
            continue
        slow = slow_of(int(matter_id))
        if slow:
            if details_known(int(matter_id)):
                continue
            out.append(Waiting(rule.id, int(matter_id), f"court_email:{since.isoformat()}", since, int(slow["nudge_working_days"]), str(slow["name"])))
            continue
        out.append(Waiting(rule.id, int(matter_id), f"court_email:{since.isoformat()}", since))
    return out


def envelope_waiting(
    envelopes: list[dict[str, Any]],
    rules: list[Rule],
    matter_of: Callable[[dict[str, Any]], int | None],
    skipped: Counter,
) -> list[Waiting]:
    envelope_rules = [r for r in rules if r.kind == "envelope"]
    out = []
    for env in envelopes:
        status = str(env.get("status") or "").upper()
        if status == "DRAFT":
            skipped["draft_never_sent"] += 1
            continue
        if status != "PENDING":
            continue
        recipients = env.get("recipients") or []
        if not any(r.get("sendStatus") == "SENT" and r.get("signingStatus") == "NOT_SIGNED" for r in recipients):
            skipped["not_sent"] += 1
            continue
        title = str(env.get("title") or "").lower()
        rule = next((r for r in envelope_rules if any(k in title for k in r.title_keywords)), None)
        if rule is None:
            skipped["other_kind"] += 1
            continue
        since = london_date(env.get("createdAt"))
        matter = matter_of(env)
        if matter is None or since is None:
            skipped["no_matter"] += 1
            continue
        out.append(Waiting(rule.id, matter, f"env:{env.get('id')}", since))
    return out


def make_matter_resolver(local_records: list[dict[str, Any]], email_lookup: Callable[[str], int | None]) -> Callable[[dict], int | None]:
    by_document = {str(r.get("document_id")): r.get("external_id") for r in local_records}

    def resolve(env: dict[str, Any]) -> int | None:
        for candidate in (env.get("externalId"), by_document.get(str(env.get("id")))):
            if str(candidate or "").strip().isdigit():
                return int(str(candidate).strip())
        found = {
            email_lookup(str(r.get("email")).strip().lower())
            for r in (env.get("recipients") or [])
            if r.get("email")
        } - {None}
        return found.pop() if len(found) == 1 else None

    return resolve


def fetch_envelopes() -> list[dict[str, Any]]:
    from agents import documenso_envelopes as de

    token = de.api_token()
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        body = de._api("GET", f"/api/v2/envelope?page={page}&perPage=100", token=token)
        out.extend(body.get("data") or [])
        if page >= int(body.get("totalPages") or 1):
            return out
        page += 1


def local_envelope_records() -> list[dict[str, Any]]:
    try:
        from agents import documenso_envelopes as de

        return de.load_state_strict()
    except Exception:
        return []


def email_lookup_from_clientdb(email: str) -> int | None:
    import clientdb_sql

    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT mp.matter_id FROM matter_parties mp JOIN matters m ON m.matter_id = mp.matter_id "
            "WHERE lower(mp.email_primary) = ? AND m.closed_at IS NULL",
            (email,),
        )
        rows = cursor.fetchall()
    return int(rows[0][0]) if len(rows) == 1 else None


class ClientTodoStore:

    def known_refs(self) -> set[str]:
        return {r["source_ref"] for r in self._rows("SELECT todo_id, source_ref FROM client_todos WHERE source = ?", (SOURCE,))}

    def open_nudges(self) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT todo_id, source_ref FROM client_todos WHERE source = ? AND done_utc IS NULL AND deleted_utc IS NULL",
            (SOURCE,),
        )

    def create(self, **fields: Any) -> dict[str, Any]:
        from todos import todo_store

        return todo_store.create(source=SOURCE, created_by=BY, **fields)

    def close(self, todo_id: str, note: str = "") -> None:
        from todos import todo_store

        if note:
            current = todo_store.get(todo_id, automatic=True) or {}
            todo_store.update(todo_id, {"notes": f"{note}\n\n{current.get('notes') or ''}".rstrip()}, by=BY)
        todo_store.complete(todo_id, True, by=BY)

    @staticmethod
    def _rows(sql: str, params: tuple) -> list[dict[str, Any]]:
        import clientdb_sql
        from todos import todo_store

        with clientdb_sql.get_connection() as conn:
            todo_store.ensure_tables(conn)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return [{"todo_id": r[0], "source_ref": r[1]} for r in cursor.fetchall()]




def _left_matters(conn: Any, waiting: list[Waiting]) -> set[str]:
    from onboarding.pipeline import board_sink

    return board_sink.left_ids_on(conn, [str(w.matter_id) for w in waiting])


def run(
    *,
    conn: Any,
    store: Any,
    fetch: Callable[[], list[dict[str, Any]]],
    local_records: list[dict[str, Any]],
    email_lookup: Callable[[str], int | None],
    now: dt.datetime,
    rules: list[Rule],
    cfg: dict[str, Any],
    dry_run: bool,
    max_new: int | None = None,
    hearings: Callable[[dt.date], list[dict[str, Any]]] = hearings_from_store,
    drafter: Callable[[Waiting, Rule], str | tuple[str, str]] | None = None,
    all_hearings: Callable[[dt.date], list[dict[str, Any]]] = hearings_around_today,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    today = now.astimezone(LONDON).date()
    skipped: Counter = Counter()
    ok = {"statement_reply": True, "envelope": True, "court_reply": True, "statement_first": True, "draft_unsent": True, "after_hearing": True, HEARING_RULE_KIND: True}
    waiting: list[Waiting] = []

    for rule in (r for r in rules if r.kind == "statement_reply"):
        try:
            waiting += statement_waiting(conn, rule)
        except Exception:
            ok["statement_reply"] = False
    for rule in (r for r in rules if r.kind == "statement_first"):
        try:
            waiting += statement_first_waiting(conn, rule)
        except Exception:
            ok["statement_first"] = False
    for rule in (r for r in rules if r.kind == HEARING_RULE_KIND):
        try:
            waiting += final_hearing_waiting(hearings(today), rule, today, skipped)
        except Exception:
            ok[HEARING_RULE_KIND] = False
    for rule in (r for r in rules if r.kind == "after_hearing"):
        try:
            waiting += after_hearing_waiting(conn, rule, all_hearings(today), today)
        except Exception:
            ok["after_hearing"] = False
    for rule in (r for r in rules if r.kind == "draft_unsent"):
        try:
            waiting += draft_unsent_waiting(conn, rule)
        except Exception:
            ok["draft_unsent"] = False
    for rule in (r for r in rules if r.kind == "court_reply"):
        try:
            waiting += court_reply_waiting(conn, rule)
        except Exception:
            ok["court_reply"] = False
    try:
        waiting += envelope_waiting(fetch(), rules, make_matter_resolver(local_records, email_lookup), skipped)
    except Exception:
        ok["envelope"] = False

    disabled = {r.get("id") for r in cfg.get("rules", []) if r.get("enabled") is False}
    if disabled:
        waiting = [w for w in waiting if w.rule_id not in disabled]
    excluded = {int(m) for m in cfg.get("exclude_matters", [])}
    if excluded:
        skipped["excluded"] = sum(1 for w in waiting if w.matter_id in excluded)
        waiting = [w for w in waiting if w.matter_id not in excluded]
    left = _left_matters(conn, waiting)
    if left:
        skipped["client_left"] = sum(1 for w in waiting if str(w.matter_id) in left)
        waiting = [w for w in waiting if str(w.matter_id) not in left]
    plan = build_plan(
        waiting, store.open_nudges(), store.known_refs(), rules, today, ok,
        lookback_days=int(cfg.get("lookback_days", 45)),
        max_new=int(cfg.get("max_new_per_run", 10) if max_new is None else max_new),
    )
    created: Counter = Counter()
    failed = 0
    detail: list[dict[str, Any]] = []
    for w, rule, days in plan.create:
        deadline = rule.kind == HEARING_RULE_KIND
        due_day = post_by(w.since, today) if deadline else today
        detail.append({"action": "create", "rule": rule.id, "matter_id": w.matter_id, "working_days": days})
        if dry_run:
            created[rule.id] += 1
            continue
        try:
            content = todo_content(w, rule, days, today)
            if rule.draft_chaser:
                made = (drafter or draft_court_chaser)(w, rule)
                summary, link = made if isinstance(made, tuple) else (made, "")
                content["notes"] += "\n" + summary
                if link.startswith("https://"):
                    content["draft_link"] = link
            store.create(
                matter_id=w.matter_id, due=due_day.isoformat(), source_ref=ref_of(w),
                **content,
            )
            created[rule.id] += 1
        except Exception:
            failed += 1
    closed = 0
    for todo in plan.close:
        detail.append({"action": "close", "source_ref": todo["source_ref"].split("|")[0] + "|" + todo["source_ref"].split("|")[1]})
        if dry_run:
            closed += 1
            continue
        try:
            rule = next((r for r in rules if r.id == str(todo["source_ref"]).split("|", 1)[0]), None)
            note = rule.closed_note if rule is not None and rule.id in disabled else ""
            store.close(todo["todo_id"], note=note) if note else store.close(todo["todo_id"])
            closed += 1
        except Exception:
            failed += 1
    open_after = Counter(str(t["source_ref"]).split("|", 1)[0] for t in store.open_nudges())
    if dry_run:
        for item in plan.create:
            open_after[item[1].id] += 1
        for todo in plan.close:
            open_after[str(todo["source_ref"]).split("|", 1)[0]] -= 1
    report = {
        "schema": SCHEMA,
        "available": True,
        "computed_at": now.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "dry_run": dry_run,
        "sources_ok": ok,
        "waiting": dict(plan.waiting),
        "due": dict(plan.due),
        "created": dict(created),
        "closed": closed,
        "failed": failed,
        "over_cap": plan.over_cap,
        "open": {k: v for k, v in open_after.items() if v > 0},
        "skipped": dict(skipped),
    }
    return report, detail


def draft_court_chaser(waiting: Waiting, rule: Rule) -> tuple[str, str]:
    try:
        from onboarding.pipeline import court_chaser, load_context

        if rule.kind == "court_reply":
            from todos import court_chase_auto

            if court_chase_auto.enabled(load_rules()[1]):
                return "No chaser is drafted here: the automatic court chaser follows after seven working days if the court has not replied.", ""
        ctx = load_context(str(waiting.matter_id))
        if rule.kind != "after_hearing":
            out = court_chaser.draft(ctx, rule.draft_chaser, waiting.since)
            return out["summary"], str(out.get("web_link") or "")
        from onboarding.pipeline import court_common as cc, step_court_email

        filed, _how = step_court_email.gone_to_court(ctx)
        if not filed:
            return "No chaser could be drafted: the day the application was filed is not on record.", ""
        out = court_chaser.draft(ctx, rule.draft_chaser, dt.date.fromisoformat(filed), hearing=cc.long_day(waiting.since))
        return out["summary"], str(out.get("web_link") or "")
    except Exception as exc:
        return f"No chaser could be drafted ({type(exc).__name__}). Use the suggested text above.", ""


def unsigned_reminders(envelopes: list[dict[str, Any]] | None, local_records: list[dict[str, Any]], cfg: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    if envelopes is None:
        return {"available": False}
    try:
        from todos import client_nudge

        return client_nudge.auto_remind(
            envelopes=envelopes, matter_of=make_matter_resolver(local_records, email_lookup_from_clientdb), cfg=cfg,
            now=dt.datetime.now(dt.timezone.utc), dry_run=dry_run,
        )
    except Exception as exc:
        return {"available": False, "error": type(exc).__name__}


def court_chasers(rules: list[Rule], cfg: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    try:
        import ops_db
        from todos import court_chase_auto

        with ops_db.connect() as conn:
            return court_chase_auto.run(conn, cfg, rules, now=dt.datetime.now(dt.timezone.utc), dry_run=dry_run)
    except Exception as exc:
        return {"error": type(exc).__name__}


def _report_path(output: str) -> Path:
    if output:
        return Path(output)
    return Path(os.environ.get("CASEFORGE_TELEMETRY_ROOT") or REPO_ROOT / "telemetry") / REPORT_NAME


def main(argv: list[str] | None = None) -> int:
    import ops_db

    parser = argparse.ArgumentParser(description="Make and close chase to-dos for matters waiting on someone else")
    parser.add_argument("--rules", default=str(RULES_PATH))
    parser.add_argument("--output", default="", help="Report path (default: telemetry root / nudges.json)")
    parser.add_argument("--max-new", type=int, default=None, help="Override max_new_per_run")
    parser.add_argument("--dry-run", action="store_true", help="Print what it would do; write nothing")
    args = parser.parse_args(argv)

    rules, cfg = load_rules(Path(args.rules))
    try:
        envelopes: list[dict[str, Any]] | None = fetch_envelopes()
    except Exception:
        envelopes = None

    def fetch() -> list[dict[str, Any]]:
        if envelopes is None:
            raise RuntimeError("Documenso could not be read")
        return envelopes

    local_records = local_envelope_records()
    with ops_db.connect() as conn:
        report, detail = run(
            conn=conn,
            store=ClientTodoStore(),
            fetch=fetch,
            local_records=local_records,
            email_lookup=email_lookup_from_clientdb,
            now=dt.datetime.now(dt.timezone.utc),
            rules=rules,
            cfg=cfg,
            dry_run=args.dry_run,
            max_new=args.max_new,
        )
    report["unsigned_reminders"] = unsigned_reminders(envelopes, local_records, cfg, dry_run=args.dry_run)
    report["court_chaser_auto"] = court_chasers(rules, cfg, dry_run=args.dry_run)
    if args.dry_run:
        print(json.dumps({"report": report, "would": detail}, indent=2))
        return 0
    path = _report_path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(
        f"nudges: created {sum(report['created'].values())}, closed {report['closed']}, failed {report['failed']}, "
        f"open {sum(report['open'].values())}, over cap {report['over_cap']}, sources ok {report['sources_ok']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
