#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
import urllib.error
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import graph_files
import clientdb_sql

SOS_QUERY = "statement of service"
_DRAFT_RE = re.compile(r"\bdraft\d*\b", re.IGNORECASE)
_DRAFT_SEPARATOR_RE = re.compile(r"[-_.]+")
_SOS_NAME_TOKEN = re.compile(r"[^a-z0-9]+")


def _is_draft_filename(name: str) -> bool:
    return bool(_DRAFT_RE.search(_DRAFT_SEPARATOR_RE.sub(" ", name)))


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def _is_sos_filename(name: str) -> bool:
    normalised = _SOS_NAME_TOKEN.sub("", name.lower())
    return "statementofservice" in normalised


def _matter_folder(matter_id: str) -> str:
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT live_matter_folder FROM matters WHERE matter_id = ?", (matter_id,))
        row = cursor.fetchone()
    return clean_text(row[0]) if row else ""


_SEEN_DDL = """
CREATE TABLE IF NOT EXISTS matter_sos_seen (
    matter_id TEXT NOT NULL,
    name TEXT NOT NULL,
    modified_utc TEXT NOT NULL DEFAULT '',
    web_url TEXT NOT NULL DEFAULT '',
    is_draft INTEGER NOT NULL DEFAULT 0,
    first_seen_utc TEXT NOT NULL,
    PRIMARY KEY (matter_id, name)
)
"""


def _seen(matter_id: str) -> list[dict[str, Any]]:
    try:
        import ops_db

        with ops_db.connect() as conn:
            conn.execute(_SEEN_DDL)
            rows = conn.execute(
                "SELECT name, modified_utc, web_url, is_draft FROM matter_sos_seen WHERE matter_id = ?", (matter_id,)
            ).fetchall()
        return [{"name": r[0], "modified_utc": r[1], "web_url": r[2], "is_draft": bool(r[3])} for r in rows]
    except Exception:
        return []


def _remember(matter_id: str, items: list[dict[str, Any]]) -> None:
    if not items:
        return
    try:
        import datetime as dt

        import ops_db

        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        with ops_db.connect() as conn:
            conn.execute(_SEEN_DDL)
            for item in items:
                conn.execute(
                    "INSERT INTO matter_sos_seen (matter_id, name, modified_utc, web_url, is_draft, first_seen_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(matter_id, name) DO UPDATE SET "
                    "modified_utc = excluded.modified_utc, web_url = excluded.web_url, is_draft = excluded.is_draft",
                    (matter_id, item["name"], item["modified_utc"], item["web_url"], 1 if item["is_draft"] else 0, now),
                )
    except Exception:
        return


def _answer(matter_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    items = sorted(items, key=lambda i: i["modified_utc"], reverse=True)
    signed_count = sum(1 for i in items if not i["is_draft"])
    return {"matter_id": matter_id, "count": signed_count, "draft_count": len(items) - signed_count, "items": items, "folder_found": True}


def sos_status(matter_id: str, *, access_token: str | None = None) -> dict[str, Any]:
    matter_id = clean_text(matter_id)
    if not matter_id:
        return {"matter_id": matter_id, "count": 0, "draft_count": 0, "items": [], "folder_found": False}

    folder = _matter_folder(matter_id)
    if not folder:
        return {"matter_id": matter_id, "count": 0, "draft_count": 0, "items": [], "folder_found": False}

    try:
        matches = graph_files.search_in_folder(folder, SOS_QUERY, access_token=access_token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"matter_id": matter_id, "count": 0, "draft_count": 0, "items": [], "folder_found": False}
        remembered = _seen(matter_id)
        if remembered:
            return _answer(matter_id, remembered)
        raise
    except (urllib.error.URLError, TimeoutError, OSError):
        remembered = _seen(matter_id)
        if remembered:
            return _answer(matter_id, remembered)
        raise
    items: list[dict[str, Any]] = []
    for item in matches:
        name = clean_text(item.get("name"))
        if not name.lower().endswith((".pdf", ".docx", ".doc")):
            continue
        if not _is_sos_filename(name):
            continue
        items.append(
            {
                "name": name,
                "modified_utc": clean_text(item.get("lastModifiedDateTime")),
                "web_url": graph_files.short_link_for_item(item, access_token=access_token),
                "is_draft": _is_draft_filename(name),
            }
        )
    _remember(matter_id, items)
    found = {i["name"] for i in items}
    items = items + [r for r in _seen(matter_id) if r["name"] not in found]
    return _answer(matter_id, items)
