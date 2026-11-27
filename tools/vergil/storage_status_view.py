from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

STALE_MINUTES = 150


def telemetry_root() -> Path:
    return Path(__file__).resolve().parents[2] / "telemetry"


def _num(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _row(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not raw.get("name"):
        return None
    size = _num(raw.get("bytes"))
    return {
        "key": str(raw.get("key") or "")[:80], "group": str(raw.get("group") or "")[:30], "name": str(raw.get("name"))[:120],
        "bytes": size, "total_bytes": _num(raw.get("total_bytes")),
        "state": "ok" if size is not None else "unknown", "note": str(raw.get("note") or "")[:160],
    }


def storage_view(root: Path | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    empty = {"available": False, "note": "No storage figures yet.", "generated_at": "", "age_minutes": None, "stale": True,
             "target_backup_bytes": 0, "rows": []}
    try:
        raw = json.loads(((root or telemetry_root()) / "storage-status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    if not isinstance(raw, dict):
        return empty
    try:
        when = dt.datetime.fromisoformat(str(raw.get("generated_at") or "").replace("Z", "+00:00"))
        when = when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)
        age = max(0, int((now - when).total_seconds() // 60))
    except ValueError:
        age = None
    rows = [r for r in (_row(x) for x in raw.get("rows") or []) if r]
    return {
        "available": bool(raw.get("available")) and bool(rows), "note": str(raw.get("note") or "")[:160],
        "generated_at": str(raw.get("generated_at") or ""), "age_minutes": age, "stale": age is None or age > STALE_MINUTES,
        "target_backup_bytes": _num(raw.get("target_backup_bytes")) or 0, "rows": rows,
    }
