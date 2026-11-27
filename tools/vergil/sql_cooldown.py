from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

SESSION_DIR = Path.home() / ".caseforge-chat-sessions"
LONDON_TZ = ZoneInfo("Europe/London")


def sql_cooldown_file() -> Path:
    return SESSION_DIR / "sql-cooldown.json"


def _local_sql_configured() -> bool:
    return bool(
        os.getenv("LOCAL_SQLITE_PATH", "").strip()
        or os.getenv("LOCAL_SQL_CONNECTION_STRING", "").strip()
    )


def _cooldown_expiry() -> dt.datetime | None:
    try:
        path = sql_cooldown_file()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = str(data.get("unavailable_until", "")).strip()
        if not raw:
            return None
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def is_sql_available() -> bool:
    if _local_sql_configured():
        return True
    try:
        until = _cooldown_expiry()
        if until is None:
            return True
        return dt.datetime.now(dt.timezone.utc) >= until
    except Exception:
        return True


def sql_cooldown_until() -> str:
    if _local_sql_configured():
        return ""
    try:
        until = _cooldown_expiry()
        if until is None or dt.datetime.now(dt.timezone.utc) >= until:
            return ""
        return until.astimezone(LONDON_TZ).strftime("%-d %b %Y")
    except Exception:
        return ""


def sql_cooldown_fail_count() -> int:
    try:
        path = sql_cooldown_file()
        if not path.exists():
            return 0
        return int(json.loads(path.read_text(encoding="utf-8")).get("fail_count", 0))
    except Exception:
        return 0


