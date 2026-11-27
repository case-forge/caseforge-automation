from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import clientdb_sql


INTAKE_SOURCE = "referrer email intro"
WINDOW_DAYS = 14
LIST_LIMIT = 25


def list_recent(*, days: int = WINDOW_DAYS, limit: int = LIST_LIMIT, db_path: str | Path | None = None) -> dict[str, Any]:
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat().replace("+00:00", "Z")
    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT matter_id, canonical_name, created_utc FROM dbo.matters "
            "WHERE closed_at IS NULL AND intake_source = ? AND created_utc >= ? ORDER BY created_utc DESC",
            (INTAKE_SOURCE, since),
        )
        rows = [(str(r[0]), str(r[1] or ""), str(r[2] or "")) for r in cur.fetchall()]
    from onboarding import client_removal

    rows = client_removal.visible_rows(rows, matter_id_of=lambda r: r[0], db_path=db_path)
    items = [
        {
            "matter_id": mid,
            "client_name": name,
            "created_utc": created,
        }
        for mid, name, created in rows
    ]
    return {"total": len(items), "items": items[:limit]}
