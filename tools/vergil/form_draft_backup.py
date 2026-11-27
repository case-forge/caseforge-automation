#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db

MAX_PAYLOAD = 100_000
MAX_ID = 120
MAX_AGE = dt.timedelta(days=7)
MATTER_ID = re.compile(r"^\d{1,20}$")


class DraftError(ValueError):
    pass


def _key(value: Any, name: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > MAX_ID:
        raise DraftError(f"{name} must be short text")
    return text


def get(matter_id: str, form_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    matter, form = str(matter_id or "").strip(), str(form_id or "").strip()
    if not matter or not form:
        return None
    with ops_db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT payload, updated_utc FROM form_draft_backups WHERE matter_id = ? AND form_id = ?", (matter, form)
        ).fetchone()
    if not row:
        return None
    try:
        updated = dt.datetime.fromisoformat(row[1].replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.datetime.now(dt.timezone.utc) - updated > MAX_AGE:
        with ops_db.connect(db_path) as conn:
            conn.execute("DELETE FROM form_draft_backups WHERE matter_id = ? AND form_id = ? AND updated_utc = ?", (matter, form, row[1]))
        return None
    return json.loads(row[0])


def purge_stale(*, db_path: str | Path | None = None) -> int:
    cutoff = (dt.datetime.now(dt.timezone.utc) - MAX_AGE).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with ops_db.connect(db_path) as conn:
        return conn.execute("DELETE FROM form_draft_backups WHERE updated_utc < ?", (cutoff,)).rowcount


def put(matter_id: str, form_id: str, saved_at: Any, data: Any, *, db_path: str | Path | None = None) -> None:
    matter, form = _key(matter_id, "matter_id"), _key(form_id, "form_id")
    if not MATTER_ID.match(matter):
        raise DraftError("matter_id must be a matter number")
    if data is not None:
        if isinstance(saved_at, bool) or not isinstance(saved_at, (int, float)):
            raise DraftError("savedAt must be a number")
        payload = json.dumps({"savedAt": saved_at, "data": data}, ensure_ascii=False)
        if len(payload) > MAX_PAYLOAD:
            raise DraftError("draft is too large")
    with ops_db.connect(db_path) as conn:
        if data is None:
            conn.execute("DELETE FROM form_draft_backups WHERE matter_id = ? AND form_id = ?", (matter, form))
            return
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        cutoff = (dt.datetime.now(dt.timezone.utc) - MAX_AGE).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        conn.execute("DELETE FROM form_draft_backups WHERE updated_utc < ?", (cutoff,))
        conn.execute(
            "INSERT INTO form_draft_backups (matter_id, form_id, payload, updated_utc) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(matter_id, form_id) DO UPDATE SET payload = excluded.payload, updated_utc = excluded.updated_utc",
            (matter, form, payload, now),
        )
