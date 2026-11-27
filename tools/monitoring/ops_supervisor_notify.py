#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from atomic_json import atomic_write_json

SNAPSHOT_PATH = REPO_ROOT / "telemetry" / "ops-supervisor.json"
STATE_PATH = REPO_ROOT / "telemetry" / "ops-supervisor-notify-state.json"
TELEGRAM_STATE_NAME = "ops-supervisor-telegram-state.json"

LONDON = ZoneInfo("Europe/London")
REMIND_AFTER_HOURS = 6
REMIND_BACKOFF = ((72, 72), (24, 24), (0, REMIND_AFTER_HOURS))
RED_HOLD_MINUTES = 30
MAX_TITLES = 8


def _category(alert: dict) -> str:
    return str(alert.get("category") or "health")


def red_health_alerts(payload: dict) -> list[dict]:
    return [
        a
        for a in list(payload.get("alerts") or [])
        if isinstance(a, dict) and _category(a) == "health" and str(a.get("severity")) == "red"
    ]


SNAPSHOT_MAX_AGE_MINUTES = 45
STALE_ALERT = {
    "key": "supervisor-stale-snapshot",
    "category": "health",
    "severity": "red",
    "title": "Supervisor is not producing snapshots",
}


def _is_stale(payload: dict, now: dt.datetime) -> bool:
    stamp = _parse(str(payload.get("generated_at") or ""))
    if stamp is None:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return now - stamp > dt.timedelta(minutes=SNAPSHOT_MAX_AGE_MINUTES)


def _titles(alerts: list[dict]) -> str:
    names = sorted({str(a.get("title") or "").strip() for a in alerts if str(a.get("title") or "").strip()})
    shown = names[:MAX_TITLES]
    extra = len(names) - len(shown)
    return "; ".join(shown) + (f"; and {extra} more" if extra > 0 else "")


def _fingerprint(alerts: list[dict]) -> str:
    return "|".join(sorted(str(a.get("key") or "") for a in alerts))


def _parse(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def plan(payload: dict, state: dict, now: dt.datetime) -> tuple[list[str], dict]:
    now = now.astimezone(dt.timezone.utc)
    stamp = now.isoformat().replace("+00:00", "Z")
    new_state = {k: v for k, v in state.items() if k != "digest_date"}
    messages: list[str] = []

    red = red_health_alerts(payload)
    stale = _is_stale(payload, now)
    if stale:
        red = [*red, STALE_ALERT]
    fingerprint = _fingerprint(red)
    last_fingerprint = str(state.get("red_fingerprint") or "")
    last_sent = _parse(str(state.get("red_sent_utc") or ""))
    if not red:
        if last_fingerprint:
            messages.append("CaseForge: back to normal. The problem reported earlier has cleared.")
        for key in ("red_fingerprint", "red_sent_utc", "red_since_utc"):
            new_state.pop(key, None)
        return messages, new_state

    since = _parse(str(state.get("red_since_utc") or "")) or now
    if stale:
        since = min(since, now - dt.timedelta(minutes=RED_HOLD_MINUTES))
    new_state["red_since_utc"] = since.isoformat().replace("+00:00", "Z")
    minutes = int((now - since).total_seconds() // 60)
    if minutes < RED_HOLD_MINUTES:
        return messages, new_state
    changed = fingerprint != last_fingerprint
    due = last_sent is None or now - last_sent >= dt.timedelta(hours=remind_gap(minutes))
    if changed or due:
        lead = "CaseForge needs attention" if changed else "CaseForge still needs attention"
        messages.append(f"{lead}: {_titles(red)}. Ongoing for {_duration(minutes)}.")
        new_state["red_fingerprint"] = fingerprint
        new_state["red_sent_utc"] = stamp
    return messages, new_state


def remind_gap(minutes: int) -> int:
    for lasted_hours, gap in REMIND_BACKOFF:
        if minutes >= lasted_hours * 60:
            return gap
    return REMIND_AFTER_HOURS


def _duration(minutes: int) -> str:
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h"


def _record_telegram_health(state_path: Path, *, working: bool, now: dt.datetime) -> None:
    path = state_path.with_name(TELEGRAM_STATE_NAME)
    try:
        previous = _load_json(path)
        if working:
            if previous:
                atomic_write_json(path, {})
            return
        if previous.get("silent_since_utc"):
            return
        atomic_write_json(path, {"silent_since_utc": now.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")})
    except OSError:
        pass


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Page Telegram from the ops supervisor snapshot")
    parser.add_argument("--snapshot", default=str(SNAPSHOT_PATH))
    parser.add_argument("--state", default=str(STATE_PATH))
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent; send nothing, save nothing")
    args = parser.parse_args(argv)

    snapshot_path = Path(args.snapshot)
    if not snapshot_path.exists():
        return 0
    payload = _load_json(snapshot_path)
    if not payload:
        payload = {"generated_at": "1970-01-01T00:00:00Z"}
    state_path = Path(args.state)
    state = _load_json(state_path)

    now = dt.datetime.now(dt.timezone.utc)
    messages, new_state = plan(payload, state, now)
    if not args.dry_run:
        from monitoring import telegram_secretary_alert

        if not telegram_secretary_alert.alert_configured(ops=True):
            _record_telegram_health(state_path, working=False, now=now)
        elif not messages:
            _record_telegram_health(state_path, working=True, now=now)
    if args.dry_run:
        for message in messages:
            print(message)
        return 0
    if not messages:
        if new_state != state:
            atomic_write_json(state_path, new_state)
        return 0

    from monitoring import telegram_secretary_alert

    if not telegram_secretary_alert.alert_configured(ops=True):
        print("ops_supervisor_notify: Telegram is not configured; nothing sent", file=sys.stderr)
        return 1
    for message in messages:
        result = telegram_secretary_alert.send_ops_alert(message)
        if not result.get("sent"):
            _record_telegram_health(state_path, working=False, now=now)
            print(f"ops_supervisor_notify: send failed ({result.get('reason')}); will retry next run", file=sys.stderr)
            return 1
    _record_telegram_health(state_path, working=True, now=now)
    atomic_write_json(state_path, new_state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
