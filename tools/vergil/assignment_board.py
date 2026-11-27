from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import firm_profile
import ops_db

TTL_SECONDS = 120.0
_LOCK = threading.Lock()
_CACHE: dict[bool, tuple[float, dict[str, Any]]] = {}


def clear() -> None:
    with _LOCK:
        _CACHE.clear()


def _index_refreshed_utc() -> str:
    try:
        from telemetry_sqlite import list_runtime_events

        for event in list_runtime_events(limit=200):
            if event.get("event_name") == "graph_index_refresh" and (event.get("metrics") or {}).get("status") == "success":
                return str(event.get("timestamp") or "")
    except Exception:
        pass
    try:
        with ops_db.connect() as conn:
            row = conn.execute("SELECT MAX(last_seen_utc) FROM onedrive_items WHERE deleted_at_utc IS NULL").fetchone()
        return str((row[0] if row else "") or "")
    except Exception:
        return ""


_SORT_PREFIX = re.compile(r"^\s*\d*a+-z\s*-?\s*", re.IGNORECASE)


def _book_key(book: str) -> str:
    return _SORT_PREFIX.sub("", str(book or "")).strip().lower()


def gather(*, include_concluded: bool = False, db_path: str | Path | None = None) -> dict[str, Any]:
    import graph_index
    from onboarding import client_removal, pipeline

    matters = graph_index._load_sql_matter_rows()
    matters = client_removal.visible_rows(matters, matter_id_of=lambda r: str(r.get("matter_id") or ""), db_path=db_path)
    worker_books = {w: pipeline.WORKER_BOOKS.get(w, "") for w in firm_profile.load_profile().workers}
    return graph_index.assignment_board_report(
        matters,
        ops_db.list_onedrive_folders(db_path=db_path),
        worker_books=worker_books,
        default_book=firm_profile.load_profile().protective_orders_book,
        index_refreshed_utc=_index_refreshed_utc(),
        include_concluded=include_concluded,
    )


def board(*, include_concluded: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(include_concluded)
        if hit and now - hit[0] < TTL_SECONDS:
            return hit[1]
    result = gather(include_concluded=include_concluded)
    with _LOCK:
        _CACHE[include_concluded] = (now, result)
    return result
