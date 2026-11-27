from __future__ import annotations

import datetime as dt
import json
from typing import Any, Callable

from mail_blocked_reasons import QUEUE_LABEL, blocked_reason_label
from vergil.primitives import REPO_ROOT

SEEN_PATH = REPO_ROOT / "telemetry" / "caseforge-chat" / "notifications-seen.json"

FINISHED_JOB_STATUSES = frozenset({"done", "failed", "blocked", "cancelled"})

SEVERITY_ORDER = {"red": 0, "error": 0, "amber": 1, "warning": 1, "info": 2, "success": 3}

DEFAULT_LIMIT = 25


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_stamp(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _read_seen() -> dict[str, str]:
    try:
        payload = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k): str(v) for k, v in payload.items()} if isinstance(payload, dict) else {}


def last_seen(username: str) -> dt.datetime | None:
    return parse_stamp(_read_seen().get(str(username or "").strip()))


def mark_seen(username: str, *, when: dt.datetime | None = None) -> None:
    name = str(username or "").strip()
    if not name:
        return
    stamp = (when or _now()).astimezone(dt.timezone.utc)
    seen = _read_seen()
    seen[name] = stamp.isoformat().replace("+00:00", "Z")
    try:
        SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        from atomic_json import atomic_write_json
        atomic_write_json(SEEN_PATH, seen, indent=1, sort_keys=True)
    except OSError:
        return


def _job_notification(job: dict, describe: Callable[[dict], str], link_for: Callable[[dict], str]) -> dict | None:
    status = str(job.get("status") or "").strip().lower()
    if status not in FINISHED_JOB_STATUSES:
        return None
    stamp = parse_stamp(job.get("updated_utc") or job.get("created_utc"))
    if stamp is None:
        return None
    job_type = str(job.get("job_type") or "job")
    subject = describe(job)
    headline = f"{job_type} {status}"
    if subject:
        headline = f"{job_type} {status}: {subject}"
    severity = {"done": "success", "failed": "error", "blocked": "warning"}.get(status, "info")
    return {
        "id": f"job:{job.get('job_id') or ''}:{status}",
        "kind": "job",
        "severity": severity,
        "text": headline,
        "detail": "",
        "timestamp": stamp,
        "link": link_for(job),
    }


def job_notifications(
    jobs: list[dict],
    *,
    describe: Callable[[dict], str],
    link_for: Callable[[dict], str],
) -> list[dict]:
    items = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        item = _job_notification(job, describe, link_for)
        if item is not None:
            items.append(item)
    return items


def manual_review_notifications(items: list[dict], *, timestamp_for: Callable[[dict], Any]) -> list[dict]:
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        stamp = timestamp_for(item)
        if stamp is None:
            continue
        source = str(item.get("source") or "manual review").replace("_", " ")
        reason = " ".join(str(item.get("reason") or item.get("error") or "Review required").split())
        why = blocked_reason_label(reason)
        out.append({
            "id": f"review:{item.get('id') or item.get('message_id') or reason[:40]}",
            "kind": "review",
            "severity": "warning",
            "text": f"{QUEUE_LABEL} ({source})",
            "detail": (f"{why}: {reason}" if why else reason)[:200],
            "timestamp": stamp,
            "link": str(item.get("webLink") or "").strip(),
        })
    return out


def supervisor_notifications(payload: dict, *, limit: int = 5) -> list[dict]:
    alerts = [item for item in (payload.get("alerts") or []) if isinstance(item, dict)]
    if not alerts:
        return []
    stamp = parse_stamp(payload.get("generated_at")) or _now()
    out = []
    for alert in alerts[: max(1, int(limit or 5))]:
        severity = str(alert.get("severity") or "info").strip().lower()
        title = " ".join(str(alert.get("title") or "Operational alert").split())
        out.append({
            "id": f"supervisor:{alert.get('key') or title}",
            "kind": "supervisor",
            "severity": severity,
            "text": title,
            "detail": " ".join(str(alert.get("summary") or "").split())[:200],
            "timestamp": stamp,
            "link": "",
        })
    return out


def sort_notifications(items: list[dict], *, limit: int = DEFAULT_LIMIT) -> list[dict]:
    floor = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    ordered = sorted(
        items,
        key=lambda item: (
            item.get("timestamp") or floor,
            -SEVERITY_ORDER.get(str(item.get("severity") or "info"), 9),
        ),
        reverse=True,
    )
    return ordered[: max(1, int(limit or DEFAULT_LIMIT))]


def collect(
    *,
    jobs: Callable[[], list[dict]],
    describe: Callable[[dict], str],
    link_for: Callable[[dict], str],
    review_items: Callable[[], list[dict]],
    review_timestamp: Callable[[dict], Any],
    supervisor: Callable[[], dict],
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    items: list[dict] = []
    try:
        items.extend(job_notifications(jobs(), describe=describe, link_for=link_for))
    except Exception:
        pass
    try:
        items.extend(manual_review_notifications(review_items(), timestamp_for=review_timestamp))
    except Exception:
        pass
    try:
        items.extend(supervisor_notifications(supervisor()))
    except Exception:
        pass
    return sort_notifications(items, limit=limit)


def unseen(items: list[dict], seen_at: dt.datetime | None) -> list[dict]:
    if seen_at is None:
        return list(items)
    return [item for item in items if (item.get("timestamp") or seen_at) > seen_at]
