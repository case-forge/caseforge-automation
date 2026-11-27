#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import sys
import uuid
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db

OPS_CHANGE_LOG_EXCLUDED = {"board_overrides": "append-only record of corrections to board lines; removal sets removed_utc, nothing is deleted"}
FIELDS = ("bundle_done", "counsel_booked")
DEFAULT_DAYS = 7
MAX_DAYS = 30


def ensure_table(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS board_overrides (override_id TEXT PRIMARY KEY, hearing_id TEXT NOT NULL, matter_id TEXT NOT NULL DEFAULT '', "
        "field TEXT NOT NULL, value INTEGER NOT NULL, reason TEXT NOT NULL, by_name TEXT NOT NULL, created_utc TEXT NOT NULL, "
        "expires_utc TEXT NOT NULL, removed_utc TEXT NOT NULL DEFAULT '')"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS board_overrides_hearing ON board_overrides (hearing_id)")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _z(moment: dt.datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def add(hearing_id: Any, field: str, value: bool, reason: str, by: str, *, matter_id: Any = "", days: int = DEFAULT_DAYS, db_path: Any = None) -> str:
    if field not in FIELDS:
        raise ValueError(f"field must be one of {', '.join(FIELDS)}")
    if not str(hearing_id or "").strip():
        raise ValueError("a hearing id is required")
    if not " ".join(str(reason or "").split()):
        raise ValueError("a reason is required")
    if not " ".join(str(by or "").split()):
        raise ValueError("who is making the correction is required")
    span = max(1, min(int(days), MAX_DAYS))
    now = _now()
    override_id = uuid.uuid4().hex[:12]
    with ops_db.connect(db_path) as conn:
        ensure_table(conn)
        conn.execute(
            "UPDATE board_overrides SET removed_utc = ? WHERE hearing_id = ? AND field = ? AND removed_utc = ''",
            (_z(now), str(hearing_id), field),
        )
        conn.execute(
            "INSERT INTO board_overrides (override_id, hearing_id, matter_id, field, value, reason, by_name, created_utc, expires_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (override_id, str(hearing_id), str(matter_id or ""), field, 1 if value else 0, " ".join(str(reason).split())[:300],
             " ".join(str(by).split())[:80], _z(now), _z(now + dt.timedelta(days=span))),
        )
        conn.commit()
    return override_id


def remove(override_id: str = "", *, hearing_id: Any = "", db_path: Any = None) -> int:
    if not override_id and not str(hearing_id or "").strip():
        raise ValueError("an override id or a hearing id is required")
    with ops_db.connect(db_path) as conn:
        ensure_table(conn)
        if override_id:
            cur = conn.execute("UPDATE board_overrides SET removed_utc = ? WHERE override_id = ? AND removed_utc = ''", (_z(_now()), override_id))
        else:
            cur = conn.execute("UPDATE board_overrides SET removed_utc = ? WHERE hearing_id = ? AND removed_utc = ''", (_z(_now()), str(hearing_id)))
        conn.commit()
        return cur.rowcount


def active(*, db_path: Any = None, now: dt.datetime | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    stamp = _z(now or _now())
    with ops_db.connect(db_path) as conn:
        ensure_table(conn)
        rows = conn.execute(
            "SELECT override_id, hearing_id, field, value, reason, by_name, created_utc, expires_utc FROM board_overrides "
            "WHERE removed_utc = '' AND expires_utc > ? ORDER BY created_utc",
            (stamp,),
        ).fetchall()
    return {
        (str(r[1]), str(r[2])): {"id": r[0], "value": bool(r[3]), "reason": r[4], "by": r[5], "created_utc": r[6], "expires_utc": r[7]}
        for r in rows
    }
