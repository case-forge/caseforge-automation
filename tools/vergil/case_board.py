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
from onboarding import pipeline as pl

IMPLIED: dict[str, tuple[str, ...]] = {"court_email": ("court_pack", "ws_sign"), "court_pack": ("ws_sign",)}
NOT_COLUMNS: tuple[str, ...] = ("amend",)
BOARD_STEP = "board"
QUIET_DAYS = 14
LIMIT = 300
_NO_RESET = "reset"


def columns() -> list[dict[str, Any]]:
    labels = {key: label for key, label, _module in pl.STEPS}
    return [{"key": key, "number": pl.STEP_NUMBERS.get(key), "label": labels[key]} for key in pl.AUTO_STEPS if key not in NOT_COLUMNS]


def _parse(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _chunks(items: list[str], size: int = 400) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _done_steps(matter_ids: list[str], db_path: str | Path | None) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with ops_db.connect(db_path) as conn:
        for chunk in _chunks(matter_ids):
            marks = ", ".join("?" for _ in chunk)
            for matter_id, step, checked in conn.execute(
                f"SELECT matter_id, step, checked_utc FROM pipeline_step_done WHERE matter_id IN ({marks})", tuple(chunk)
            ).fetchall():
                out.setdefault(str(matter_id), {})[str(step)] = str(checked or "")
    unfinished = pl.fetch_unfinished_matters(list(out), db_path=db_path)
    for matter_id, steps in out.items():
        if pl.folded_done(steps, matter_id in unfinished):
            steps[pl.FOLDER_STEP] = max(steps[k] for k in pl.LEGACY_FOLDER_STEPS if k in steps)
    return out


def _events_since_reset(matter_ids: list[str], db_path: str | Path | None) -> dict[str, list[dict[str, str]]]:
    rows_by: dict[str, list[dict[str, str]]] = {}
    with ops_db.connect(db_path) as conn:
        for chunk in _chunks(matter_ids):
            marks = ", ".join("?" for _ in chunk)
            for matter_id, step, status, summary, created in conn.execute(
                f"SELECT matter_id, step, status, summary, created_utc FROM pipeline_events WHERE matter_id IN ({marks}) "
                "ORDER BY created_utc DESC, rowid DESC",
                tuple(chunk),
            ).fetchall():
                rows_by.setdefault(str(matter_id), []).append(
                    {"step": pl.canonical_step(str(step)), "status": str(status), "summary": str(summary or ""), "created_utc": str(created or "")}
                )
    out: dict[str, list[dict[str, str]]] = {}
    for matter_id, rows in rows_by.items():
        kept: list[dict[str, str]] = []
        for row in rows:
            if row["step"] == _NO_RESET:
                break
            kept.append(row)
        out[matter_id] = kept
    return out


def _created(matter_ids: list[str]) -> dict[str, str]:
    import clientdb_sql

    out: dict[str, str] = {}
    try:
        with clientdb_sql.get_connection() as conn:
            cur = conn.cursor()
            for chunk in _chunks(matter_ids):
                marks = ", ".join("?" for _ in chunk)
                cur.execute(f"SELECT matter_id, created_utc FROM dbo.matters WHERE CAST(matter_id AS TEXT) IN ({marks})", tuple(chunk))
                out.update({str(r[0]): str(r[1] or "") for r in cur.fetchall()})
    except Exception:
        return {}
    return out


def removed(db_path: str | Path | None = None) -> set[str]:
    with ops_db.connect(db_path) as conn:
        return {str(r[0]) for r in conn.execute("SELECT matter_id FROM pipeline_board_removed").fetchall()}


def remove(matter_id: str, by: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    mid = str(matter_id or "").strip()
    who = str(by or "").strip()[:80]
    if not mid.isdigit():
        raise pl.PipelineError("matter_id must be a matter number")
    if not who:
        raise pl.PipelineError("type your name first")
    with ops_db.connect(db_path) as conn:
        done = conn.execute(
            "INSERT OR IGNORE INTO pipeline_board_removed (matter_id, removed_by, removed_utc) VALUES (?, ?, ?)",
            (mid, who, ops_db.utc_now_z()),
        ).rowcount
        conn.commit()
    if done:
        pl.log_event(mid, BOARD_STEP, "info", f"Taken off the Case flow board by {who}. Nothing was deleted.", who, pl.get_mode(db_path=db_path), db_path=db_path)
    return {"matter_id": mid, "removed": bool(done), "already_removed": not done}


def _pending_text(step_label: str, events: list[dict[str, str]], step_key: str) -> str:
    for event in events:
        if event["step"] != step_key:
            continue
        summary = event["summary"].strip()
        if event["status"] == "failed":
            return f"Failed: {summary}" if summary else "Failed"
        if event["status"] == pl.WAITING:
            return summary.removeprefix(pl.WAITING_PREFIX) or "Waiting for a person"
        if event["status"] == pl.HELD:
            return "Held"
        break
    return step_label


def _age_days(created: str, now: dt.datetime) -> int | None:
    opened = _parse(created)
    return max(0, (now - opened).days) if opened else None


def board(*, now: dt.datetime | None = None, db_path: str | Path | None = None, limit: int = LIMIT) -> dict[str, Any]:
    import clientdb_sql

    now = now or dt.datetime.now(dt.timezone.utc)
    ids = {i for i in pl.open_matter_ids() if str(i).isdigit()} - removed(db_path)
    from onboarding import client_removal

    ids = set(client_removal.visible_rows(sorted(ids), matter_id_of=str, db_path=db_path))
    if not ids:
        return {"steps": columns(), "items": [], "complete": 0, "total": 0}

    matters = clientdb_sql._matter_summaries(sorted(ids))
    open_ids = sorted(m for m in ids if m in matters and not matters[m].get("closed_at"))
    done = _done_steps(open_ids, db_path)
    events = _events_since_reset(open_ids, db_path)
    opened = _created(open_ids)
    chain = [key for key in pl.AUTO_STEPS if key not in NOT_COLUMNS]
    labels = {key: label for key, label, _module in pl.STEPS}

    from onboarding.pipeline import sync_scan

    sync = sync_scan.saved(open_ids, db_path=db_path)
    from vergil import today_board

    stopped = today_board._pit_stops(db_path)
    items: list[dict[str, Any]] = []
    complete = 0
    for matter_id in open_ids:
        log = events.get(matter_id, [])
        finished = dict(done.get(matter_id, {}))
        for e in reversed(log):
            if e["step"] in pl.REPEAT_STEPS and e["status"] in ("ok", pl.OUTSIDE_EVENT):
                finished.setdefault(e["step"], e["created_utc"])
        for later, earlier in IMPLIED.items():
            if later in finished:
                for key in earlier:
                    finished.setdefault(key, finished[later])
        current = next((key for key in chain if key not in finished), None)
        if current is None:
            complete += 1
            continue
        index = chain.index(current)
        since = ""
        if index > 0:
            before = chain[index - 1]
            ok = next((e["created_utc"] for e in log if e["step"] == before and e["status"] == "ok"), "")
            since = ok or finished.get(before, "")
        last_event = log[0]["created_utc"] if log else ""
        started = _parse(since) or _parse(opened.get(matter_id, "")) or _parse(last_event)
        latest = max((t for t in (_parse(since), _parse(last_event)) if t is not None), default=started)
        days = max(0, (now - started).days) if started else None
        quiet = bool(latest and (now - latest).days >= QUIET_DAYS)
        name = str(matters[matter_id].get("canonical_name") or "")
        items.append(
            {
                "matter_id": matter_id,
                "client_name": name,
                "surname": pl.surname_of(name),
                "step": current,
                "step_number": pl.STEP_NUMBERS.get(current),
                "pending": _pending_text(labels[current], log, current),
                "since_utc": started.isoformat().replace("+00:00", "Z") if started else "",
                "days": days,
                "age_days": _age_days(opened.get(matter_id, ""), now),
                "quiet": quiet,
                "seen": bool(finished or log),
                "done_steps": [key for key in chain if key in finished],
                "sync": sync.get(matter_id),
                "waiting": stopped.get(matter_id, ""),
            }
        )
    items.sort(key=lambda i: (bool(i["waiting"]), i["quiet"], -(i["days"] or 0), i["surname"]))
    return {
        "steps": columns(),
        "items": items[:limit],
        "complete": complete,
        "total": len(items),
    }
