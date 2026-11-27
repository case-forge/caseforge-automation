#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import firm_profile
import ops_db
from vergil import assignment_board

def _graph_fetch() -> Any:
    import graph_files

    tok = graph_files.token()

    def fetch(drive_id: str, item_id: str) -> list[dict[str, Any]]:
        body = graph_files.graph_json(f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/activities", tok)
        return list(body.get("value") or [])

    return fetch


def previous_move(activities: list[dict[str, Any]], *, current_book: str, client_folder: str = "") -> tuple[str, str] | None:
    now_key = assignment_board._book_key(current_book)
    own = str(client_folder or "").strip().lower()
    for activity in activities:
        previous = str(((activity.get("action") or {}).get("move") or {}).get("from") or "").rstrip("/").split("/")
        if len(previous) < 2:
            continue
        parent = previous[-2]
        if (own and parent.strip().lower() == own) or assignment_board._book_key(parent) == now_key:
            continue
        times = activity.get("times") or {}
        return parent, str(times.get("recordedTime") or activity.get("lastRecordedDateTime") or "")
    return None


def _parse_time(text: str) -> dt.datetime | None:
    try:
        when = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)


READ_KIND = "move_read"
BASELINE_KIND = "move_read_baseline"
RECENT_DAYS = 7


def announce_moves(*, db_path: str | Path | None = None, fetch: Any = None, now: dt.datetime | None = None) -> dict[str, Any]:
    import robot_notices
    from agwu import folder_delta
    from onboarding import pipeline
    now = now or dt.datetime.now(dt.timezone.utc)
    worker_books = {w: pipeline.WORKER_BOOKS.get(w, "") for w in firm_profile.load_profile().workers}
    shared = pipeline.SHARED_BOOKS
    key = assignment_board._book_key
    in_scope = {key(b) for b in shared} | {key(b) for b in worker_books.values() if b}
    fetch = fetch or _graph_fetch()
    cases = assignment_board.gather(include_concluded=False, db_path=db_path)["cases"]
    open_ids = {str(c["matter_id"]) for c in cases}
    counts = {"checked": 0, "already_read": 0, "read_failed": 0, "never_moved": 0, "announced": 0, "recorded_quietly": 0}
    with ops_db.connect(db_path) as conn:
        folder_delta.ensure_state_table(conn)
        first_run = not conn.execute("SELECT 1 FROM folder_delta_seen WHERE kind = ?", (BASELINE_KIND,)).fetchone()
        read = folder_delta._seen(conn, READ_KIND)
        todo = []
        for mid, item_id, drive_id in conn.execute("SELECT matter_id, COALESCE(folder_item_id, ''), COALESCE(drive_id, '') FROM matter_onedrive_roots").fetchall():
            if str(mid) not in open_ids or not item_id or not drive_id:
                continue
            row = conn.execute("SELECT path, name FROM onedrive_items WHERE item_id = ? AND item_type = 'folder' AND deleted_at_utc IS NULL LIMIT 1", (item_id,)).fetchone()
            if not row or key(folder_delta._book_of(row[0])) not in in_scope:
                continue
            if str(item_id) in read:
                counts["already_read"] += 1
                continue
            todo.append((str(mid), str(item_id), str(drive_id), str(row[0]), str(row[1])))
    moves: list[dict[str, str]] = []
    done: list[str] = []
    for mid, item_id, drive_id, path, name in todo:
        counts["checked"] += 1
        try:
            activities = fetch(drive_id, item_id)
        except Exception:
            counts["read_failed"] += 1
            continue
        done.append(item_id)
        new_book = folder_delta._book_of(path)
        hit = previous_move(activities, current_book=new_book, client_folder=name)
        if not hit:
            counts["never_moved"] += 1
            continue
        old_book, when_text = hit
        when = _parse_time(when_text)
        recent = (not first_run) if when is None else (now - when) <= dt.timedelta(days=RECENT_DAYS)
        if recent:
            moves.append({"matter_id": mid, "item_id": item_id, "name": name, "old": old_book, "new": new_book})
        else:
            counts["recorded_quietly"] += 1
    with ops_db.connect(db_path) as conn:
        folder_delta.ensure_state_table(conn)
        folder_delta._mark(conn, READ_KIND, done)
        folder_delta._mark(conn, BASELINE_KIND, ["done"])
        conn.commit()
    if len(moves) > folder_delta.MAX_INDIVIDUAL:
        robot_notices.add(
            "folder_moved_many",
            f"{len(moves)} cases moved between books",
            "Several case folders moved between books. Casework carries on as normal wherever the folder is.",
            dedupe_key=f"folder_moved_many:{ops_db.utc_now_z()[:13]}",
            db_path=db_path,
        )
        counts["announced"] = 1
    else:
        for m in moves:
            robot_notices.add(
                "folder_moved",
                "Case moved",
                f"Moved from {folder_delta.book_display(m['old'])} to {folder_delta.book_display(m['new'])}. Casework carries on as normal wherever the folder is.",
                matter_id=m["matter_id"],
                client_name=m["name"],
                dedupe_key=folder_delta.moved_dedupe_key(m["item_id"], m["new"]),
                db_path=db_path,
            )
            counts["announced"] += 1
    return {**counts, "first_run": first_run}

