from __future__ import annotations

import datetime as dt
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ops_db

WORK_TYPES: tuple[str, ...] = (
    "opening_letter",
    "attendance_note",
    "closing_letter",
    "court_outcome_letter",
    "notice_of_acting",
    "statement_of_service",
    "fl401",
    "bundle",
    "brief_to_counsel",
    "legal_aid_signing",
    "letterhead",
)

STATUSES: tuple[str, ...] = ("completed", "draft", "superseded")

COLUMNS = (
    "work_id", "matter_id", "work_type", "status", "performed_by", "performed_on_host",
    "occurred_at", "reference", "artefact_url", "notes", "created_at", "updated_at",
)


class WorkLogError(ValueError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _clean(value: Any, *, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def record_work(
    *,
    matter_id: str,
    work_type: str,
    performed_by: str = "",
    performed_on_host: str = "",
    status: str = "completed",
    reference: str = "",
    artefact_url: str = "",
    notes: str = "",
    occurred_at: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        raise WorkLogError("matter_id is required")
    if work_type not in WORK_TYPES:
        raise WorkLogError(f"unknown work_type {work_type!r}; expected one of {WORK_TYPES}")
    if status not in STATUSES:
        raise WorkLogError(f"unknown status {status!r}; expected one of {STATUSES}")

    now = utc_now()
    row = {
        "work_id": uuid.uuid4().hex,
        "matter_id": matter,
        "work_type": work_type,
        "status": status,
        "performed_by": _clean(performed_by, limit=128),
        "performed_on_host": _clean(performed_on_host, limit=128),
        "occurred_at": _clean(occurred_at, limit=64) or now,
        "reference": _clean(reference, limit=128),
        "artefact_url": _clean(artefact_url, limit=1000),
        "notes": _clean(notes, limit=2000),
        "created_at": now,
        "updated_at": now,
    }
    with ops_db.connect(db_path) as conn:
        conn.execute(
            f"INSERT INTO matter_work_log ({', '.join(COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in COLUMNS)})",
            tuple(row[col] for col in COLUMNS),
        )
    return row


def list_work(
    matter_id: str,
    *,
    work_type: str = "",
    include_superseded: bool = False,
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        return []
    clauses = ["matter_id = ?"]
    params: list[Any] = [matter]
    if work_type:
        clauses.append("work_type = ?")
        params.append(work_type)
    if not include_superseded:
        clauses.append("status <> 'superseded'")
    params.append(max(1, min(int(limit or 50), 500)))
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM matter_work_log "
            f"WHERE {' AND '.join(clauses)} ORDER BY occurred_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    return [dict(zip(COLUMNS, row)) for row in rows]


def work_summary(
    matter_id: str,
    *,
    db_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for row in list_work(matter_id, limit=500, db_path=db_path):
        entry = summary.setdefault(
            row["work_type"], {"count": 0, "latest": "", "status": "", "by": ""}
        )
        entry["count"] += 1
        if str(row["occurred_at"]) > str(entry["latest"]):
            entry["latest"] = row["occurred_at"]
            entry["status"] = row["status"]
            entry["by"] = row["performed_by"]
    return summary


def has_work(
    matter_id: str,
    work_type: str,
    *,
    since: str = "",
    db_path: str | Path | None = None,
) -> bool:
    rows = list_work(matter_id, work_type=work_type, limit=500, db_path=db_path)
    if not since:
        return bool(rows)
    return any(str(row["occurred_at"]) >= since for row in rows)


def supersede(work_id: str, *, db_path: str | Path | None = None) -> bool:
    identifier = _clean(work_id, limit=64)
    if not identifier:
        return False
    with ops_db.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE matter_work_log SET status = 'superseded', updated_at = ? WHERE work_id = ?",
            (utc_now(), identifier),
        )
        return bool(cursor.rowcount)


def recent_work(
    *,
    since: str = "",
    work_types: Iterable[str] = (),
    limit: int = 200,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    clauses = ["status <> 'superseded'"]
    params: list[Any] = []
    if since:
        clauses.append("occurred_at >= ?")
        params.append(_clean(since, limit=64))
    types = [t for t in work_types if t in WORK_TYPES]
    if types:
        clauses.append(f"work_type IN ({', '.join('?' for _ in types)})")
        params.extend(types)
    params.append(max(1, min(int(limit or 200), 1000)))
    with ops_db.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM matter_work_log "
            f"WHERE {' AND '.join(clauses)} ORDER BY occurred_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    return [dict(zip(COLUMNS, row)) for row in rows]
