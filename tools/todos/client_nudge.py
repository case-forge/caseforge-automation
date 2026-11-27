#!/usr/bin/env python3

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db
from todos import nudges

SOURCE = "client-nudge"
STEP = "nudge"
REPEAT_HOURS = 4
SIGN_OFF = "Kind regards,"
ENVELOPE_RULE = "signing_loa_ws"
STATEMENT_RULE = "statement_unanswered"
CHASE_CLASS = "statement-reply-chase"


class NudgeRefused(Exception):

    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


def _rules() -> dict[str, nudges.Rule]:
    rules, _cfg = nudges.load_rules()
    return {r.id: r for r in rules if r.id in (ENVELOPE_RULE, STATEMENT_RULE)}


DOC_KEYWORDS = (("witness_statement", ("witness", "statement")), ("client_docs", ("authority", "loa")))


def doc_of(title: str) -> str:
    low = str(title or "").lower()
    return next((doc for doc, words in DOC_KEYWORDS if any(w in low for w in words)), "")


def waiting_for(
    matter_ids: list[str],
    *,
    db_path: Any = None,
    records: list[dict[str, Any]] | None = None,
    today: dt.date | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    from vergil.hearings import working_days_between

    wanted = {str(m) for m in matter_ids}
    if not wanted:
        return {}
    rules = _rules()
    today = today or dt.datetime.now(nudges.LONDON).date()
    newest: dict[tuple[str, str], tuple[str, str, dt.date | None]] = {}
    for row in nudges.local_envelope_records() if records is None else records:
        matter = str(row.get("external_id") or "").strip()
        doc = doc_of(str(row.get("title") or ""))
        if matter not in wanted or not doc:
            continue
        created = str(row.get("created_utc") or "")
        if (matter, doc) not in newest or created >= newest[(matter, doc)][0]:
            newest[(matter, doc)] = (created, str(row.get("status") or "").upper(), nudges.london_date(created))
    out: dict[str, dict[str, tuple[str, dt.date]]] = {}
    for (matter, doc), (_created, status, since) in newest.items():
        if status == "PENDING" and since is not None and ENVELOPE_RULE in rules:
            out.setdefault(matter, {})[doc] = (ENVELOPE_RULE, since)
    statement_rule = rules.get(STATEMENT_RULE)
    if statement_rule is not None:
        with ops_db.connect(db_path) as conn:
            rows = nudges.statement_waiting(conn, statement_rule)
        for w in rows:
            matter = str(w.matter_id)
            signed = newest.get((matter, "witness_statement"), ("", "", None))[1] == "COMPLETED"
            if matter in wanted and "witness_statement" not in out.get(matter, {}) and not signed:
                out.setdefault(matter, {})["witness_statement"] = (STATEMENT_RULE, w.since)
    from onboarding.pipeline import board_sink

    gone = board_sink.left_ids(list(out), db_path=db_path)
    return {
        m: {
            doc: {"rule_id": rule_id, "since_date": since.isoformat(), "working_days": working_days_between(since, today)}
            for doc, (rule_id, since) in docs.items()
        }
        for m, docs in out.items()
        if m not in gone
    }


def waiting(matter_id: str, *, db_path: Any = None, records: list[dict[str, Any]] | None = None, today: dt.date | None = None) -> list[dict[str, Any]]:
    found = waiting_for([str(matter_id)], db_path=db_path, records=records, today=today).get(str(matter_id), {})
    return [
        {"doc": doc, "rule_id": v["rule_id"], "since_date": v["since_date"], "working_days_waiting": v["working_days"]}
        for doc, v in sorted(found.items())
    ]


def _earlier(matter_id: str, doc: str, now: dt.datetime, db_path: Any) -> tuple[str, str] | None:
    cutoff = (now - dt.timedelta(hours=REPEAT_HOURS)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with ops_db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT rule_id, draft_id FROM pipeline_client_nudges WHERE matter_id = ? AND doc = ? AND nudged_utc >= ? "
            "ORDER BY nudged_utc DESC, nudge_id DESC LIMIT 1",
            (matter_id, doc, cutoff),
        ).fetchone()
    return (str(row[0]), str(row[1])) if row else None


def _html(body: str) -> str:
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    return "<html><body>" + "".join(f"<div>{html.escape(p).replace(chr(10), '<br>')}</div><br>" for p in paragraphs) + "</body></html>"


def statement_email_sent(matter_id: str, *, db_path: Any = None) -> bool:
    from onboarding.pipeline import sent_watch

    with ops_db.connect(db_path) as conn:
        sent_watch.ensure_table(conn)
        row = conn.execute(
            "SELECT 1 FROM pipeline_sent_watch WHERE matter_id = ? AND step IN ('email', 'amend') AND status = 'sent' LIMIT 1", (str(matter_id),)
        ).fetchone()
    return row is not None


def nudge(matter_id: str, doc: str, by: str, *, db_path: Any = None, now: dt.datetime | None = None, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from onboarding import pipeline
    from onboarding.pipeline import court_common as cc, folder_guard, send_gate

    mid = str(matter_id or "").strip()
    who = " ".join(str(by or "").split())
    if not mid.isdigit():
        raise NudgeRefused("matter_id must be a matter number", 422)
    if doc not in nudges.CHASE_DOCS:
        raise NudgeRefused("doc must be client_docs or witness_statement", 422)
    if not who:
        raise NudgeRefused("who pressed Nudge is not known", 422)
    now = now or dt.datetime.now(dt.timezone.utc)
    found = next((w for w in waiting(mid, db_path=db_path, records=records, today=now.astimezone(nudges.LONDON).date()) if w["doc"] == doc), None)
    if found is None:
        raise NudgeRefused("Nothing is waiting on this client for that document, so there is nothing to nudge.")
    rule_id = found["rule_id"]
    earlier = _earlier(mid, doc, now, db_path)
    if earlier is not None:
        return {"matter_id": mid, "doc": doc, "rule_id": earlier[0], "draft_id": earlier[1], "repeat": True}
    try:
        ctx = pipeline.load_context(mid)
    except pipeline.PipelineError as exc:
        raise NudgeRefused(str(exc), 404) from exc
    email = (ctx.email or "").strip()
    if not email or "@" not in email:
        raise NudgeRefused("The client has no email address on record, so no reminder was made.", 422)
    try:
        folder_guard.stop_if_billed(mid, ctx.folder_path)
        folder_guard.stop_if_retired(ctx.folder_path)
    except folder_guard.FolderStop as exc:
        raise NudgeRefused(str(exc)) from exc
    since = dt.date.fromisoformat(found["since_date"])
    first = (ctx.client_name.split() or [""])[0].title()
    try:
        subject, text = nudges.chase_text(_rules()[rule_id], first, since, doc)
    except ValueError as exc:
        raise NudgeRefused(f"No reminder was made: {exc}.", 422) from exc
    mail_class = CHASE_CLASS if rule_id == STATEMENT_RULE else REMINDER_CLASS
    wanted = send_gate.enabled(mid, db_path=db_path)
    held_back = wanted and rule_id == STATEMENT_RULE and not statement_email_sent(mid, db_path=db_path)
    auto = wanted and not held_back
    try:
        made = cc.make_draft(
            ctx, subject=subject, html_body=_html(text + "\n\n" + SIGN_OFF), to=[email], files=[], source=SOURCE,
            auto_send=auto, watch_step=STEP, watch_round=0, mail_class=mail_class,
        )
    except folder_guard.FolderStop as exc:
        raise NudgeRefused(str(exc)) from exc
    draft_id = str((made or {}).get("id") or "")
    link = str((made or {}).get("webLink") or "")
    if auto and draft_id:
        send_gate.arm_if_enabled(mid, STEP, draft_id, mail_class, [email], db_path=db_path)
    stamp = now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with ops_db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO pipeline_client_nudges (matter_id, rule_id, doc, nudged_by, nudged_utc, draft_id) VALUES (?, ?, ?, ?, ?, ?)",
            (mid, rule_id, doc, who[:80], stamp, draft_id),
        )
    label = "the client documents" if doc == "client_docs" else "the witness statement"
    pipeline.log_event(
        mid, STEP, "ok", f"Nudge: {who} made the reminder email for the client about {label}" + (", armed to send itself (Case flow is on Auto)." if auto else " (draft: the statement email is not recorded as sent, so check it reached the client first)." if held_back else " (draft)."), who, "manual",
        db_path=db_path, instance=doc, links=[{"label": "Open the draft in Outlook", "url": link}] if link else None,
    )
    return {"matter_id": mid, "doc": doc, "rule_id": rule_id, "draft_id": draft_id, "repeat": False, "armed": auto}



REMINDER_CLASS = "unsigned-signature-reminder"
REMINDER_SOURCE = "unsigned-reminder"
REMINDER_BY = "Nudge engine"
ALERT_STAGE = "alert"
GO_LIVE_STAGE = "go_live"
GO_LIVE_KEY = "*"
DOC_WORDS = {"client_docs": "client documents", "witness_statement": "witness statement"}


@dataclasses.dataclass(frozen=True)
class Unsigned:

    envelope_id: str
    matter_id: str
    doc: str
    created: dt.datetime


@dataclasses.dataclass(frozen=True)
class ReminderSettings:
    enabled: bool
    go_live: str
    stage_days: tuple[int, ...]
    alert_after: int
    max_late: int
    mail_class: str
    texts: dict[str, tuple[tuple[str, str], ...]]


def reminder_settings(cfg: dict[str, Any]) -> ReminderSettings:
    block = cfg.get("unsigned_reminders") or {}
    stage_days = tuple(int(d) for d in block.get("stage_days") or ())
    texts = {
        doc: tuple((str(t["subject"]), str(t["body"])) for t in items)
        for doc, items in (block.get("texts") or {}).items()
    }
    for doc, items in texts.items():
        if doc not in DOC_WORDS or len(items) != len(stage_days):
            raise ValueError(f"unsigned_reminders: {doc} needs one text per stage")
    if list(stage_days) != sorted(set(stage_days)) or any(d < 1 for d in stage_days):
        raise ValueError("unsigned_reminders: stage_days must be rising whole days")
    return ReminderSettings(
        enabled=bool(block.get("enabled")) and bool(stage_days), go_live=str(block.get("go_live") or "").strip(),
        stage_days=stage_days, alert_after=int(block.get("alert_after_days", 1)), max_late=int(block.get("max_late_days", 2)),
        mail_class=str(block.get("mail_class") or REMINDER_CLASS), texts=texts,
    )


def stage_name(days: int) -> str:
    return f"day{int(days)}"


def due_stage(stage_days: tuple[int, ...], days_since: int, max_late: int = 2) -> int | None:
    for days in reversed(stage_days):
        if days <= days_since <= days + max_late:
            return days
    return None


def amendment_requested(matter_id: str, db_path: Any = None) -> bool:
    try:
        from onboarding.pipeline import step_amend
        from vergil import statement_replies

        rows = step_amend.rounds(str(matter_id), db_path=db_path)
        if step_amend.open_round(rows) is not None:
            return True
        reply = statement_replies.get_reply(str(matter_id), db_path=db_path)
        if not reply or reply.get("state") != "amend":
            return False
        since = str(reply.get("recorded_utc") or "")
        return not any(str(r["prepared_utc"] or "") >= since for r in rows)
    except Exception:
        return True


def reminder_text(settings: ReminderSettings, doc: str, days: int, first_name: str, since: dt.date) -> tuple[str, str]:
    subject, body = settings.texts[doc][settings.stage_days.index(days)]
    name = " ".join(str(first_name or "").split())
    if not name:
        raise ValueError("the client's first name is not on record")
    day = f"{since.day} {since:%B %Y}"
    subject, body = subject.replace("[first name]", name).replace("[date]", day), body.replace("[first name]", name).replace("[date]", day)
    if nudges._BRACKET_RE.search(subject) or nudges._BRACKET_RE.search(body):
        raise ValueError("a placeholder was left in the reminder")
    return subject, body.rstrip()


def unsigned_envelopes(envelopes: list[dict[str, Any]], matter_of: Any) -> list[Unsigned]:
    newest: dict[tuple[str, str], tuple[dt.datetime, dict[str, Any]]] = {}
    for env in envelopes:
        doc = doc_of(str(env.get("title") or ""))
        created = nudges._instant(env.get("createdAt"))
        if not doc or created is None:
            continue
        matter = matter_of(env)
        if matter is None:
            continue
        key = (str(matter), doc)
        if key not in newest or created >= newest[key][0]:
            newest[key] = (created, env)
    out = []
    for (matter, doc), (created, env) in sorted(newest.items()):
        if str(env.get("status") or "").upper() != "PENDING":
            continue
        recipients = env.get("recipients") or []
        if not any(r.get("sendStatus") == "SENT" and r.get("signingStatus") == "NOT_SIGNED" for r in recipients):
            continue
        out.append(Unsigned(str(env.get("id") or ""), matter, doc, created))
    return [u for u in out if u.envelope_id]


def _utc_z(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def go_live_moment(conn: Any, settings: ReminderSettings, now: dt.datetime, *, record: bool) -> dt.datetime:
    if settings.go_live:
        day = dt.date.fromisoformat(settings.go_live)
        return dt.datetime(day.year, day.month, day.day, tzinfo=nudges.LONDON).astimezone(dt.timezone.utc)
    row = conn.execute(
        "SELECT made_utc FROM pipeline_unsigned_reminders WHERE envelope_id = ? AND stage = ?", (GO_LIVE_KEY, GO_LIVE_STAGE)
    ).fetchone()
    if row:
        return nudges._instant(row[0]) or now
    if record:
        conn.execute(
            "INSERT OR IGNORE INTO pipeline_unsigned_reminders (envelope_id, stage, made_utc, note) VALUES (?, ?, ?, ?)",
            (GO_LIVE_KEY, GO_LIVE_STAGE, _utc_z(now), "reminders began"),
        )
        conn.commit()
    return now


def first_seen(conn: Any, matter_id: str) -> dt.datetime | None:
    row = conn.execute("SELECT MIN(created_utc) FROM pipeline_events WHERE matter_id = ?", (str(matter_id),)).fetchone()
    return nudges._instant(row[0]) if row and row[0] else None


def _stage_row(conn: Any, envelope_id: str, stage: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT made_utc, draft_id, note FROM pipeline_unsigned_reminders WHERE envelope_id = ? AND stage = ?", (envelope_id, stage)
    ).fetchone()
    return {"made_utc": row[0], "draft_id": row[1], "note": row[2]} if row else None


def _claim(conn: Any, item: Unsigned, stage: str, now: dt.datetime) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO pipeline_unsigned_reminders (envelope_id, stage, matter_id, doc, made_utc) VALUES (?, ?, ?, ?, ?)",
        (item.envelope_id, stage, item.matter_id, item.doc, _utc_z(now)),
    )
    conn.commit()
    return cur.rowcount == 1


def _settle(conn: Any, item: Unsigned, stage: str, *, draft_id: str = "", note: str = "", release: bool = False) -> None:
    if release:
        conn.execute("DELETE FROM pipeline_unsigned_reminders WHERE envelope_id = ? AND stage = ?", (item.envelope_id, stage))
    else:
        conn.execute(
            "UPDATE pipeline_unsigned_reminders SET draft_id = ?, note = ? WHERE envelope_id = ? AND stage = ?",
            (draft_id, note[:300], item.envelope_id, stage),
        )
    conn.commit()


def make_reminder(item: Unsigned, days: int, since: dt.date, settings: ReminderSettings, *, db_path: Any = None) -> str:
    from onboarding import pipeline
    from onboarding.pipeline import court_common as cc, folder_guard, send_gate

    try:
        ctx = pipeline.load_context(item.matter_id)
    except pipeline.PipelineError as exc:
        raise NudgeRefused(str(exc), 404) from exc
    email = (ctx.email or "").strip()
    if not email or "@" not in email:
        raise NudgeRefused("the client has no email address on record", 422)
    try:
        folder_guard.stop_if_billed(item.matter_id, ctx.folder_path)
        folder_guard.stop_if_retired(ctx.folder_path)
    except folder_guard.FolderStop as exc:
        raise NudgeRefused(str(exc)) from exc
    try:
        subject, text = reminder_text(settings, item.doc, days, (ctx.client_name.split() or [""])[0].title(), since)
    except ValueError as exc:
        raise NudgeRefused(str(exc), 422) from exc
    auto = send_gate.enabled(item.matter_id, db_path=db_path)
    made = cc.make_draft(
        ctx, subject=subject, html_body=_html(text + "\n\n" + SIGN_OFF), to=[email], files=[], source=REMINDER_SOURCE,
        auto_send=auto, watch_step=STEP, watch_round=days, mail_class=settings.mail_class,
    )
    draft_id = str((made or {}).get("id") or "")
    link = str((made or {}).get("webLink") or "")
    if auto and draft_id:
        send_gate.arm_if_enabled(item.matter_id, STEP, draft_id, settings.mail_class, [email], db_path=db_path)
    how = "armed to send itself" if auto else "a draft for a person to send (Case flow is on Manual for this client)"
    try:
        pipeline.log_event(
            item.matter_id, STEP, "ok",
            f"Reminder: the {DOC_WORDS[item.doc]} sent on {since:%d/%m/%Y} is not signed after {days} working days, so a reminder email was made, {how}.",
            REMINDER_BY, "auto" if auto else "manual", db_path=db_path, instance=item.doc,
            links=[{"label": "Open the draft in Outlook", "url": link}] if link else None,
        )
    except Exception:
        pass
    return draft_id


def raise_alert(item: Unsigned, since: dt.date, settings: ReminderSettings) -> None:
    from vergil import attention_store

    who = ""
    try:
        from onboarding import pipeline

        who = pipeline.load_context(item.matter_id).client_name
    except Exception:
        pass
    words = DOC_WORDS[item.doc]
    attention_store.record(
        kind="update", message_key=f"unsigned:{item.envelope_id}"[:80], matter_id=item.matter_id, who=who,
        subject=f"Client has not signed the {words}",
        summary=f"The {words} sent on {since:%d/%m/%Y} is still not signed after {len(settings.stage_days)} reminder emails. Please contact the client.",
        importance="high", label="NOT SIGNED",
    )


def graph_sent_at() -> Any:
    from onboarding.pipeline import sent_evidence

    batch = sent_evidence.fetch_sent(since=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=45))

    def sent_at(item: Unsigned) -> dt.datetime | None:
        found = sent_evidence.sent_evidence_checked(item.matter_id, messages=batch)
        if not found.get("readable"):
            return None
        times = []
        for key in ("email", "amend"):
            row = (found.get("rows") or {}).get(key) or {}
            for field in ("sent", "latest"):
                moment = nudges._instant(row.get(field))
                if moment is not None and moment >= item.created - dt.timedelta(minutes=5):
                    times.append(moment)
        return min(times) if times else None

    return sent_at


def auto_remind(
    *,
    envelopes: list[dict[str, Any]],
    matter_of: Any,
    cfg: dict[str, Any],
    now: dt.datetime,
    sent_at: Any = None,
    maker: Any = None,
    alerter: Any = None,
    dry_run: bool = False,
    db_path: Any = None,
) -> dict[str, Any]:
    settings = reminder_settings(cfg)
    out: dict[str, Any] = {"enabled": settings.enabled, "unsigned": 0, "reminded": {}, "alerted": 0, "failed": 0, "skipped": {}}
    if not settings.enabled:
        return out
    maker = maker or (lambda item, days, since: make_reminder(item, days, since, settings, db_path=db_path))
    alerter = alerter or (lambda item, since: raise_alert(item, since, settings))
    today = now.astimezone(nudges.LONDON).date()
    items = unsigned_envelopes(envelopes, matter_of)
    out["unsigned"] = len(items)

    def skip(why: str) -> None:
        out["skipped"][why] = out["skipped"].get(why, 0) + 1

    with ops_db.connect(db_path) as conn:
        start = go_live_moment(conn, settings, now, record=not dry_run)
        reader = None
        from onboarding.pipeline import board_sink

        gone = board_sink.left_ids([i.matter_id for i in items], db_path=db_path)
        for item in items:
            if item.matter_id in gone:
                skip("client_left")
                continue
            seen = first_seen(conn, item.matter_id)
            if item.created < start or seen is None or seen < start:
                skip("before_go_live")
                continue
            reader = reader or sent_at or graph_sent_at()
            sent = reader(item)
            if sent is None:
                skip("email_not_sent")
                continue
            if amendment_requested(item.matter_id, db_path):
                skip("amendment_requested")
                continue
            since = sent.astimezone(nudges.LONDON).date()
            last = _stage_row(conn, item.envelope_id, stage_name(settings.stage_days[-1]))
            if last is not None:
                reminded_on = nudges.london_date(last["made_utc"]) or today
                if (today - reminded_on).days >= settings.alert_after and _stage_row(conn, item.envelope_id, ALERT_STAGE) is None:
                    if dry_run:
                        out["alerted"] += 1
                        continue
                    if _claim(conn, item, ALERT_STAGE, now):
                        try:
                            alerter(item, since)
                            _settle(conn, item, ALERT_STAGE, note="bell item raised")
                            out["alerted"] += 1
                        except Exception as exc:
                            _settle(conn, item, ALERT_STAGE, release=True)
                            out["failed"] += 1
                            skip(f"alert_{type(exc).__name__}")
                continue
            days = due_stage(settings.stage_days, (today - since).days, settings.max_late)
            if days is None:
                skip("no_stage_due")
                continue
            stage = stage_name(days)
            if _stage_row(conn, item.envelope_id, stage) is not None:
                skip("already_reminded")
                continue
            if dry_run:
                out["reminded"][stage] = out["reminded"].get(stage, 0) + 1
                continue
            if not _claim(conn, item, stage, now):
                skip("already_reminded")
                continue
            try:
                draft_id = maker(item, days, since)
            except NudgeRefused as exc:
                _settle(conn, item, stage, note=f"not made: {exc}")
                skip("refused")
                continue
            except Exception as exc:
                _settle(conn, item, stage, release=True)
                out["failed"] += 1
                skip(f"error_{type(exc).__name__}")
                continue
            _settle(conn, item, stage, draft_id=str(draft_id or ""), note="reminder made")
            out["reminded"][stage] = out["reminded"].get(stage, 0) + 1
    return out
