#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Iterable

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

DIRECTIONS = ("prev", "next")


def _hidden_ids() -> set[str]:
    from onboarding import client_removal

    return client_removal.hidden_ids()


def _query(sql: str, params: tuple) -> list[tuple]:
    import clientdb_sql

    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def neighbour(
    matter_id: int,
    direction: str,
    *,
    hidden: Iterable[str] | None = None,
    query: Callable[[str, tuple], list[tuple]] | None = None,
) -> str | None:
    if direction not in DIRECTIONS:
        raise ValueError("dir must be prev or next")
    current = int(matter_id)
    skip = {str(h).strip() for h in (_hidden_ids() if hidden is None else hidden)}
    before = direction == "prev"
    in_the_way = sum(1 for h in skip if h.isdigit() and (int(h) < current if before else int(h) > current))
    op, order = ("<", "DESC") if before else (">", "ASC")
    rows = (query or _query)(
        f"SELECT matter_id FROM dbo.matters WHERE matter_id {op} ? ORDER BY matter_id {order} LIMIT ?",
        (current, in_the_way + 1),
    )
    for row in rows:
        candidate = str(row[0]).strip()
        if candidate and candidate not in skip:
            return candidate
    return None
