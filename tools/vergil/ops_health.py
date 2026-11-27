from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

STALE_AFTER_MINUTES = 45

SEVERITIES = ("red", "amber", "info", "green")
CATEGORIES = ("health", "housekeeping")

_PATH_RE = re.compile(r"(?:(?<![\w.])~?/(?:[\w.@+-]+/)+[\w.@+-]*|\b[A-Za-z]:\\[^\s`'\"]+)")


def snapshot_path() -> Path:
    import monitoring.ops_supervisor as ops_supervisor_lib

    return Path(ops_supervisor_lib.DEFAULT_OUT)


def scrub_paths(text: str) -> str:
    return _PATH_RE.sub("[path]", str(text or ""))


def _parse_utc(value: str) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _age_minutes(metrics: Any) -> int | None:
    if not isinstance(metrics, dict):
        return None
    minutes = metrics.get("age_minutes")
    if isinstance(minutes, (int, float)) and not isinstance(minutes, bool) and minutes >= 0:
        return int(minutes)
    hours = metrics.get("age_hours")
    if isinstance(hours, (int, float)) and not isinstance(hours, bool) and hours >= 0:
        return int(hours * 60)
    return None


def _alert(raw: dict) -> dict:
    severity = str(raw.get("severity") or "info").lower()
    category = str(raw.get("category") or "health").lower()
    return {
        "severity": severity if severity in SEVERITIES else "info",
        "category": category if category in CATEGORIES else "health",
        "title": scrub_paths(str(raw.get("title") or "").strip()) or "Untitled alert",
        "next_action": scrub_paths(str(raw.get("next_action") or "").strip()),
        "kind": str(raw.get("kind") or "state"),
        "age_minutes": _age_minutes(raw.get("metrics")),
    }


def reduce_snapshot(payload: dict | None, *, now: dt.datetime) -> dict:
    if not isinstance(payload, dict):
        return {
            "available": False,
            "generated_at": "",
            "snapshot_age_minutes": None,
            "stale": True,
            "overall_severity": "unknown",
            "housekeeping_severity": "unknown",
            "alerts": [],
        }
    generated = str(payload.get("generated_at") or "")
    when = _parse_utc(generated)
    age = max(0, int((now - when).total_seconds() // 60)) if when else None
    overall = str(payload.get("overall_severity") or "unknown").lower()
    housekeeping = str(payload.get("housekeeping_severity") or "green").lower()
    order = {s: i for i, s in enumerate(SEVERITIES)}
    alerts = [_alert(a) for a in list(payload.get("alerts") or []) if isinstance(a, dict)]
    alerts.sort(key=lambda a: (order[a["severity"]], a["title"]))
    return {
        "available": True,
        "generated_at": generated,
        "snapshot_age_minutes": age,
        "stale": age is None or age > STALE_AFTER_MINUTES,
        "overall_severity": overall if overall in SEVERITIES else "unknown",
        "housekeeping_severity": housekeeping if housekeeping in SEVERITIES else "unknown",
        "alerts": alerts,
    }


def load(path: Path | None = None, *, now: dt.datetime | None = None) -> dict:
    target = path or snapshot_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = None
    return reduce_snapshot(payload, now=now or dt.datetime.now(dt.timezone.utc))
