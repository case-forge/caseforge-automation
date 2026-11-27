#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db

MAX_DRAFTS = 30
MAX_TEXT = 100_000
MAX_SHORT = 200
KINDS = ("call", "perusal", "preparation", "letter_out", "letter_in")


class BackupError(ValueError):
    pass


def _short(value: Any, name: str) -> str:
    text = str(value if value is not None else "")
    if not isinstance(value, (str, type(None))) or len(text) > MAX_SHORT:
        raise BackupError(f"{name} must be short text")
    return text


def _form(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise BackupError("a note must be an object")
    note = value.get("noteText", "")
    if not isinstance(note, str) or len(note) > MAX_TEXT:
        raise BackupError("noteText must be text of at most 100,000 characters")
    kind = value.get("kind") or "call"
    if kind == "bundle":
        kind = "call"
    if kind not in KINDS:
        raise BackupError("kind is not a note type")
    return {"caller": _short(value.get("caller"), "caller"), "callerOther": _short(value.get("callerOther"), "callerOther"), "noteText": note, "kind": kind}


def _is_blank(form: dict[str, str]) -> bool:
    return not form["caller"] and not form["callerOther"].strip() and not form["noteText"].strip() and form["kind"] == "call"


def _draft(value: Any) -> dict[str, str]:
    form = _form(value)
    return {"id": _short(value.get("id"), "id"), "savedAt": _short(value.get("savedAt"), "savedAt"), **form}


def get(matter_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    matter = str(matter_id or "").strip()
    if not matter:
        return None
    with ops_db.connect(db_path) as conn:
        row = conn.execute("SELECT payload FROM an_backups WHERE matter_id = ?", (matter,)).fetchone()
    return json.loads(row[0]) if row else None


def put(matter_id: str, working: Any, drafts: Any, *, db_path: str | Path | None = None) -> None:
    matter = str(matter_id or "").strip()
    if not matter:
        raise BackupError("matter_id is required")
    if not (matter.isdigit() and len(matter) <= 20):
        raise BackupError("matter_id must be a matter number")
    if not isinstance(drafts, list) or len(drafts) > MAX_DRAFTS:
        raise BackupError(f"drafts must be a list of at most {MAX_DRAFTS}")
    clean_working = None if working is None else _form(working)
    if clean_working is not None and _is_blank(clean_working):
        clean_working = None
    clean_drafts = [_draft(draft) for draft in drafts]
    with ops_db.connect(db_path) as conn:
        if clean_working is None and not clean_drafts:
            conn.execute("DELETE FROM an_backups WHERE matter_id = ?", (matter,))
            return
        payload = json.dumps({"working": clean_working, "drafts": clean_drafts}, ensure_ascii=False)
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        conn.execute(
            "INSERT INTO an_backups (matter_id, payload, updated_utc) VALUES (?, ?, ?) "
            "ON CONFLICT(matter_id) DO UPDATE SET payload = excluded.payload, updated_utc = excluded.updated_utc",
            (matter, payload, now),
        )
