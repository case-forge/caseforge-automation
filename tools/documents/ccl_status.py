#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from agents import job_queue
import ops_db

DEFAULT_INTAKE_PATH = REPO_ROOT / "telemetry" / "referralpartner-intake" / "intake.jsonl"
DEFAULT_STALE_DAYS = 7
DRAFT_JOB_TYPE = "client-care-letter"
FINALISE_JOB_TYPE = "client-care-letter-finalise"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def sha1_hex(value: str) -> str:
    return hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()


def parse_graph_dt(value: str) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def format_date_label(value: str) -> str:
    parsed = parse_graph_dt(value)
    if parsed:
        return parsed.date().isoformat()
    text = str(value or "").strip()
    return text[:10] if text else ""


def candidate_key(row: Mapping[str, Any]) -> str:
    matter_id = normalise_space(str(row.get("matter_id") or ""))
    if matter_id:
        return f"matter:{matter_id}"
    name = normalise_space(str(row.get("name") or "")).lower()
    created = normalise_space(str(row.get("created_utc") or ""))
    source = normalise_space(str(row.get("source") or row.get("referral_source") or ""))
    return "client:" + sha1_hex("|".join([name, created, source]))[:16]


def merge_new_client_rows(existing: list[dict[str, Any]], incoming: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in list(existing) + [dict(item) for item in incoming]:
        name = normalise_space(str(row.get("name") or ""))
        if not name:
            continue
        key = name.lower()
        previous = by_key.get(key)
        if previous is None or str(row.get("created_utc") or "") > str(previous.get("created_utc") or ""):
            cleaned = dict(row)
            cleaned["name"] = name
            by_key[key] = cleaned
    return list(by_key.values())


def load_recent_new_clients(days: int, limit: int, *, repo_root: Path = REPO_ROOT, intake_path: Path = DEFAULT_INTAKE_PATH) -> list[dict[str, Any]]:
    days = max(1, min(int(days or 90), 365))
    limit = max(1, min(int(limit or 10), 200))
    now = utc_now()
    cutoff_dt = now - dt.timedelta(days=days)
    cutoff_iso = cutoff_dt.isoformat().replace("+00:00", "Z")
    cutoff_date = cutoff_dt.date()
    results: list[dict[str, Any]] = []

    if intake_path.exists():
        intake_rows: list[dict[str, Any]] = []
        for raw in intake_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            name = normalise_space(str(row.get("name") or ""))
            if not name or str(row.get("status") or "") not in {"inserted", "already-in-sql"}:
                continue
            try:
                referral_date = dt.date.fromisoformat(str(row.get("referral_date") or "")[:10])
            except ValueError:
                continue
            if referral_date < cutoff_date:
                continue
            fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
            intake_rows.append(
                {
                    "name": name,
                    "matter_id": normalise_space(str(row.get("matter_id") or fields.get("matter_id") or "")),
                    "company_reference": normalise_space(str(fields.get("company_reference") or "")),
                    "orders": normalise_space(str(fields.get("order_type") or "")),
                    "referral_source": "ReferralPartner",
                    "created_utc": referral_date.isoformat(),
                    "source": "referralpartner-intake",
                }
            )
        results = merge_new_client_rows(results, intake_rows)

    try:
        from clientdb_sql import get_connection

        sqlite_mode = bool(
            os.environ.get("LOCAL_SQLITE_PATH", "").strip()
            or os.environ.get("LOCAL_SQL_CONNECTION_STRING", "").strip()
        )
        if sqlite_mode:
            sql = """
                SELECT DISTINCT
                    m.matter_id, p.canonical_name, m.company_reference,
                    m.order_requested_text, m.referral_source, m.created_utc
                FROM matters m
                JOIN people p ON m.primary_person_id = p.person_id
                WHERE COALESCE(m.created_utc, '') >= ?
                ORDER BY m.created_utc DESC
                LIMIT ?
            """
            params = (cutoff_iso, limit)
        else:
            sql = f"""
                SELECT DISTINCT TOP ({limit})
                    m.matter_id, p.canonical_name, m.company_reference,
                    m.order_requested_text, m.referral_source, m.created_utc
                FROM dbo.matters m
                JOIN dbo.people p ON m.primary_person_id = p.person_id
                WHERE COALESCE(m.created_utc, '') >= ?
                ORDER BY m.created_utc DESC
            """
            params = (cutoff_iso,)
        with get_connection() as conn:
            try:
                conn.timeout = 5
            except Exception:
                pass
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
        sql_rows = [
            {
                "matter_id": normalise_space(str(row[0] or "")),
                "name": normalise_space(str(row[1] or "")),
                "company_reference": normalise_space(str(row[2] or "")),
                "orders": normalise_space(str(row[3] or "")),
                "referral_source": normalise_space(str(row[4] or "")),
                "created_utc": normalise_space(str(row[5] or "")),
                "source": "sql",
            }
            for row in rows
            if normalise_space(str(row[1] or ""))
        ]
        results = merge_new_client_rows(results, sql_rows)
    except Exception as exc:
        print(f"load_recent_new_clients: SQL lookup failed ({type(exc).__name__}: {exc})", file=sys.stderr)

    return sorted(results, key=lambda row: str(row.get("created_utc") or ""), reverse=True)[:limit]


def _job_client_key(job: Mapping[str, Any]) -> tuple[str, str]:
    payload = job.get("payload") if isinstance(job.get("payload"), Mapping) else {}
    matter_id = normalise_space(str(job.get("matter_id") or payload.get("matter_id") or ""))
    client_name = normalise_space(str(payload.get("client_name") or payload.get("client") or ""))
    return matter_id.lower(), client_name.lower()


def _job_status_rank(job: Mapping[str, Any]) -> tuple[int, str]:
    job_type = str(job.get("job_type") or "")
    status = str(job.get("status") or "")
    type_rank = 2 if job_type == FINALISE_JOB_TYPE else 1 if job_type == DRAFT_JOB_TYPE else 0
    active_rank = {
        "running": 5,
        "waiting_approval": 4,
        "queued": 3,
        "blocked": 2,
        "failed": 2,
        "done": 1,
        "cancelled": 0,
    }.get(status, 0)
    return type_rank, f"{active_rank}:{str(job.get('updated_utc') or job.get('created_utc') or '')}"


def _ccl_status_from_job(job: Mapping[str, Any] | None) -> tuple[str, str]:
    if not job:
        return "candidate", "candidate"
    job_type = str(job.get("job_type") or "")
    status = str(job.get("status") or "")
    if job_type == FINALISE_JOB_TYPE:
        return {
            "queued": ("finalise_queued", "finalise queued"),
            "running": ("finalising", "finalising"),
            "waiting_approval": ("finalise_waiting", "finalise waiting"),
            "blocked": ("finalise_blocked", "finalise blocked"),
            "failed": ("finalise_failed", "finalise failed"),
            "done": ("email_ready", "email ready"),
            "cancelled": ("finalise_cancelled", "finalise cancelled"),
        }.get(status, ("finalise_unknown", status or "finalise"))
    if job_type == DRAFT_JOB_TYPE:
        return {
            "queued": ("draft_queued", "draft queued"),
            "running": ("draft_running", "draft running"),
            "waiting_approval": ("draft_waiting", "draft waiting"),
            "blocked": ("draft_blocked", "draft blocked"),
            "failed": ("draft_failed", "draft failed"),
            "done": ("draft_ready", "draft ready"),
            "cancelled": ("draft_cancelled", "draft cancelled"),
        }.get(status, ("draft_unknown", status or "draft"))
    return "candidate", "candidate"


def latest_ccl_jobs_by_client(*, db_path: str | Path | None = None, limit: int = 200) -> dict[tuple[str, str], dict[str, Any]]:
    try:
        jobs = job_queue.list_jobs(limit=max(1, min(int(limit or 200), 200)), db_path=db_path)
    except Exception:
        return {}
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for job in jobs:
        if str(job.get("job_type") or "") not in {DRAFT_JOB_TYPE, FINALISE_JOB_TYPE}:
            continue
        matter_key, client_key = _job_client_key(job)
        keys = []
        if matter_key:
            keys.append((matter_key, ""))
        if client_key:
            keys.append(("", client_key))
        if matter_key or client_key:
            keys.append((matter_key, client_key))
        for key in keys:
            previous = latest.get(key)
            if previous is None or _job_status_rank(job) >= _job_status_rank(previous):
                latest[key] = dict(job)
    return latest


def load_client_care_letter_status_rows(
    days: int = 90,
    limit: int = 10,
    *,
    repo_root: Path = REPO_ROOT,
    intake_path: Path = DEFAULT_INTAKE_PATH,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    rows = load_recent_new_clients(days, limit, repo_root=repo_root, intake_path=intake_path)
    latest_jobs = latest_ccl_jobs_by_client(db_path=db_path)
    status_rows: list[dict[str, Any]] = []
    for row in rows:
        matter_key = normalise_space(str(row.get("matter_id") or "")).lower()
        client_key = normalise_space(str(row.get("name") or "")).lower()
        job = (
            latest_jobs.get((matter_key, client_key))
            or latest_jobs.get((matter_key, ""))
            or latest_jobs.get(("", client_key))
        )
        status, status_label = _ccl_status_from_job(job)
        key = candidate_key(row)
        meta_bits = [
            format_date_label(str(row.get("created_utc") or "")),
            normalise_space(str(row.get("orders") or "")),
            normalise_space(str(row.get("referral_source") or row.get("source") or "")),
            status_label,
        ]
        label = normalise_space(str(row.get("name") or ""))
        meta = " | ".join(bit for bit in meta_bits if bit)
        if meta:
            label = f"{label} - {meta}"
        status_rows.append(
            {
                **row,
                "candidate_key": key,
                "ccl_status": status,
                "ccl_status_label": status_label,
                "ccl_job_id": str((job or {}).get("job_id") or ""),
                "ccl_job_type": str((job or {}).get("job_type") or ""),
                "ccl_job_status": str((job or {}).get("status") or ""),
                "ccl_updated_utc": str((job or {}).get("updated_utc") or ""),
                "label": label,
            }
        )
    return status_rows


def indexed_drive_item_for_word(word_item_id: str, *, db_path: str | Path | None = None) -> dict[str, str]:
    item_id = normalise_space(word_item_id)
    if not item_id:
        return {}
    try:
        with ops_db.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT drive_id, item_id, path, name
                FROM onedrive_items
                WHERE item_id = ?
                LIMIT 1
                """,
                (item_id,),
            ).fetchone()
    except Exception:
        return {}
    if row is None:
        return {}
    data = dict(row)
    return {key: normalise_space(str(data.get(key) or "")) for key in ("drive_id", "item_id", "path", "name")}
