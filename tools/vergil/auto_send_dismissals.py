from __future__ import annotations

from pathlib import Path
from typing import Any

import ops_db

MAX_ID_LENGTH = 300
LEAVING_SOON = "leaving_soon"


def load_items() -> list[dict[str, Any]]:
    from vergil import auto_send_items

    return auto_send_items.load_items()


def clean_id(item_id: str) -> str:
    text = str(item_id or "").strip()
    if not text or len(text) > MAX_ID_LENGTH or any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ValueError("item id must be 1 to 300 characters with no control characters")
    return text


def dismiss(item_id: str, by: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    iid = clean_id(item_id)
    name = " ".join(str(by or "").split())[:80]
    if not name:
        raise ValueError("the person dismissing must be named")
    with ops_db.connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO pipeline_auto_send_dismissals (item_id, dismissed_by, dismissed_utc) VALUES (?, ?, ?)",
            (iid, name, ops_db.utc_now_z()),
        )
        row = conn.execute(
            "SELECT dismissed_by, dismissed_utc FROM pipeline_auto_send_dismissals WHERE item_id = ?", (iid,)
        ).fetchone()
    return {"ok": True, "id": iid, "dismissed_by": row[0], "dismissed_utc": row[1]}


def dismissed_ids(*, db_path: str | Path | None = None) -> set[str]:
    with ops_db.connect(db_path) as conn:
        return {str(r[0]) for r in conn.execute("SELECT item_id FROM pipeline_auto_send_dismissals")}


def filter_items(items: list[dict[str, Any]], *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    gone = dismissed_ids(db_path=db_path)
    return [i for i in items if str(i.get("id", "")) not in gone]


def state_of(item_id: str, items: list[dict[str, Any]]) -> str:
    for i in items:
        if str(i.get("id", "")) == item_id:
            return str(i.get("state", ""))
    return ""
