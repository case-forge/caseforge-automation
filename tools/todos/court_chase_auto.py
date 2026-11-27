#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db
from todos import nudges

GO_LIVE_ANCHOR = "go_live"
BY = "Nudge engine"
SUPERSEDED = "superseded"


def settings(cfg: dict[str, Any]) -> dict[str, Any]:
    block = cfg.get("court_chaser_auto") or {}
    return {
        "enabled": bool(block.get("enabled")),
        "go_live": str(block.get("go_live") or "").strip(),
        "working_days": int(block.get("working_days", 7)),
        "late_days": int(block.get("max_late_working_days", 3)),
        "mail_class": str(block.get("mail_class") or "court-application-chaser"),
        "kind": str(block.get("chaser") or "application_not_answered"),
    }


def enabled(cfg: dict[str, Any]) -> bool:
    return settings(cfg)["enabled"]


def _anchor(since: dt.date) -> str:
    return since.isoformat()


def _row(conn: Any, matter_id: str, anchor: str) -> dict[str, Any] | None:
    got = conn.execute(
        "SELECT status, draft_id, made_utc, note FROM pipeline_court_chasers WHERE matter_id = ? AND anchor = ?", (str(matter_id), anchor)
    ).fetchone()
    return {"status": got[0], "draft_id": got[1], "made_utc": got[2], "note": got[3]} if got else None


def _claim(conn: Any, matter_id: str, anchor: str, now: dt.datetime) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO pipeline_court_chasers (matter_id, anchor, made_utc) VALUES (?, ?, ?)",
        (str(matter_id), anchor, now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    conn.commit()
    return cur.rowcount == 1


def _settle(conn: Any, matter_id: str, anchor: str, status: str, *, draft_id: str = "", note: str = "") -> None:
    conn.execute(
        "UPDATE pipeline_court_chasers SET status = ?, draft_id = ?, note = ? WHERE matter_id = ? AND anchor = ?",
        (status, draft_id, note[:300], str(matter_id), anchor),
    )
    conn.commit()


def _release(conn: Any, matter_id: str, anchor: str) -> None:
    conn.execute("DELETE FROM pipeline_court_chasers WHERE matter_id = ? AND anchor = ?", (str(matter_id), anchor))
    conn.commit()


def go_live_moment(conn: Any, cfg: dict[str, Any], now: dt.datetime, *, record: bool) -> dt.date:
    given = settings(cfg)["go_live"]
    if given:
        return dt.date.fromisoformat(given)
    row = _row(conn, "*", GO_LIVE_ANCHOR)
    if row:
        return nudges.london_date(row["made_utc"]) or now.astimezone(nudges.LONDON).date()
    if record:
        _claim(conn, "*", GO_LIVE_ANCHOR, now)
    return now.astimezone(nudges.LONDON).date()


def court_replied(conn: Any, matter_id: str, since: dt.date) -> bool:
    if conn.execute("SELECT 1 FROM pipeline_step_done WHERE matter_id = ? AND step = 'court_reply'", (str(matter_id),)).fetchone():
        return True
    return any(day >= since for day in nudges.court_replies(conn).get(str(matter_id), []))


def application_recipient(ctx: Any, since: dt.date) -> tuple[str, str]:
    from onboarding.pipeline import step_court_email

    try:
        sent = step_court_email.sent_court_email(ctx)
    except Exception as exc:
        return "", f"Sent Items could not be read ({type(exc).__name__})"
    if not sent:
        return "", "the sent application was not found in Sent Items (it may have been filed through the court's portal)"
    if str(sent.get("sent") or "")[:10] != since.isoformat():
        return "", "the sent application found is not the one recorded as filed"
    to = [str(a) for a in sent.get("to") or [] if a]
    if len(to) != 1:
        return "", f"the application went to {len(to)} court addresses, not one"
    return to[0], ""


def raise_bell(matter_id: str, since: dt.date, why: str) -> None:
    from vergil import attention_store

    who = ""
    try:
        from onboarding import pipeline

        who = pipeline.load_context(str(matter_id)).client_name
    except Exception:
        pass
    attention_store.record(
        kind="update", message_key=f"court-chaser:{matter_id}:{since.isoformat()}"[:80], matter_id=str(matter_id), who=who,
        subject="Court chaser needs a person",
        summary=f"The application sent on {since:%d/%m/%Y} has had no court reply. A chaser draft is in Drafts and has not been sent: {why}",
        importance="high", label="CHASE COURT",
    )


def make_chaser(matter_id: str, since: dt.date, cfg: dict[str, Any], *, db_path: Any = None) -> dict[str, Any]:
    from onboarding import pipeline
    from onboarding.pipeline import court_chaser, folder_guard, send_gate

    conf = settings(cfg)
    ctx = pipeline.load_context(str(matter_id))
    try:
        folder_guard.stop_if_billed(str(matter_id), ctx.folder_path)
        folder_guard.stop_if_retired(ctx.folder_path)
    except folder_guard.FolderStop as exc:
        return {"status": "refused", "draft_id": "", "note": str(exc)[:200]}
    address, why = application_recipient(ctx, since)
    auto = bool(address) and send_gate.enabled(str(matter_id), db_path=db_path)
    out = court_chaser.draft(ctx, conf["kind"], since, to_address=address, auto=auto, mail_class=conf["mail_class"])
    if not out.get("ok"):
        return {"status": "refused", "draft_id": "", "note": str(out.get("summary") or "")[:200]}
    draft_id = str(out.get("draft_id") or "")
    link = str(out.get("web_link") or "")
    armed = False
    if auto and draft_id:
        result = send_gate.arm_if_enabled(str(matter_id), court_chaser.AUTO_STEP, draft_id, conf["mail_class"], [address], db_path=db_path)
        armed = bool(result and result.get("state") in ("armed", "already_armed"))
        if not armed:
            why = "the send gate did not arm it (see Auto send)"
    elif not address:
        why = why or "no court address was confirmed"
    elif not auto:
        why = "Case flow is on Manual for this client"
    note = "armed to send itself at 8am" if armed else f"left unsent: {why}"
    try:
        pipeline.log_event(
            str(matter_id), court_chaser.AUTO_STEP, "ok",
            f"Court chaser: no court reply {conf['working_days']} working days after the application sent on {since:%d/%m/%Y}, so a chaser was drafted, {note}.",
            BY, "auto" if armed else "manual", db_path=db_path, links=[{"label": "Open the draft in Outlook", "url": link}] if link else None,
        )
    except Exception:
        pass
    if not armed:
        try:
            raise_bell(str(matter_id), since, why)
        except Exception:
            pass
    return {"status": "armed" if armed else "drafted", "draft_id": draft_id, "note": note}


def auto_chase(
    *,
    conn: Any,
    cfg: dict[str, Any],
    now: dt.datetime,
    waiting: list[Any],
    maker: Any = None,
    dry_run: bool = False,
    db_path: Any = None,
) -> dict[str, Any]:
    from vergil.hearings import working_days_between

    conf = settings(cfg)
    out: dict[str, Any] = {"enabled": conf["enabled"], "armed": 0, "drafted": 0, "refused": 0, "failed": 0, "skipped": {}}
    if not conf["enabled"]:
        return out
    maker = maker or (lambda matter, since: make_chaser(matter, since, cfg, db_path=db_path))
    today = now.astimezone(nudges.LONDON).date()
    start = go_live_moment(conn, cfg, now, record=not dry_run)

    def skip(why: str) -> None:
        out["skipped"][why] = out["skipped"].get(why, 0) + 1

    from onboarding.pipeline import board_sink

    left = board_sink.left_ids_on(conn, [str(w.matter_id) for w in waiting])
    for wait in waiting:
        matter, since = str(wait.matter_id), wait.since
        if matter in left:
            skip("client_left")
            continue
        if since < start:
            skip("before_go_live")
            continue
        waited = working_days_between(since, today)
        if waited < conf["working_days"]:
            skip("not_due")
            continue
        if waited > conf["working_days"] + conf["late_days"]:
            skip("too_late")
            continue
        if court_replied(conn, matter, since):
            skip("court_replied")
            continue
        if _row(conn, matter, _anchor(since)) is not None:
            skip("already_chased")
            continue
        if dry_run:
            out["drafted"] += 1
            continue
        if not _claim(conn, matter, _anchor(since), now):
            skip("already_chased")
            continue
        try:
            made = maker(matter, since)
        except Exception as exc:
            _release(conn, matter, _anchor(since))
            out["failed"] += 1
            skip(f"error_{type(exc).__name__}")
            continue
        _settle(conn, matter, _anchor(since), str(made["status"]), draft_id=str(made.get("draft_id") or ""), note=str(made.get("note") or ""))
        out[str(made["status"])] += 1
    return out


def withdraw_replied(
    *,
    conn: Any,
    stopper: Any = None,
    db_path: Any = None,
) -> dict[str, int]:
    from onboarding.pipeline import sent_watch

    stopper = stopper or sent_watch.graph_set_stopped
    out = {"withdrawn": 0, "left": 0, "failed": 0}
    rows = conn.execute(
        "SELECT matter_id, anchor, draft_id FROM pipeline_court_chasers WHERE status IN ('armed', 'drafted') AND draft_id <> ''"
    ).fetchall()
    for matter, anchor, draft_id in rows:
        try:
            since = dt.date.fromisoformat(anchor)
            watch = conn.execute("SELECT status FROM pipeline_sent_watch WHERE draft_id = ?", (draft_id,)).fetchone()
            if watch and watch[0] == "sent":
                _settle(conn, matter, anchor, "left", draft_id=draft_id, note="left before any court reply")
                out["left"] += 1
                continue
            if not court_replied(conn, matter, since):
                continue
            if watch and watch[0] == "draft":
                stopper(draft_id)
                sent_watch.mark_stopped(draft_id, "Superseded: the court replied before the chaser left", db_path=db_path)
            _settle(conn, matter, anchor, SUPERSEDED, draft_id=draft_id, note="the court replied before the chaser left")
            out["withdrawn"] += 1
            try:
                from onboarding import pipeline

                pipeline.log_event(
                    str(matter), "court_chaser", "info",
                    "Court chaser withdrawn: the court replied before it left, so SEND STOPPED was put on the draft. It stays in Drafts and will not send.",
                    BY, "auto", db_path=db_path,
                )
            except Exception:
                pass
        except Exception:
            out["failed"] += 1
    return out


def run(conn: Any, cfg: dict[str, Any], rules: list[Any], *, now: dt.datetime, dry_run: bool) -> dict[str, Any]:
    if not enabled(cfg):
        return {"enabled": False}
    try:
        rule = next(r for r in rules if r.kind == "court_reply")
        report: dict[str, Any] = {}
        if not dry_run:
            report["withdraw"] = withdraw_replied(conn=conn)
        report.update(auto_chase(conn=conn, cfg=cfg, now=now, waiting=nudges.court_reply_waiting(conn, rule), dry_run=dry_run))
        return report
    except Exception as exc:
        return {"enabled": True, "error": type(exc).__name__}


def withdraw_pass(db_path: Any = None) -> dict[str, int]:
    try:
        _rules, cfg = nudges.load_rules()
        if not enabled(cfg):
            return {"withdrawn": 0, "left": 0, "failed": 0}
        with ops_db.connect(db_path) as conn:
            return withdraw_replied(conn=conn, db_path=db_path)
    except Exception:
        return {"withdrawn": 0, "left": 0, "failed": 1}
