#!/usr/bin/env python3
"Backfill/reconcile ``matters.closed_at`` from a real OneDrive signal for"

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import graph_files
from agwu.folder import relocate_missing_folder
import clientdb_sql
from vergil import client_edits

CONCLUDED_FOLDER_RE = re.compile(r"concluded", re.IGNORECASE)
DROPPED_OUT_FOLDER_RE = re.compile(r"withdraw|not[\s_-]*seen|\bmissing\b", re.IGNORECASE)
TRANSFERRED_FOLDER_RE = re.compile(r"transfer", re.IGNORECASE)
BILLED_FOLDER_RE = re.compile(r"(?<![a-z])billed", re.IGNORECASE)

CARE_FOLDER_RE = re.compile(r"(?:^|/)[^/]*care-proceedings(?:/|$)", re.IGNORECASE)

BACKFILL_EDITOR = "system:folder-closure-reconciler"

FOLDER_FLAGS: dict[str, tuple[re.Pattern[str], str]] = {
    "dropped_out": (DROPPED_OUT_FOLDER_RE, "Its folder is in a Withdrawn bucket or marked Not seen or Missing"),
    "transferred": (TRANSFERRED_FOLDER_RE, "Its folder name says Transferred"),
    "billed": (BILLED_FOLDER_RE, "Its folder is in a Billed folder"),
    "cat_care_proceedings": (CARE_FOLDER_RE, "Its folder is in the Care-Proceedings book"),
}
CLOSING_FLAGS = frozenset({"dropped_out", "transferred", "billed"})
BILLED_BASELINE_EDITOR = "system:billed-baseline"
BILLED_BASELINE_KEY = "billed_flag_baseline_utc"


def _billed_baseline_done() -> bool:
    "Whether the one-off baseline has run: matters already in a Billed folder when the Billed tick began."
    import ops_db

    try:
        with ops_db.connect() as conn:
            return conn.execute("SELECT 1 FROM pipeline_settings WHERE key = ?", (BILLED_BASELINE_KEY,)).fetchone() is not None
    except Exception:
        return False


def _mark_billed_baseline_done() -> None:
    import ops_db

    with ops_db.connect() as conn:
        conn.execute(
            "INSERT INTO pipeline_settings (key, value, updated_by, updated_utc) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_utc = excluded.updated_utc",
            (BILLED_BASELINE_KEY, "done", BILLED_BASELINE_EDITOR, ops_db.utc_now_z()),
        )


def folder_flags(path: str) -> set[str]:
    "The quick-tick flags a matter's recorded folder path calls for (``dropped_out``, ``transferred``)."
    return {flag for flag, (pattern, _reason) in FOLDER_FLAGS.items() if pattern.search(str(path or ""))}


def closes_matter(path: str) -> bool:
    "Whether the folder path puts the matter out of the live caseload: a Concluded bucket, a Withdrawn bucket,"
    text = str(path or "")
    return bool(CONCLUDED_FOLDER_RE.search(text)) or bool(folder_flags(text) & CLOSING_FLAGS)


class FolderClosureError(RuntimeError):
    "Raised when the Graph metadata call itself fails -- never for \"not"

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status

    @property
    def is_not_found(self) -> bool:
        if self.status is not None:
            return self.status == 404
        return bool(_HTTP_404_RE.search(str(self)))


_HTTP_404_RE = re.compile(r"HTTP Error 404\b")


def _matters_needing_closure_backfill() -> list[dict[str, Any]]:
    sql = "SELECT matter_id, live_matter_folder FROM matters WHERE closed_at IS NULL AND closed_notes IS NULL AND live_matter_folder IS NOT NULL"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        cols = [col[0] for col in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return [
        r
        for r in rows
        if str(r.get("live_matter_folder") or "").strip() and closes_matter(str(r["live_matter_folder"]))
    ]


def _open_matters_with_folder() -> list[dict[str, Any]]:
    "Every open matter that records a folder, in a closing place or live (``concluded`` says which)."
    sql = "SELECT matter_id, live_matter_folder FROM matters WHERE closed_at IS NULL AND closed_notes IS NULL AND live_matter_folder IS NOT NULL"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        cols = [col[0] for col in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    out = []
    for r in rows:
        path = str(r.get("live_matter_folder") or "").strip()
        if path:
            out.append({"matter_id": r["matter_id"], "live_matter_folder": path, "concluded": closes_matter(path)})
    return out


def _closed_matters_with_folder() -> list[dict[str, Any]]:
    "Every closed matter that records a folder. Checked only for a moved or renamed folder, never backfilled."
    sql = "SELECT matter_id, live_matter_folder FROM matters WHERE (closed_at IS NOT NULL OR closed_notes IS NOT NULL) AND live_matter_folder IS NOT NULL"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        cols = [col[0] for col in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return [
        {"matter_id": r["matter_id"], "live_matter_folder": str(r["live_matter_folder"]).strip(), "concluded": False}
        for r in rows
        if str(r.get("live_matter_folder") or "").strip()
    ]


def _matters_needing_reopen() -> list[dict[str, Any]]:
    "Matters this reconciler closed whose folder has since left every closing place."
    sql = "SELECT matter_id, live_matter_folder FROM matters WHERE closed_at IS NOT NULL AND closed_by = ?"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, (BACKFILL_EDITOR,))
        cols = [col[0] for col in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return [
        r
        for r in rows
        if str(r.get("live_matter_folder") or "").strip() and not closes_matter(str(r["live_matter_folder"]))
    ]


def closed_at_from_folder(folder_path: str) -> str:
    "The folder's own ``lastModifiedDateTime`` from live Graph metadata."
    try:
        meta = graph_files.metadata(folder_path)
    except Exception as exc:
        status = getattr(exc, "code", None)
        raise FolderClosureError(
            f"Graph metadata call failed for {folder_path!r}: {exc}",
            status=status if isinstance(status, int) else None,
        ) from exc
    last_modified = str(meta.get("lastModifiedDateTime") or "").strip()
    if not last_modified:
        raise FolderClosureError(f"Graph metadata for {folder_path!r} has no lastModifiedDateTime")
    return last_modified


def backfill_matter(matter_id: str, folder_path: str, *, dry_run: bool = False) -> dict[str, Any]:
    closed_at = closed_at_from_folder(folder_path)
    if dry_run:
        return {"matter_id": matter_id, "closed_at": closed_at, "applied": False}
    client_edits.record_edit(
        matter_id=str(matter_id),
        field_name="concluded",
        new_value="1",
        note=(
            "Closed date inferred from the OneDrive folder's own lastModifiedDateTime "
            "(folder sits under a Concluded or Withdrawn path, or is marked Transferred, Not seen or Missing) -- "
            "not a verified move event."
        ),
        edited_by=BACKFILL_EDITOR,
        closed_at=closed_at,
    )
    return {"matter_id": matter_id, "closed_at": closed_at, "applied": True}


def _matters_with_folder() -> list[dict[str, Any]]:
    "Every matter that records a folder, open or closed: the flags follow the folder, not the open state."
    sql = "SELECT matter_id, live_matter_folder FROM matters WHERE live_matter_folder IS NOT NULL"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall() if str(row[1] or "").strip()]


def sync_folder_flags(*, dry_run: bool = False) -> dict[str, list[dict[str, str]]]:
    "Tick ``dropped_out`` / ``transferred`` for a matter whose folder path calls for it, and take back a tick this"
    names = list(FOLDER_FLAGS)
    rows = client_edits.list_flag_rows(names)
    summary: dict[str, list[dict[str, str]]] = {"set": [], "cleared": []}
    billed_baseline = not _billed_baseline_done()
    for row in _matters_with_folder():
        matter_id = str(row["matter_id"])
        wanted = folder_flags(str(row["live_matter_folder"]))
        for flag in names:
            have = rows.get((matter_id, flag))
            reason = FOLDER_FLAGS[flag][1]
            if flag == "billed" and billed_baseline:
                if flag in wanted and not have and not dry_run:
                    client_edits.set_flag(matter_id=matter_id, flag_name=flag, is_set=False, set_by=BILLED_BASELINE_EDITOR, reason="In a Billed folder before the Billed tick began")
                continue
            if flag in wanted:
                if have and (have["is_set"] or have["set_by"] != BACKFILL_EDITOR):
                    continue
                if not dry_run:
                    client_edits.set_flag(matter_id=matter_id, flag_name=flag, is_set=True, set_by=BACKFILL_EDITOR, reason=reason)
                summary["set"].append({"matter_id": matter_id, "flag": flag})
            elif have and have["is_set"] and have["reason"] == reason:
                if not dry_run:
                    client_edits.set_flag(matter_id=matter_id, flag_name=flag, is_set=False, set_by=BACKFILL_EDITOR, only_if_reason=reason)
                summary["cleared"].append({"matter_id": matter_id, "flag": flag})
    if billed_baseline and not dry_run:
        _mark_billed_baseline_done()
    return summary


def scan(*, dry_run: bool = False, limit: int | None = None, include_closed: bool = False) -> dict[str, Any]:
    "Check every open matter's recorded folder; backfill closed_at for those in a closing place (a Concluded"
    rows = _open_matters_with_folder()
    if include_closed:
        rows = rows + _closed_matters_with_folder()
    if limit:
        rows = rows[:limit]
    summary: dict[str, Any] = {
        "scanned": len(rows),
        "applied": [],
        "relocated": [],
        "stale_paths": [],
        "errored": [],
        "live_checked": 0,
        "reopened": [],
        "flags_set": [],
        "flags_cleared": [],
    }
    try:
        flags = sync_folder_flags(dry_run=dry_run)
        summary["flags_set"], summary["flags_cleared"] = flags["set"], flags["cleared"]
    except Exception as exc:
        summary["errored"].append({"matter_id": "", "reason": f"folder flags not synced ({type(exc).__name__})"})
    for row in _matters_needing_reopen():
        matter_id = row["matter_id"]
        if not dry_run:
            client_edits.record_edit(
                matter_id=str(matter_id),
                field_name="concluded",
                new_value="0",
                note="Folder is no longer under a Concluded path, so the matter is live again.",
                edited_by=BACKFILL_EDITOR,
            )
        summary["reopened"].append({"matter_id": matter_id, "applied": not dry_run})
    for row in rows:
        matter_id = row["matter_id"]
        folder_path = row["live_matter_folder"]
        concluded = row.get("concluded", True)
        try:
            try:
                if concluded:
                    result = backfill_matter(matter_id, folder_path, dry_run=dry_run)
                else:
                    closed_at_from_folder(folder_path)
                    result = None
            except FolderClosureError as exc:
                if not exc.is_not_found:
                    raise
                moved = relocate_missing_folder(matter_id, folder_path, update_cache=not dry_run)
                if moved.status != "found":
                    summary["stale_paths"].append(str(matter_id))
                    continue
                summary["relocated"].append({"matter_id": matter_id, "how": moved.how})
                if moved.how != "name_search_ambiguous" and not dry_run:
                    try:
                        client_edits.record_folder_move(
                            matter_id=str(matter_id), old_path=folder_path, new_path=moved.path, edited_by=BACKFILL_EDITOR
                        )
                    except Exception as move_exc:
                        summary["errored"].append({"matter_id": matter_id, "reason": f"folder found but record not updated ({type(move_exc).__name__})"})
                        continue
                result = backfill_matter(matter_id, moved.path, dry_run=dry_run) if concluded else None
        except FolderClosureError as exc:
            summary["errored"].append({"matter_id": matter_id, "reason": str(exc)})
            continue
        if result is None:
            summary["live_checked"] += 1
        else:
            summary["applied"].append(result)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matter-id", help="Backfill (or preview) one matter by id")
    parser.add_argument("--scan", action="store_true", help="Backfill every matter in a closing folder with no closed_at, and tick Dropped out / Transferred from folder paths")
    parser.add_argument("--include-closed", action="store_true", help="With --scan, also check closed matters' folders for a rename or move and follow it in SQL")
    parser.add_argument("--dry-run", action="store_true", help="Read the Graph metadata but do not write")
    parser.add_argument("--limit", type=int, default=None, help="With --scan, cap how many matters are processed")
    args = parser.parse_args(argv)

    if args.scan:
        try:
            summary = scan(dry_run=args.dry_run, limit=args.limit, include_closed=args.include_closed)
        except Exception as exc:
            print(json.dumps({"error": f"scan failed: {type(exc).__name__}: {exc}"}, indent=2), file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=2, default=str))
        return 1 if summary["errored"] else 0

    if not args.matter_id:
        parser.error("--matter-id or --scan is required")

    rows = [r for r in _matters_needing_closure_backfill() if str(r["matter_id"]) == str(args.matter_id)]
    if not rows:
        print(json.dumps({"matter_id": args.matter_id, "error": "matter has no closed_at gap in a closing folder"}, indent=2))
        return 1
    result = backfill_matter(args.matter_id, rows[0]["live_matter_folder"], dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
