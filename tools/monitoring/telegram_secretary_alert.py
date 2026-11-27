#!/usr/bin/env python3

from __future__ import annotations

import fcntl
import os
import sys
import time
import urllib.request
from pathlib import Path

_TOOLS_DIR = str(Path(__file__).resolve().parents[1])
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import monitoring.telegram_log as telegram_log
import monitoring.telegram_text_safety as telegram_text_safety


def bot_token() -> str:
    return (os.environ.get("CASEFORGE_MONITOR_TELEGRAM_BOT_TOKEN") or "").strip()


def owner_chat_id() -> str:
    return (os.environ.get("CASEFORGE_MONITOR_TELEGRAM_CHAT_ID") or "").strip()


def ops_bot_token() -> str:
    return (os.environ.get("CASEFORGE_COUNSEL_TELEGRAM_BOT_TOKEN") or "").strip() or bot_token()


def alert_configured(*, ops: bool = False) -> bool:
    return bool((ops_bot_token() if ops else bot_token()) and owner_chat_id())


OPS_GAP_SECONDS = 120
_MAX_WAIT_SECONDS = 150


def _ops_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "caseforge-alert"


def send_ops_alert(text: str, *, timeout: float = 10.0, route: str = "", kind: str = "ops") -> dict:
    if not alert_configured(ops=True):
        return send_secretary_alert(text, timeout=timeout, token=ops_bot_token(), kind=kind, route=route)
    gap_file = _ops_state_dir() / "ops_last_sent"
    try:
        gap_file.parent.mkdir(parents=True, exist_ok=True)
        lock = open(gap_file.with_suffix(".lock"), "w")
    except OSError:
        return send_secretary_alert(text, timeout=timeout, token=ops_bot_token(), kind=kind, route=route)
    with lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            last = float(gap_file.read_text())
        except (OSError, ValueError):
            last = 0.0
        wait = min(max(0.0, last + OPS_GAP_SECONDS - time.time()), _MAX_WAIT_SECONDS)
        if wait:
            time.sleep(wait)
        result = send_secretary_alert(text, timeout=timeout, token=ops_bot_token(), kind=kind, route=route)
        if result.get("sent"):
            try:
                gap_file.write_text(str(time.time()))
            except OSError:
                pass
        return result


def send_secretary_alert(text: str, *, timeout: float = 10.0, chat_id: str = "", token: str = "", kind: str = "casework",
                         route: str = "") -> dict:
    token = str(token or "").strip() or bot_token()
    chat_id = str(chat_id or "").strip() or owner_chat_id()
    if not token or not chat_id:
        return {"sent": False, "reason": "not_configured"}
    source = telegram_log.caller_source()
    ops_token = ops_bot_token()
    bot = "counsel_ops" if (token == ops_token and token != bot_token()) else "auto_bot"
    if telegram_text_safety.looks_unsafe(text):
        telegram_log.log_blocked(bot=bot, source=source, kind=kind, chat_id=chat_id, reason="text_failed_safety_check")
        return {"sent": False, "reason": "text_failed_safety_check"}

    result = telegram_log.send(bot=bot, source=source, kind=kind, token=token, chat_id=chat_id, text=text, timeout=timeout,
                               route=route)
    if result.get("held"):
        return {"sent": True, "held": result["held"]}
    if result.get("sent"):
        return {"sent": True}
    out = {"sent": False, "reason": result.get("reason", "request_failed")}
    if result.get("detail"):
        out["detail"] = result["detail"]
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Send one Telegram alert to the owner.")
    parser.add_argument("--critical", metavar="MESSAGE", required=True, help="alert text")
    args = parser.parse_args(argv)
    result = send_secretary_alert(f"CRITICAL: {args.critical}")
    if result.get("sent"):
        return 0
    print(f"telegram_secretary_alert: not sent ({result.get('reason')})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
