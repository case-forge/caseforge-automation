#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from agents import job_queue
from agents.order_intake import run_order_intake


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "payload_file", ""):
        return json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    if getattr(args, "payload_json", ""):
        return json.loads(args.payload_json)
    return {}


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _record_runtime_event(command: str, metrics: dict[str, Any]) -> None:
    try:
        from telemetry_sqlite import record_runtime_event, utc_now_z

        record_runtime_event(
            {
                "timestamp": utc_now_z(),
                "event_name": "agent_runner",
                "runtime_label": os.environ.get("CASEFORGE_RUNTIME_LABEL", ""),
                "model_label": os.environ.get("CASEFORGE_MODEL_LABEL", ""),
                "command": command,
                "files_read": ["tools/run_agent.py"],
                "files_written": ["ops/caseforge-ops.sqlite3"],
                "metrics": metrics,
            }
        )
    except Exception:
        pass


def run_claimed_job(job: dict[str, Any], *, db_path: str | Path | None = None) -> dict[str, Any]:
    job_type = str(job.get("job_type") or "")
    if job_type == "order-intake":
        result = run_order_intake(job, db_path=db_path)
        return {"job_id": job["job_id"], "status": result.status, "blocker": result.blocker_text}
    if job_type == "email-print-archive":
        from agents.email_print_archive import run_email_print_archive_job

        updated = run_email_print_archive_job(job, db_path=db_path)
        return {
            "job_id": updated["job_id"],
            "status": updated["status"],
            "blocker": updated.get("blocker_text", ""),
        }
    if job_type == "sos-to-court-draft":
        from agents.sos_to_court_draft import run_sos_to_court_draft_job

        updated = run_sos_to_court_draft_job(job, db_path=db_path)
        return {
            "job_id": updated["job_id"],
            "status": updated["status"],
            "blocker": updated.get("blocker_text", ""),
        }
    if job_type == "mail-intake":
        from mail_intake.classifier import run_mail_intake_classifier_job

        updated = run_mail_intake_classifier_job(job, db_path=db_path)
        return {
            "job_id": updated["job_id"],
            "status": updated["status"],
            "blocker": updated.get("blocker_text", ""),
        }
    if job_type in job_queue.RETIRED_JOB_TYPES:
        reason = job_queue.RETIRED_JOB_TYPES[job_type]
        updated = job_queue.update_job(
            str(job["job_id"]),
            status="cancelled",
            error_text=reason,
            event_type="cancelled",
            event_message=reason,
            db_path=db_path,
        )
        return {"job_id": updated["job_id"], "status": updated["status"], "blocker": reason}
    if job_type == "documenso-document-completed":
        from agents.documenso_webhook_worker import run_documenso_webhook_worker_job

        result = run_documenso_webhook_worker_job(job, db_path=db_path)
        return {
            "job_id": job["job_id"],
            "status": result["status"],
            "blocker": result.get("manual_review_reason", ""),
        }
    if job_type == "repo-cleanup":
        from agents.repo_maintenance import run_cleanup_job

        updated = run_cleanup_job(job, db_path=db_path)
        return {
            "job_id": updated["job_id"],
            "status": updated["status"],
            "blocker": updated.get("blocker_text", ""),
        }
    if job_type == "repo-pii-scan":
        from agents.repo_maintenance import run_pii_scan_job

        updated = run_pii_scan_job(job, db_path=db_path)
        return {
            "job_id": updated["job_id"],
            "status": updated["status"],
            "blocker": updated.get("blocker_text", ""),
        }
    if job_type == "doc-discipline":
        from agents.repo_maintenance import run_doc_discipline_job

        updated = run_doc_discipline_job(job, db_path=db_path)
        return {
            "job_id": updated["job_id"],
            "status": updated["status"],
            "blocker": updated.get("blocker_text", ""),
        }
    if job_type == "agent-friction":
        from agents.repo_maintenance import run_agent_friction_job

        updated = run_agent_friction_job(job, db_path=db_path)
        return {
            "job_id": updated["job_id"],
            "status": updated["status"],
            "blocker": updated.get("blocker_text", ""),
        }
    blocker = f"Unsupported job type: {job_type}"
    updated = job_queue.update_job(
        str(job["job_id"]),
        status="failed",
        error_text=blocker,
        event_type="failed",
        event_message=blocker,
        db_path=db_path,
    )
    return {"job_id": updated["job_id"], "status": updated["status"], "error": blocker}


def cancel_retired_queued_jobs(db_path: str | Path | None = None) -> list[dict[str, str]]:
    try:
        cancelled = job_queue.cancel_retired_queued_jobs(db_path=db_path)
    except Exception as exc:
        print(f"[run_agent] retired-job sweep failed: {type(exc).__name__}", file=sys.stderr)
        return []
    for row in cancelled:
        print(f"[run_agent] cancelled queued retired job {row['job_id']} ({row['job_type']})", file=sys.stderr)
    return cancelled


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    cancel_retired_queued_jobs(getattr(args, "db_path", "") or None)
    job = job_queue.claim_next_job(
        job_type=getattr(args, "type", "") or "",
        worker_id=getattr(args, "worker_id", "") or "",
        db_path=getattr(args, "db_path", "") or None,
    )
    if job is None:
        return {"claimed": False}
    try:
        result = run_claimed_job(job, db_path=getattr(args, "db_path", "") or None)
        result["claimed"] = True
        return result
    except Exception as exc:
        try:
            requeued = job_queue.requeue_transient(job, exc, db_path=getattr(args, "db_path", "") or None)
        except Exception:
            requeued = None
        if requeued is not None:
            return {"claimed": True, "job_id": requeued["job_id"], "status": "queued", "error": str(exc)}
        updated = job_queue.update_job(
            str(job["job_id"]),
            status="failed",
            error_text=str(exc),
            event_type="failed",
            event_message=str(exc),
            db_path=getattr(args, "db_path", "") or None,
        )
        return {"claimed": True, "job_id": updated["job_id"], "status": "failed", "error": str(exc)}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CaseForge background agent jobs.")
    parser.add_argument("--db-path", default="", help="Override agent job DB path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_enqueue = sub.add_parser("enqueue", help="Create a background agent job")
    p_enqueue.add_argument("--type", required=True, help="Job type, e.g. order-intake, email-print-archive, sos-to-court-draft, attendance-note-memos, repo-cleanup, or agent-friction")
    p_enqueue.add_argument("--payload-json", default="")
    p_enqueue.add_argument("--payload-file", default="")
    p_enqueue.add_argument("--created-user", default="")
    p_enqueue.add_argument("--matter-id", default="")
    p_enqueue.add_argument("--idempotency-key", default="")

    p_run_once = sub.add_parser("run-once", help="Claim and advance one queued job")
    p_run_once.add_argument("--type", default="", help="Optional job type filter")
    p_run_once.add_argument("--worker-id", default="")

    p_loop = sub.add_parser("run-loop", help="Run jobs until stopped")
    p_loop.add_argument("--type", default="", help="Optional job type filter")
    p_loop.add_argument("--worker-id", default="")
    p_loop.add_argument("--poll-seconds", type=float, default=10)
    p_loop.add_argument("--max-jobs", type=int, default=0, help="Stop after N jobs; 0 means forever")

    p_status = sub.add_parser("status", help="Show one job with events and artefacts")
    p_status.add_argument("--job-id", required=True)

    p_list = sub.add_parser("list", help="List recent jobs")
    p_list.add_argument("--status", default="")
    p_list.add_argument("--limit", type=int, default=20)
    return parser


def sweep_queued_attendance_notes(job_type: str, db_path: str | Path | None = None) -> int:
    if job_type != "attendance-note-memos":
        return 0
    try:
        from documents import attendance_note_drafts

        return attendance_note_drafts.sweep_queued(db_path=db_path)
    except Exception as exc:
        print(f"[run_agent] attendance note sweep failed: {type(exc).__name__}", file=sys.stderr)
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    db_path = args.db_path or None

    if args.cmd == "enqueue":
        payload = _load_payload(args)
        job, created = job_queue.enqueue_job(
            args.type,
            payload,
            created_user=args.created_user,
            matter_id=args.matter_id,
            idempotency_key=args.idempotency_key,
            db_path=db_path,
        )
        _record_runtime_event("tools/run_agent.py enqueue", {"job_type": args.type, "created": created})
        _print_json({"created": created, "job": job})
        return 0

    if args.cmd == "run-once":
        result = run_once(args)
        _record_runtime_event("tools/run_agent.py run-once", result)
        _print_json(result)
        return 0

    if args.cmd == "run-loop":
        completed = 0
        while True:
            sweep_queued_attendance_notes(args.type, db_path)
            result = run_once(args)
            if result.get("claimed"):
                completed += 1
                _print_json(result)
                if args.max_jobs and completed >= args.max_jobs:
                    return 0
                continue
            time.sleep(max(1.0, float(args.poll_seconds)))

    if args.cmd == "status":
        job = job_queue.get_job(args.job_id, db_path=db_path)
        if job is None:
            _print_json({"found": False, "job_id": args.job_id})
            return 1
        _print_json(
            {
                "found": True,
                "job": job,
                "events": job_queue.list_events(args.job_id, db_path=db_path),
                "artifacts": job_queue.list_artifacts(args.job_id, db_path=db_path),
            }
        )
        return 0

    if args.cmd == "list":
        _print_json({"jobs": job_queue.list_jobs(status=args.status, limit=args.limit, db_path=db_path)})
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
