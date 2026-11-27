#!/usr/bin/env python3
"Folder delta check: client folders the system does not know about, or that moved."
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Iterable

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db
import robot_notices

NO_RECORD = "no_record"
MOVED = "moved"
MAX_INDIVIDUAL = 8
MIN_FOLDERS_TO_TRUST = 30

_NOT_A_CLIENT = re.compile(
    r"\b(?:templates?|unsorted|delete later|batch|holding|misc|forms|invoices?|knowledge base)\b"
    r"|^(?:zz|~|\.)|^\d{4}\b|^0|^1\s",
    re.IGNORECASE,
)


def _norm(path: str) -> str:
    return str(path or "").strip().rstrip("/").lower()


def _book_of(path: str) -> str:
    parts = [p for p in str(path or "").split("/") if p]
    return parts[-2] if len(parts) >= 2 else ""


_SORT_PREFIX = re.compile(r"^\s*\d*a+-z\s*-?\s*", re.IGNORECASE)


def book_display(book: str) -> str:
    "A book's name without its sort prefix (\"<sort prefix> - Alex\" shows as \"Alex\")."
    return _SORT_PREFIX.sub("", str(book or "")).strip() or str(book or "").strip()


def moved_dedupe_key(item_id: str, book: str) -> str:
    "The one robot-notice key for a folder arriving in a book, shared with ``vergil.moved_from_sync.announce_moves``"
    return f"folder_moved:{item_id}:{book_display(book).lower()}"


def ensure_state_table(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS folder_delta_seen ("
        "kind TEXT NOT NULL, key TEXT NOT NULL, first_seen_utc TEXT NOT NULL, PRIMARY KEY (kind, key))"
    )


def client_folders(conn, *, live_base: str, roots: Iterable[str], excluded: Iterable[re.Pattern]) -> list[dict[str, str]]:
    "Top-level folders of each caseload book that look like a client, not a bucket."
    excluded = list(excluded)
    found: list[dict[str, str]] = []
    for book in roots:
        root = conn.execute(
            "SELECT drive_id, item_id FROM onedrive_items WHERE path = ? COLLATE NOCASE "
            "AND item_type = 'folder' AND deleted_at_utc IS NULL LIMIT 1",
            (f"{live_base}/{book}",),
        ).fetchone()
        if not root:
            continue
        for item_id, drive_id, path, name in conn.execute(
            "SELECT item_id, drive_id, path, name FROM onedrive_items WHERE drive_id = ? AND parent_item_id = ? "
            "AND item_type = 'folder' AND deleted_at_utc IS NULL",
            (root[0], root[1]),
        ).fetchall():
            if _NOT_A_CLIENT.search(name) or any(p.search(name) for p in excluded):
                continue
            found.append({"item_id": str(item_id), "drive_id": str(drive_id), "path": str(path), "name": str(name), "book": book})
    return found


def _linked(conn) -> tuple[set[str], list[str], dict[str, dict[str, str]]]:
    ids: set[str] = set()
    paths: list[str] = []
    by_item: dict[str, dict[str, str]] = {}
    for matter_id, item_id, path in conn.execute(
        "SELECT matter_id, COALESCE(folder_item_id, ''), COALESCE(folder_path, '') FROM matter_onedrive_roots"
    ).fetchall():
        if item_id:
            ids.add(str(item_id))
            by_item[str(item_id)] = {"matter_id": str(matter_id), "path": str(path)}
        if path:
            paths.append(_norm(path))
    return ids, paths, by_item


def unlinked(folders: list[dict[str, str]], ids: set[str], paths: list[str]) -> list[dict[str, str]]:
    "Folders with no matter behind them: not linked by id, by path, or by a sub-folder."
    out = []
    for f in folders:
        p = _norm(f["path"])
        if f["item_id"] in ids or any(p == c or c.startswith(p + "/") or p.startswith(c + "/") for c in paths):
            continue
        out.append(f)
    return out


def moved(conn, by_item: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    "Linked folders whose indexed path is no longer the recorded one."
    out = []
    items = list(by_item)
    for i in range(0, len(items), 400):
        chunk = items[i : i + 400]
        marks = ",".join("?" for _ in chunk)
        for item_id, path, name in conn.execute(
            f"SELECT item_id, path, name FROM onedrive_items WHERE item_type = 'folder' "
            f"AND deleted_at_utc IS NULL AND item_id IN ({marks})",
            chunk,
        ).fetchall():
            recorded = by_item[str(item_id)]
            if recorded["path"] and _norm(path) != _norm(recorded["path"]):
                out.append(
                    {"item_id": str(item_id), "path": str(path), "name": str(name), "old_path": recorded["path"], "matter_id": recorded["matter_id"]}
                )
    return out


def _seen(conn, kind: str) -> set[str]:
    return {r[0] for r in conn.execute("SELECT key FROM folder_delta_seen WHERE kind = ?", (kind,)).fetchall()}


def _mark(conn, kind: str, keys: Iterable[str]) -> None:
    now = ops_db.utc_now_z()
    conn.executemany(
        "INSERT OR IGNORE INTO folder_delta_seen (kind, key, first_seen_utc) VALUES (?, ?, ?)", [(kind, k, now) for k in keys]
    )


def run(*, live_base: str, roots: Iterable[str], excluded: Iterable[re.Pattern] = (), db_path: str | Path | None = None) -> dict[str, Any]:
    "One pass. Never raises for a data problem: returns what it did (or why it did nothing)."
    summary: dict[str, Any] = {"raised": 0, "resolved": 0}
    with ops_db.connect(db_path) as conn:
        ensure_state_table(conn)
        folders = client_folders(conn, live_base=live_base, roots=roots, excluded=excluded)
        if len(folders) < MIN_FOLDERS_TO_TRUST:
            return {**summary, "skipped": f"only {len(folders)} client folders indexed; index looks partial"}
        ids, paths, by_item = _linked(conn)
        gap = unlinked(folders, ids, paths)
        moves = moved(conn, by_item)
        first_run = not conn.execute("SELECT 1 FROM folder_delta_seen WHERE kind = 'baseline'").fetchone()
        _mark(conn, "baseline", ["done"])
        seen_gap, seen_moved = _seen(conn, NO_RECORD), _seen(conn, MOVED)
        new_gap = [f for f in gap if f["item_id"] not in seen_gap]
        move_key = lambda m: f"{m['item_id']}|{_norm(m['path'])}"
        announced = lambda m: conn.execute(
            "SELECT 1 FROM robot_notices WHERE dedupe_key = ? LIMIT 1", (moved_dedupe_key(m["item_id"], _book_of(m["path"])),)
        ).fetchone()
        new_moves = [m for m in moves if move_key(m) not in seen_moved and not announced(m)]
        _mark(conn, NO_RECORD, [f["item_id"] for f in new_gap])
        _mark(conn, MOVED, [move_key(m) for m in new_moves])
        conn.commit()
        still_gap = {f["item_id"] for f in gap}
        still_moved = {move_key(m) for m in moves}
        summary.update(unlinked=len(gap), moved=len(moves))

    raised = 0
    if first_run and new_gap:
        per_book: dict[str, int] = {}
        for f in new_gap:
            per_book[f["book"]] = per_book.get(f["book"], 0) + 1
        detail = "; ".join(f"{b}: {n}" for b, n in sorted(per_book.items(), key=lambda kv: -kv[1]))
        robot_notices.add(
            "folder_gap_baseline",
            f"{len(new_gap)} client folders have no client record",
            f"Existing folders no matter is linked to, so notes, billing and lookups cannot find them. By book: {detail}. "
            "Run: python3 tools/agwu/folder_delta.py report",
            dedupe_key="folder_gap_baseline",
            db_path=db_path,
        )
        raised += 1
    elif len(new_gap) > MAX_INDIVIDUAL:
        robot_notices.add(
            "folder_gap_many",
            f"{len(new_gap)} new client folders have no client record",
            "Several folders appeared at once (a book handed over or re-indexed). Run: python3 tools/agwu/folder_delta.py report",
            dedupe_key=f"folder_gap_many:{ops_db.utc_now_z()[:13]}",
            db_path=db_path,
        )
        raised += 1
    else:
        for f in new_gap:
            robot_notices.add(
                "folder_no_record",
                "Client folder has no client record",
                f"In {f['book']}. No matter is linked to this folder, so notes, billing and lookups cannot find it. "
                "Create the client record or link the folder.",
                client_name=f["name"],
                dedupe_key=f"folder_no_record:{f['item_id']}",
                db_path=db_path,
            )
            raised += 1
    for m in new_moves:
        robot_notices.add(
            "folder_moved",
            "Case moved",
            f"Moved from {book_display(_book_of(m['old_path']))} to {book_display(_book_of(m['path']))}. "
            "Casework carries on as normal wherever the folder is.",
            matter_id=m["matter_id"],
            client_name=m["name"],
            dedupe_key=moved_dedupe_key(m["item_id"], _book_of(m["path"])),
            db_path=db_path,
        )
        raised += 1

    resolved = 0
    for key in seen_gap - still_gap:
        resolved += robot_notices.resolve(f"folder_no_record:{key}", db_path=db_path)
    for key in seen_moved - still_moved:
        item_id, _, old_norm = key.partition("|")
        resolved += robot_notices.resolve(moved_dedupe_key(item_id, _book_of(old_norm)), db_path=db_path)
    if not gap and not first_run:
        resolved += robot_notices.resolve("folder_gap_baseline", db_path=db_path)
    summary.update(raised=raised, resolved=resolved, first_run=first_run)
    return summary


def report(*, live_base: str, roots: Iterable[str], excluded: Iterable[re.Pattern] = (), db_path: str | Path | None = None) -> dict[str, list[str]]:
    "Every client folder with no matter behind it, by book (names, for staff)."
    with ops_db.connect(db_path) as conn:
        folders = client_folders(conn, live_base=live_base, roots=roots, excluded=excluded)
        ids, paths, _ = _linked(conn)
    by_book: dict[str, list[str]] = {}
    for f in unlinked(folders, ids, paths):
        by_book.setdefault(f["book"], []).append(f["name"])
    return {b: sorted(n, key=str.lower) for b, n in by_book.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["report", "run"])
    args = parser.parse_args(argv)
    import graph_index

    kwargs = {"live_base": graph_index.LIVE_BASE, "roots": [r for r in graph_index.ROOTS if r not in graph_index.RECONCILE_EXCLUDED_ROOTS], "excluded": graph_index.HOT_REFRESH_EXCLUDED_FOLDER_PATTERNS}
    if args.command == "run":
        print(run(**kwargs))
        return 0
    for book, names in sorted(report(**kwargs).items()):
        print(f"{book} ({len(names)})")
        for name in names:
            print(f"    {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
