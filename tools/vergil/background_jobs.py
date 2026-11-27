from __future__ import annotations

import datetime as dt
import sys

from vergil.primitives import REPO_ROOT


def agent_queue_module():
    tools_dir = REPO_ROOT / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from agents import job_queue

    return job_queue


def enqueue_order_intake_job(username: str, payload: dict) -> tuple[bool, str]:
    try:
        job_queue = agent_queue_module()
        job, created = job_queue.enqueue_job(
            "order-intake",
            payload,
            created_user=username,
            idempotency_key=str(payload.get("idempotency_key") or ""),
        )
        verb = "Queued" if created else "Already queued"
        return True, f"{verb} order-intake job {str(job.get('job_id', ''))[:8]}"
    except Exception as exc:
        return False, f"Order intake queue failed: {exc}"


def enqueue_email_print_job(username: str, payload: dict) -> tuple[bool, str]:
    try:
        job_queue = agent_queue_module()
        idempotency_key = str(payload.get("idempotency_key") or "")
        job, created = job_queue.enqueue_job(
            "email-print-archive",
            payload,
            created_user=username,
            idempotency_key=idempotency_key,
        )
        verb = "Queued" if created else "Already queued"
        return True, f"{verb} email archive job {str(job.get('job_id', ''))[:8]}"
    except Exception as exc:
        return False, f"Email archive queue failed: {exc}"


def ccl_status_module():
    tools_dir = REPO_ROOT / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from documents import ccl_status

    return ccl_status


def client_care_letter_matter_id(client_name: str) -> str:
    wanted = " ".join(str(client_name or "").split()).casefold()
    if not wanted:
        return ""
    try:
        queue = ccl_status_module()
        for row in queue.load_client_care_letter_status_rows(days=180, limit=200):
            if " ".join(str(row.get("name") or "").split()).casefold() == wanted:
                return " ".join(str(row.get("matter_id") or "").split())
    except Exception:
        pass
    return ""


CCL_USE_CASEFLOW_MESSAGE = (
    "Client care letters are made in Caseflow: open the client in the client viewer, go to "
    "the Case Flow tab and use the client care letter step."
)


def enqueue_client_care_letter_job(username: str, client_name: str) -> tuple[bool, str]:
    return False, CCL_USE_CASEFLOW_MESSAGE


CLIENT_CARE_LETTER_JOB_TYPES = ("client-care-letter", "client-care-letter-finalise")

ON_DEMAND_JOB_TYPES = (
    "client-care-letter",
    "client-care-letter-finalise",
    "email-print-archive",
    "calendar-finder",
    "order-intake",
    "sos-to-court-draft",
)

TERMINAL_JOB_STATUSES = frozenset({"done", "failed", "blocked", "cancelled"})


def on_demand_jobs(limit: int = 40) -> list[dict]:
    job_queue = agent_queue_module()
    return job_queue.list_jobs(job_types=ON_DEMAND_JOB_TYPES, limit=max(1, int(limit or 40)))


def background_queue_jobs(limit: int = 40) -> list[dict]:
    job_queue = agent_queue_module()
    return job_queue.list_jobs(exclude_job_types=ON_DEMAND_JOB_TYPES, limit=max(1, int(limit or 40)))


def job_subject(job: dict) -> str:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    for key in ("client_name", "client", "matter_id", "subject"):
        value = " ".join(str(payload.get(key) or "").split())
        if value:
            return value
    nested = payload.get("ai_exp_target") if isinstance(payload.get("ai_exp_target"), dict) else {}
    for key in ("client_name", "matter_id"):
        value = " ".join(str((nested or {}).get(key) or "").split())
        if value:
            return value
    return " ".join(str(job.get("matter_id") or "").split())


def job_outcome_text(job: dict) -> str:
    blocker = " ".join(str(job.get("blocker_text") or "").split())
    error = " ".join(str(job.get("error_text") or "").split())
    state = job.get("state") if isinstance(job.get("state"), dict) else {}
    notice = " ".join(
        str(
            (state or {}).get("review_notice")
            or ((state or {}).get("recommendation") or {}).get("review_notice")
            or ""
        ).split()
    )
    for candidate in (blocker, error, notice):
        if candidate:
            return candidate
    return ""


def job_result_link(job: dict) -> str:
    state = job.get("state") if isinstance(job.get("state"), dict) else {}
    for key in ("word_url", "result_url"):
        value = str((state or {}).get(key) or "").strip()
        if value:
            return value
    return ""


def job_age_label(job: dict, *, now: dt.datetime | None = None) -> str:
    stamp = str(
        job.get("updated_utc") or job.get("started_utc") or job.get("created_utc") or ""
    )
    return elapsed_label(stamp, now)


def job_status_counts(jobs: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        status = str(job.get("status") or "unknown").strip().lower() or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def recent_client_care_letter_jobs(limit: int = 6) -> list[dict]:
    job_queue = agent_queue_module()
    jobs = job_queue.list_jobs(limit=max(1, int(limit or 6)) * 8)
    picked = [
        job
        for job in jobs
        if isinstance(job, dict) and str(job.get("job_type") or "") in CLIENT_CARE_LETTER_JOB_TYPES
    ]
    return picked[: max(1, int(limit or 6))]


def elapsed_label(since: str, now: dt.datetime | None = None) -> str:
    started = None
    text = str(since or "").strip()
    if text:
        try:
            started = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            started = None
    if started is None:
        return ""
    if started.tzinfo is None:
        started = started.replace(tzinfo=dt.timezone.utc)
    seconds = int(((now or dt.datetime.now(dt.timezone.utc)) - started).total_seconds())
    if seconds < 0:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 172800:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d"


_elapsed_label = elapsed_label


def client_care_letter_job_line(job: dict, *, now: dt.datetime | None = None) -> str:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    client = " ".join(str(payload.get("client_name") or "").split()) or "(unknown client)"
    status = str(job.get("status") or "").strip().lower()
    finalise = str(job.get("job_type") or "") == "client-care-letter-finalise"
    stage = "finalise" if finalise else "draft"
    if status == "queued":
        waited = _elapsed_label(str(job.get("created_utc") or ""), now)
        return f"{client} - {stage} queued" + (f", waiting {waited}" if waited else "")
    if status == "running":
        elapsed = _elapsed_label(str(job.get("started_utc") or job.get("created_utc") or ""), now)
        return f"{client} - {stage} running{f' for {elapsed}' if elapsed else ''}"
    if status == "done":
        return f"{client} - {stage} done"
    if status in {"blocked", "failed"}:
        reason = " ".join(
            str(job.get("blocker_text") or job.get("error_text") or "").split()
        )
        label = "blocked" if status == "blocked" else "failed"
        return f"{client} - {stage} {label}" + (f": {reason[:120]}" if reason else "")
    if status == "cancelled":
        return f"{client} - {stage} cancelled"
    return f"{client} - {stage} {status or 'unknown'}"


def client_care_letter_job_link(job: dict) -> str:
    state = job.get("state") if isinstance(job.get("state"), dict) else {}
    return str((state or {}).get("word_url") or "").strip()


def enqueue_calendar_finder_job(username: str, payload: dict) -> tuple[bool, str]:
    try:
        job_queue = agent_queue_module()
        job, created = job_queue.enqueue_job(
            "calendar-finder",
            payload,
            created_user=username,
            idempotency_key=str(payload.get("idempotency_key") or ""),
        )
        verb = "Queued" if created else "Already queued"
        return True, f"{verb} calendar check {str(job.get('job_id', ''))[:8]}"
    except Exception as exc:
        return False, f"Calendar check queue failed: {exc}"


def email_archive_payload(client: str, *, since_days: int, dry_run: bool, document_mode: str = "") -> dict:
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    mode = str(document_mode or "").strip()
    return {
        "client": client,
        "since_days": int(since_days),
        "dry_run": bool(dry_run),
        "source": "caseforge-chat",
        "check_existing": True,
        "document_mode": mode,
        "idempotency_key": f"email-print-archive:{today}:{client.lower()}:{int(since_days)}:{int(bool(dry_run))}:{mode or 'standard'}",
    }


def queue_email_archive_download(
    username: str,
    queue: list[str],
    *,
    since_days: int,
    dry_run: bool,
    document_mode: str = "",
) -> str:
    messages: list[str] = []
    for client in queue:
        payload = email_archive_payload(client, since_days=since_days, dry_run=dry_run, document_mode=document_mode)
        ok, message = enqueue_email_print_job(username, payload)
        messages.append(message if ok else f"Failed for {client}: {message}")
    return "; ".join(messages)
