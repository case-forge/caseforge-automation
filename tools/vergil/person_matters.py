#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import clientdb_sql


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def sibling_matter_ids(matter_id: str) -> list[str]:
    matter_id = clean_text(matter_id)
    if not matter_id:
        return []
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT primary_person_id FROM matters WHERE matter_id = ?", (matter_id,))
        row = cursor.fetchone()
        if row is None or row[0] is None:
            return []
        cursor.execute(
            "SELECT matter_id FROM matters WHERE primary_person_id = ? ORDER BY matter_id",
            (row[0],),
        )
        return [clean_text(r[0]) for r in cursor.fetchall()]


def person_matters(matter_id: str) -> dict[str, Any]:
    matter_id = clean_text(matter_id)
    rows: list[dict[str, Any]] = []
    for sibling_id in sibling_matter_ids(matter_id):
        row = clientdb_sql.get_client_by_matter_id(sibling_id)
        if row:
            rows.append(row)
    return {"matter_id": matter_id, "matters": rows}
