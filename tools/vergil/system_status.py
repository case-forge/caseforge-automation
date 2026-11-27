from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

BOX_STALE_MINUTES = 5
PROVIDER_STALE_MINUTES = 15
BOX_ORDER = ("dev", "prod")
BOX_LABELS = {"dev": "Development box", "prod": "Production box"}
STATES = ("operational", "degraded", "outage", "maintenance", "unknown")

_BOX_NUMBER_FIELDS = ("cpu", "ram", "storage", "swap")


def telemetry_root() -> Path:
    return Path(__file__).resolve().parents[2] / "telemetry"


def box_path(box: str, root: Path | None = None) -> Path:
    return (root or telemetry_root()) / f"box-stats-{box}.json"


def provider_path(root: Path | None = None) -> Path:
    return (root or telemetry_root()) / "provider-status.json"


def parse_utc(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def age_minutes(generated_at: Any, now: dt.datetime) -> int | None:
    when = parse_utc(generated_at)
    return max(0, int((now - when).total_seconds() // 60)) if when else None


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _num(value: Any) -> float | int | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def clean_box(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {"generated_at": str(raw.get("generated_at") or "")[:40], "host": str(raw.get("host") or "")[:40]}
    for section in _BOX_NUMBER_FIELDS:
        block = raw.get(section)
        if not isinstance(block, dict):
            return None
        out[section] = {str(k)[:32]: _num(v) for k, v in block.items() if _num(v) is not None or v is None}
    zram = []
    for dev in raw.get("zram") or []:
        if isinstance(dev, dict):
            zram.append({str(k)[:32]: (_num(v) if k != "name" else str(v)[:16]) for k, v in dev.items()})
    out["zram"] = zram[:8]
    return out


def box_view(box: str, payload: Any, now: dt.datetime) -> dict:
    cleaned = clean_box(payload)
    base = {"box": box, "label": BOX_LABELS[box], "host": ""}
    if cleaned is None:
        return {**base, "available": False, "generated_at": "", "age_minutes": None, "stale": True}
    age = age_minutes(cleaned["generated_at"], now)
    return {
        **base,
        "available": True,
        "host": cleaned["host"],
        "generated_at": cleaned["generated_at"],
        "age_minutes": age,
        "stale": age is None or age > BOX_STALE_MINUTES,
        **{k: cleaned[k] for k in (*_BOX_NUMBER_FIELDS, "zram")},
    }


def load_boxes(root: Path | None = None, now: dt.datetime | None = None) -> list[dict]:
    now = now or dt.datetime.now(dt.timezone.utc)
    return [box_view(b, _read(box_path(b, root)), now) for b in BOX_ORDER]


def provider_view(raw: Any, snapshot_stale: bool) -> dict:
    row = raw if isinstance(raw, dict) else {}
    state = str(row.get("state") or "unknown")
    if state not in STATES or snapshot_stale:
        state = "unknown"
    note = str(row.get("note") or "")[:200]
    if snapshot_stale and not note:
        note = "Could not check: the last check is out of date"
    return {
        "key": str(row.get("key") or "")[:32],
        "name": str(row.get("name") or "")[:60],
        "state": state,
        "title": str(row.get("title") or "")[:200],
        "note": note,
        "checked_at": str(row.get("checked_at") or "")[:40],
        "flagged": state in ("degraded", "outage", "maintenance"),
    }


def load_providers(root: Path | None = None, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    payload = _read(provider_path(root))
    if not isinstance(payload, dict):
        return {"available": False, "generated_at": "", "age_minutes": None, "stale": True, "providers": []}
    age = age_minutes(payload.get("generated_at"), now)
    stale = age is None or age > PROVIDER_STALE_MINUTES
    rows = [provider_view(r, stale) for r in payload.get("providers") or [] if isinstance(r, dict)]
    return {
        "available": True,
        "generated_at": str(payload.get("generated_at") or ""),
        "age_minutes": age,
        "stale": stale,
        "providers": rows,
    }


def services_view(root: Path | None = None, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    raw = _snap("service-state.json", root)
    if not isinstance(raw, dict) or not isinstance(raw.get("services"), dict):
        return {"available": False, "generated_at": "", "age_minutes": None, "stale": True, "services": []}
    age = age_minutes(raw.get("generated_at"), now)
    stale = age is None or age > PROVIDER_STALE_MINUTES
    rows = []
    for key, v in raw["services"].items():
        if not isinstance(v, dict):
            continue
        state = v.get("state") if v.get("state") in ("up", "down", "unknown") else "unknown"
        rows.append({"key": str(key)[:40], "state": "unknown" if stale else state,
                     "reason": "The service checks have not run for a while." if stale else str(v.get("reason") or "")[:300],
                     "since": "" if stale else str(v.get("since") or "")[:40]})
    return {"available": True, "generated_at": str(raw.get("generated_at") or ""), "age_minutes": age, "stale": stale, "services": rows}



RENEW_URLS = {
    "served": "https://dash.cloudflare.com/?to=/:account/:zone/ssl-tls/edge-certificates",
    "file": "https://login.tailscale.com/admin/dns",
    "secret": "https://portal.azure.com/#view/HubsExtension/BrowseResourceBlade/resourceType/Microsoft.KeyVault%2Fvaults",
}
EXTRAS_STALE_MINUTES = 15
SCHEDULE_STALE_MINUTES = 15
BACKUP_AMBER_PERIODS, BACKUP_RED_PERIODS = 1.5, 3.0
SPEND_AMBER_REMAINING, SPEND_RED_REMAINING = 0.20, 0.05
EXPIRY_AMBER_DAYS, EXPIRY_RED_DAYS = 30, 7
FUNCTION_NAMES = {"relay": "Mail webhook relay", "send_gate": "Send gate"}


def _snap(name: str, root: Path | None) -> Any:
    return _read((root or telemetry_root()) / name)


def spend_view(root: Path | None = None, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    raw = _snap("openrouter-key-spend.json", root)
    if not isinstance(raw, dict) or not raw.get("available"):
        note = str(raw.get("note") or "") if isinstance(raw, dict) else ""
        return {"available": False, "note": note or "No spend figures yet", "generated_at": "", "usage": None,
                "usage_daily": None, "limit": None, "limit_remaining": None, "remaining_fraction": None, "tone": "grey"}
    limit, remaining = _num(raw.get("limit")), _num(raw.get("limit_remaining"))
    fraction = remaining / limit if limit and remaining is not None and limit > 0 else None
    tone = "ok"
    if fraction is not None:
        tone = "red" if fraction < SPEND_RED_REMAINING else "amber" if fraction < SPEND_AMBER_REMAINING else "ok"
    age = age_minutes(raw.get("generated_at"), now)
    if age is None or age > PROVIDER_STALE_MINUTES:
        tone = "grey"
    return {"available": True, "note": "", "generated_at": str(raw.get("generated_at") or ""), "usage": _num(raw.get("usage")),
            "usage_daily": _num(raw.get("usage_daily")), "limit": limit, "limit_remaining": remaining,
            "remaining_fraction": fraction, "tone": tone}


def _norm(name: str) -> str:
    n = re.sub(r"\.(timer|service)$", "", str(name).lower())
    n = re.sub(r"^(val|caseforge)[-_]", "", n)
    return re.sub(r"[^a-z0-9]", "", n)


def _clean_row(r: dict) -> dict:
    return {
        "name": str(r.get("name") or "")[:80], "kind": str(r.get("kind") or "timer")[:8],
        "description": str(r.get("description") or "")[:160], "schedule": str(r.get("schedule") or "")[:80],
        "last_run": str(r.get("last_run") or "")[:40], "last_result": str(r.get("last_result") or "")[:10],
        "next_run": str(r.get("next_run") or "")[:40], "period_seconds": _num(r.get("period_seconds")),
        "overdue": bool(r.get("overdue")),
    }


def workers_view(root: Path | None = None, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    extras = _snap("dev-extras.json", root)
    extras_age = age_minutes(extras.get("generated_at"), now) if isinstance(extras, dict) else None
    hc_raw = extras.get("healthchecks") if isinstance(extras, dict) else None
    hc_ok = isinstance(hc_raw, dict) and bool(hc_raw.get("available")) and extras_age is not None and extras_age <= EXTRAS_STALE_MINUTES
    checks = [
        {"name": str(c.get("name") or "")[:80], "status": str(c.get("status") or "new")[:8],
         "last_ping": str(c.get("last_ping") or "")[:40], "last_kind": c.get("last_kind") if c.get("last_kind") in ("start", "fail", "log", "ign") else "",
         "period_seconds": c.get("period_seconds") if isinstance(c.get("period_seconds"), int) else None}
        for c in (hc_raw.get("checks") if isinstance(hc_raw, dict) else None) or [] if isinstance(c, dict)
    ] if hc_ok else []
    by_norm = {_norm(c["name"]): c for c in checks}
    boxes = []
    matched: set[str] = set()
    for box in BOX_ORDER:
        payload = _snap(f"schedules-{box}.json", root) if box == "prod" else extras
        rows_raw = payload.get("schedules" if box == "dev" else "rows") if isinstance(payload, dict) else None
        age = age_minutes(payload.get("generated_at"), now) if isinstance(payload, dict) else None
        rows = []
        for r in rows_raw or []:
            if not isinstance(r, dict):
                continue
            row = _clean_row(r)
            check = by_norm.get(_norm(row["name"]))
            if check:
                matched.add(_norm(row["name"]))
            row["check"] = check
            row["no_check"] = bool(hc_ok and check is None)
            row["tone"] = "red" if row["last_result"] == "failed" else "amber" if row["overdue"] else "ok"
            rows.append(row)
        boxes.append({"box": box, "label": BOX_LABELS[box], "available": isinstance(payload, dict) and rows_raw is not None,
                      "generated_at": str(payload.get("generated_at") or "") if isinstance(payload, dict) else "",
                      "age_minutes": age, "stale": age is None or age > SCHEDULE_STALE_MINUTES, "rows": rows})
    orphans = [c for c in checks if _norm(c["name"]) not in matched]
    return {"boxes": boxes, "healthchecks": {"available": hc_ok, "note": "" if hc_ok else "No Healthchecks data (the dev box push is not enabled or is out of date)",
                                              "checks": checks, "orphan_checks": orphans}}


def backups_view(root: Path | None = None, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    raw = _snap("backup-status.json", root)
    if not isinstance(raw, dict) or not raw.get("available"):
        return {"available": False, "note": (str(raw.get("note")) if isinstance(raw, dict) else "") or "No backup figures yet", "rows": []}
    rows = []
    for r in raw.get("rows") or []:
        if not isinstance(r, dict):
            continue
        last = parse_utc(r.get("last_good"))
        period = _num(r.get("period_seconds")) or 86400
        age = (now - last).total_seconds() if last else None
        status = "red" if age is None or age > BACKUP_RED_PERIODS * period else "amber" if age > BACKUP_AMBER_PERIODS * period or r.get("shrank") else "ok"
        rows.append({"name": str(r.get("name") or "")[:100], "last_good": str(r.get("last_good") or ""), "age_seconds": int(age) if age is not None else None,
                     "latest_size_bytes": _num(r.get("latest_size_bytes")), "sizes": [x for x in (r.get("sizes") or []) if _num(x) is not None][-7:],
                     "shrank": bool(r.get("shrank")), "status": status})
    return {"available": True, "note": "", "rows": rows}


def expiries_view(root: Path | None = None, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    raw = _snap("expiry-status.json", root)
    if not isinstance(raw, dict):
        return {"available": False, "note": "No expiry figures yet", "rows": []}
    rows = []
    for r in raw.get("rows") or []:
        if not isinstance(r, dict):
            continue
        when = parse_utc(r.get("expires_at"))
        days = int((when - now).total_seconds() // 86400) if when else None
        state = str(r.get("state") or "unknown")
        tone = "grey"
        if days is not None:
            tone = "red" if days < EXPIRY_RED_DAYS else "amber" if days < EXPIRY_AMBER_DAYS else "ok"
        kind = str(r.get("kind") or "")
        rows.append({"kind": kind[:12], "name": str(r.get("name") or "")[:100], "expires_at": str(r.get("expires_at") or ""),
                     "days_left": days, "state": state[:20], "tone": tone, "note": str(r.get("note") or "")[:120],
                     "renew_url": RENEW_URLS.get(kind, "") if state != "needs_permission" else ""})
    return {"available": True, "note": "", "rows": rows}


def functions_view(root: Path | None = None) -> list[dict]:
    raw = _snap("function-events.json", root)
    raw = raw if isinstance(raw, dict) else {}
    return [{"key": k, "name": n, "last_event": str(raw.get(k) or "")[:40], "state": "ok" if raw.get(k) else "no_data"} for k, n in FUNCTION_NAMES.items()]
