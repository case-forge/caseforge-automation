from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Any

DEBOUNCE_MINUTES = 10
RECENT_LIMIT = 5


def _iso(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now(now: dt.datetime | None) -> dt.datetime:
    return now or dt.datetime.now(dt.timezone.utc)


def record(conn: sqlite3.Connection, matter_id: str, viewer: str, *, now: dt.datetime | None = None) -> bool:
    mid, who = str(matter_id or "").strip(), str(viewer or "").strip()
    if not mid or not who:
        return False
    moment = _now(now)
    cutoff = _iso(moment - dt.timedelta(minutes=DEBOUNCE_MINUTES))
    if conn.execute(
        "SELECT 1 FROM activity_log_views WHERE matter_id = ? AND viewer = ? AND viewed_utc > ? LIMIT 1", (mid, who, cutoff)
    ).fetchone():
        return False
    conn.execute("INSERT INTO activity_log_views (matter_id, viewer, viewed_utc) VALUES (?, ?, ?)", (mid, who, _iso(moment)))
    conn.commit()
    return True


def recent(conn: sqlite3.Connection, matter_id: str, *, exclude: str = "", limit: int = RECENT_LIMIT) -> list[dict[str, str]]:
    rows = conn.execute(
        "SELECT viewer, MAX(viewed_utc) AS latest FROM activity_log_views WHERE matter_id = ? AND viewer <> ? "
        "GROUP BY viewer ORDER BY latest DESC LIMIT ?",
        (str(matter_id or "").strip(), str(exclude or ""), max(1, int(limit))),
    ).fetchall()
    return [{"who": str(who), "at": str(at)} for who, at in rows]


def trail_rows(conn: sqlite3.Connection, since: str, until: str) -> list[dict[str, Any]]:
    try:
        found = conn.execute(
            "SELECT view_id, matter_id, viewer, viewed_utc FROM activity_log_views WHERE viewed_utc >= ? AND viewed_utc <= ? "
            "ORDER BY viewed_utc DESC",
            (since, until),
        ).fetchall()
    except sqlite3.Error:
        return []
    out: list[dict[str, Any]] = []
    for view_id, matter_id, viewer, viewed in found:
        try:
            when = dt.datetime.fromisoformat(str(viewed).replace("Z", "+00:00")).astimezone(dt.timezone.utc)
        except ValueError:
            when = None
        out.append({
            "id": f"view:{view_id}", "at": str(viewed)[:19] + "Z", "kind": "person", "who": viewer, "area": "view",
            "action": "Opened the Activity log", "what": "", "from": "", "to": "", "where": f"Matter {matter_id}", "ip": "",
            "seen_by": ["ours"], "matter_id": str(matter_id), "_hash": "", "_op": "", "_when": when,
        })
    return out
