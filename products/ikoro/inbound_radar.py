#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
INTAKE_PATH = REPO_ROOT / "telemetry" / "referralpartner-intake" / "intake.jsonl"

ALERT_STATUSES = {
    "inserted",
    "insert-failed",
    "name-extract-failed",
    "returning-client-review",
}
QUIET_STATUSES = {"already-in-sql"}

_STATUS_LABEL = {
    "inserted": "New referrer referral",
    "insert-failed": "referrer referral failed to record",
    "name-extract-failed": "referrer referral needs manual name",
    "returning-client-review": "Returning client — review",
}


def status_label(status: str) -> str:
    return _STATUS_LABEL.get(str(status or ""), str(status or "") or "inbound item")


def _parse_ts(raw: Any) -> Optional[dt.datetime]:
    try:
        ts = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return ts.replace(tzinfo=dt.timezone.utc) if ts.tzinfo is None else ts


def read_referrals(path: Optional[Path] = None) -> list[dict]:
    path = path or INTAKE_PATH
    out: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def recent_referrals(
    now: dt.datetime,
    *,
    window_hours: int = 168,
    referrals: Optional[Iterable[Mapping[str, Any]]] = None,
    path: Optional[Path] = None,
) -> list[dict]:
    items = list(referrals) if referrals is not None else read_referrals(path)
    cutoff = now - dt.timedelta(hours=window_hours)
    recent: list[dict] = []
    seen_keys: set[str] = set()
    for rec in items:
        ts = _parse_ts(rec.get("ts"))
        if ts is None or not (cutoff <= ts <= now):
            continue
        key = referral_key(rec)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        recent.append(dict(rec))
    return recent


def classify(referrals: Iterable[Mapping[str, Any]]) -> dict[str, list[dict]]:
    alert: list[dict] = []
    quiet: list[dict] = []
    for rec in referrals:
        (alert if str(rec.get("status")) in ALERT_STATUSES else quiet).append(dict(rec))
    return {"alert": alert, "quiet": quiet}


def referral_key(rec: Mapping[str, Any]) -> str:
    mid = rec.get("message_id")
    return f"referral:{mid}" if mid else f"referral:{rec.get('ts')}:{rec.get('status')}"


def pii_safe_referral_line(rec: Mapping[str, Any]) -> str:
    status = str(rec.get("status") or "")
    label = _STATUS_LABEL.get(status, status or "inbound item")
    ref = rec.get("matter_id") or rec.get("person_id")
    day = ""
    ts = _parse_ts(rec.get("ts"))
    if ts is not None:
        day = f" {ts.date().isoformat()}"
    tail = f" (matter {ref})" if ref else ""
    return f"[INBOUND] {label}{tail}{day}".rstrip()


def recent_alertable(
    now: dt.datetime, *, window_hours: int = 168, path: Optional[Path] = None
) -> list[dict]:
    recent = recent_referrals(now, window_hours=window_hours, path=path)
    alert = classify(recent)["alert"]
    alert.sort(key=lambda r: str(r.get("ts")), reverse=True)
    return alert


def radar_summary(
    now: Optional[dt.datetime] = None, *, window_hours: int = 168, path: Optional[Path] = None
) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    recent = recent_referrals(now, window_hours=window_hours, path=path)
    split = classify(recent)
    return {
        "window_hours": window_hours,
        "alert_count": len(split["alert"]),
        "quiet_count": len(split["quiet"]),
        "alert_lines": [pii_safe_referral_line(r) for r in
                        sorted(split["alert"], key=lambda r: str(r.get("ts")), reverse=True)],
    }
