#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from typing import Any

import ops_db

TITLE_MAX = 120
DETAIL_MAX = 500

_COLUMNS = "notice_id, kind, title, detail, matter_id, client_name, dedupe_key, created_utc"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _row(row: tuple) -> dict[str, Any]:
    notice_id, kind, title, detail, matter_id, client_name, dedupe_key, created_utc = row
    return {
        "notice_id": notice_id,
        "kind": kind,
        "title": title,
        "detail": detail,
        "matter_id": matter_id,
        "client_name": client_name,
        "dedupe_key": dedupe_key,
        "created_utc": created_utc,
    }


def add(
    kind: str,
    title: str,
    detail: str = "",
    *,
    matter_id: str = "",
    client_name: str = "",
    dedupe_key: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    kind, title = str(kind or "").strip(), str(title or "").strip()
    if not kind or not title:
        raise ValueError("a robot notice needs a kind and a title")
    key = str(dedupe_key or "").strip()
    with ops_db.connect(db_path) as conn:
        if key:
            existing = conn.execute(
                f"SELECT {_COLUMNS} FROM robot_notices WHERE dedupe_key = ? AND resolved_utc IS NULL", (key,)
            ).fetchone()
            if existing:
                return _row(existing)
        notice_id = uuid.uuid4().hex
        cursor = conn.execute(
            "INSERT OR IGNORE INTO robot_notices (notice_id, kind, title, detail, matter_id, client_name, dedupe_key, created_utc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                notice_id,
                kind,
                title[:TITLE_MAX],
                str(detail or "")[:DETAIL_MAX],
                str(matter_id or "").strip(),
                str(client_name or "").strip()[:120],
                key,
                _now(),
            ),
        )
        conn.commit()
        if cursor.rowcount == 0 and key:
            row = conn.execute(f"SELECT {_COLUMNS} FROM robot_notices WHERE dedupe_key = ? AND resolved_utc IS NULL", (key,)).fetchone()
        else:
            row = conn.execute(f"SELECT {_COLUMNS} FROM robot_notices WHERE notice_id = ?", (notice_id,)).fetchone()
    return _row(row)


def list_open(*, limit: int = 100, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with ops_db.connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM robot_notices WHERE resolved_utc IS NULL ORDER BY created_utc DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [_row(r) for r in rows]


def list_resolved(*, limit: int = 100, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with ops_db.connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS}, resolved_utc, resolved_by FROM robot_notices WHERE resolved_utc IS NOT NULL "
            "ORDER BY resolved_utc DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [{**_row(r[:8]), "resolved_utc": r[8], "resolved_by": r[9]} for r in rows]


def get(notice_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with ops_db.connect(db_path) as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM robot_notices WHERE notice_id = ?", (str(notice_id),)).fetchone()
    return _row(row) if row else None


def open_for(matter_id: str, kind: str, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with ops_db.connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM robot_notices WHERE matter_id = ? AND kind = ? AND resolved_utc IS NULL",
            (str(matter_id or "").strip(), str(kind or "")),
        ).fetchall()
    return [_row(r) for r in rows]


def ever_raised(dedupe_key: str, *, db_path: str | Path | None = None) -> bool:
    key = str(dedupe_key or "").strip()
    if not key:
        return False
    with ops_db.connect(db_path) as conn:
        return conn.execute("SELECT 1 FROM robot_notices WHERE dedupe_key = ? LIMIT 1", (key,)).fetchone() is not None


def count_open(*, db_path: str | Path | None = None) -> int:
    with ops_db.connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM robot_notices WHERE resolved_utc IS NULL").fetchone()[0])


def dismiss(notice_id: str, by: str = "", *, db_path: str | Path | None = None) -> bool:
    with ops_db.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE robot_notices SET resolved_utc = ?, resolved_by = ? WHERE notice_id = ? AND resolved_utc IS NULL",
            (_now(), str(by or "").strip()[:80] or "person", str(notice_id)),
        )
        conn.commit()
        return cursor.rowcount == 1


def resolve(dedupe_key: str, *, db_path: str | Path | None = None) -> int:
    key = str(dedupe_key or "").strip()
    if not key:
        return 0
    with ops_db.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE robot_notices SET resolved_utc = ?, resolved_by = 'robot' WHERE dedupe_key = ? AND resolved_utc IS NULL",
            (_now(), key),
        )
        conn.commit()
        return cursor.rowcount
