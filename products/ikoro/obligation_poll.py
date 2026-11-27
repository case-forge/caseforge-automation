#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import clientdb_sql
from atomic_json import atomic_write_json
from monitoring import healthchecks_ping, telegram_secretary_alert
from . import obligation_aging

LOCK_PATH = REPO_ROOT / "telemetry" / "caseforge-monitor" / "obligation_poll.lock"
STATE_PATH = REPO_ROOT / "telemetry" / "caseforge-monitor" / "obligation_alert_state.json"


class _HarnessHeldLock:

    def close(self) -> None:
        return None


_HARNESS_LOCK_SENTINEL = _HarnessHeldLock()


def _harness_already_holds_lock() -> bool:
    harness_lock = os.environ.get("CASEFORGE_JOB_LOCK_FILE", "").strip()
    if not harness_lock:
        return False
    try:
        return Path(harness_lock).resolve() == LOCK_PATH.resolve()
    except OSError:
        return False


def _acquire_lock() -> Optional[Any]:
    if _harness_already_holds_lock():
        return _HARNESS_LOCK_SENTINEL
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK_PATH, "w", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _signature(lines: list[str]) -> str:
    if not lines:
        return ""
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()


def alert_on_change(lines: list[str], *, state_path: Optional[Path] = None) -> bool:
    state_path = state_path or STATE_PATH
    try:
        previous = str(json.loads(state_path.read_text(encoding="utf-8")).get("sig") or "")
    except (OSError, ValueError, AttributeError):
        previous = ""
    current = _signature(lines)
    if current == previous:
        return False
    if lines:
        text = f"{len(lines)} overdue obligation(s): " + "; ".join(lines[:5])
    else:
        text = "Overdue obligations cleared."
    if not telegram_secretary_alert.send_ops_alert(text).get("sent"):
        return False
    atomic_write_json(state_path, {"sig": current})
    return True


def run_poll(*, now: Optional[dt.datetime] = None, dry_run: bool = False) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = clientdb_sql.list_open_obligation_rows()
    obligations = obligation_aging.compute_obligations(rows, now)
    overdue = obligation_aging.overdue_obligations(obligations)

    alerted = False
    if not dry_run:
        lines = [obligation_aging.pii_safe_alert_text(ob) for ob in overdue]
        alerted = alert_on_change(lines)

    return {
        "open_obligations": len(obligations),
        "overdue": len(overdue),
        "alerted": alerted,
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CaseForge Monitor headless obligation poller")
    ap.add_argument(
        "--dry-run", action="store_true", help="Compute and report only; no heartbeat, no Telegram"
    )
    args = ap.parse_args(argv)

    lock_handle = _acquire_lock()
    if lock_handle is None:
        print(json.dumps({"skipped": "already_running"}, ensure_ascii=False, indent=2))
        return 0

    if not args.dry_run:
        base = os.environ.get("CASEFORGE_HEALTHCHECKS_PING_BASE", "").strip().rstrip("/")
        if base:
            try:
                healthchecks_ping.ping(base, "caseforge-obligation-poll", fail=False, message="alive")
            except Exception:
                pass

    try:
        summary = run_poll(dry_run=args.dry_run)
    finally:
        lock_handle.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
