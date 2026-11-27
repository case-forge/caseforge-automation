#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BOTS = ("caseforge_dev", "auto_bot", "counsel_ops")
_API = "https://api.telegram.org/bot{token}/{method}"
_SKIP_MODULES = {"telegram_log", "telegram_secretary_alert", "monitoring.telegram_log", "monitoring.telegram_secretary_alert"}

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS telegram_sent_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_utc TEXT NOT NULL,
    bot TEXT NOT NULL,
    source TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    chat_id_hash TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    ok INTEGER NOT NULL DEFAULT 0,
    http_status INTEGER,
    error TEXT NOT NULL DEFAULT '',
    route TEXT NOT NULL DEFAULT 'page',
    label TEXT NOT NULL DEFAULT ''
)
"""
_COLUMNS = ("sent_utc", "bot", "source", "kind", "chat_id_hash", "text", "ok", "http_status", "error", "route", "label")
_ADDED_COLUMNS = {"route": "TEXT NOT NULL DEFAULT 'page'", "label": "TEXT NOT NULL DEFAULT ''"}
ROUTES = ("page", "digest", "board")



def routing_path() -> Path | None:
    if (os.environ.get("CASEFORGE_ALERT_ROUTING") or "").strip().lower() == "none":
        return None
    here = Path(__file__).resolve()
    for candidate in (os.environ.get("CASEFORGE_ALERT_ROUTING") or "", here.parents[2] / "runtime-data" / "alert-routing.json",
                      here.with_name("alert-routing.json")):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def load_routing(path: Path | None = None) -> dict[str, Any] | None:
    path = path or routing_path()
    if path is None:
        return None
    try:
        table = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return table if isinstance(table, dict) and isinstance(table.get("routes"), list) else None


def route_for(source: str, text: str, table: dict[str, Any] | None = None) -> tuple[str, str]:
    table = load_routing() if table is None else table
    if not table:
        return "page", ""
    for rule in table.get("routes", []):
        try:
            if rule.get("source") and str(rule["source"]) not in source:
                continue
            if rule.get("match") and not re.search(str(rule["match"]), text):
                continue
            route = str(rule.get("route", ""))
        except (re.error, TypeError, AttributeError):
            continue
        if route in ROUTES:
            return route, str(rule.get("label", ""))
    default = str(table.get("default", "page"))
    return (default if default in ROUTES else "page"), ""


def _now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def chat_id_hash(chat_id: str) -> str:
    return hashlib.sha256(str(chat_id).encode("utf-8")).hexdigest()[:16] if chat_id else ""


def caller_source() -> str:
    for frame in inspect.stack()[1:]:
        name = str(frame.frame.f_globals.get("__name__", ""))
        if name in _SKIP_MODULES:
            continue
        module = name if name != "__main__" else Path(str(frame.frame.f_globals.get("__file__", "main"))).stem
        return f"{module}.{frame.function}"
    return "unknown"


def _state_dir() -> Path:
    override = os.environ.get("CASEFORGE_TELEGRAM_LOG_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "caseforge-alert"


def jsonl_path() -> Path:
    return _state_dir() / "telegram_sent_log.jsonl"


def _redact(text: str, token: str) -> str:
    return str(text).replace(token, "<redacted>") if token else str(text)


def _write_row(row: dict[str, Any]) -> str:
    try:
        tools_dir = str(Path(__file__).resolve().parents[1])
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import ops_db

        with ops_db.connect() as conn:
            conn.execute(_TABLE_SQL)
            have = {r[1] for r in conn.execute("PRAGMA table_info(telegram_sent_log)")}
            for column, ddl in _ADDED_COLUMNS.items():
                if column not in have:
                    conn.execute(f"ALTER TABLE telegram_sent_log ADD COLUMN {column} {ddl}")
            conn.execute(
                f"INSERT INTO telegram_sent_log ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})",
                [row[c] for c in _COLUMNS],
            )
        return "db"
    except Exception:
        pass
    try:
        path = jsonl_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return "jsonl"
    except Exception:
        return "lost"


def log_blocked(*, bot: str, source: str, kind: str, chat_id: str, reason: str) -> None:
    _write_row({"sent_utc": _now_z(), "bot": bot, "source": source, "kind": kind, "chat_id_hash": chat_id_hash(chat_id),
                "text": "[withheld: failed the safety check]", "ok": 0, "http_status": None, "error": reason,
                "route": "page", "label": ""})


def send(*, bot: str, source: str, kind: str, token: str, chat_id: str, text: str, timeout: float = 10.0,
         form_encoded: bool = False, max_chars: int = 4000, route: str = "") -> dict[str, Any]:
    text = str(text)[:max_chars]
    label = ""
    if route not in ROUTES:
        route, label = route_for(source, text)
    if route != "page":
        _write_row({"sent_utc": _now_z(), "bot": bot, "source": source, "kind": kind, "chat_id_hash": chat_id_hash(chat_id),
                    "text": text, "ok": 1, "http_status": None, "error": "", "route": route, "label": label})
        return {"sent": True, "held": route, "http_status": None}
    params = {"chat_id": chat_id, "text": text}
    if form_encoded:
        body, headers = urllib.parse.urlencode(params).encode(), {}
    else:
        body, headers = json.dumps(params).encode("utf-8"), {"Content-Type": "application/json"}
    req = urllib.request.Request(_API.format(token=token, method="sendMessage"), data=body, headers=headers, method="POST")
    ok, status, reason, detail = False, None, "", ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None)
            raw = resp.read()
        try:
            ok = bool(json.loads(raw).get("ok", True)) if raw else True
        except (ValueError, AttributeError):
            ok = True
        if not ok:
            reason = "not_ok"
    except urllib.error.HTTPError as exc:
        status, reason, detail = exc.code, f"http_error:{exc.code}", _redact(str(exc), token)[:300]
    except Exception as exc:
        reason, detail = "request_failed", _redact(str(exc), token)[:300]
    _write_row({"sent_utc": _now_z(), "bot": bot, "source": source, "kind": kind, "chat_id_hash": chat_id_hash(chat_id),
                "text": text, "ok": 1 if ok else 0, "http_status": status, "error": reason if not ok else "",
                "route": "page", "label": label})
    result: dict[str, Any] = {"sent": ok, "http_status": status}
    if not ok:
        result.update(reason=reason, detail=detail)
    return result



def _read_rows(since: str, bot: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        tools_dir = str(Path(__file__).resolve().parents[1])
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import ops_db

        db = ops_db.resolve_ops_db_path()
        if Path(db).exists():
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                conn.row_factory = sqlite3.Row
                sql, args = "SELECT * FROM telegram_sent_log WHERE sent_utc >= ?", [since]
                if bot:
                    sql, args = sql + " AND bot = ?", args + [bot]
                rows += [dict(r) for r in conn.execute(sql + " ORDER BY sent_utc", args)]
            finally:
                conn.close()
    except Exception:
        pass
    try:
        for line in jsonl_path().read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("sent_utc", "") >= since and (not bot or row.get("bot") == bot):
                rows.append(row)
    except OSError:
        pass
    return sorted(rows, key=lambda r: r.get("sent_utc", ""))


def _since(delta: dt.timedelta) -> str:
    return (dt.datetime.now(dt.timezone.utc) - delta).isoformat(timespec="seconds").replace("+00:00", "Z")


def recent(hours: float = 24, bot: str = "") -> list[dict[str, Any]]:
    return _read_rows(_since(dt.timedelta(hours=hours)), bot)


def summary(days: float = 7) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _read_rows(_since(dt.timedelta(days=days))):
        entry = counts.setdefault((row["bot"], row["source"]),
                                  {"bot": row["bot"], "source": row["source"], "sent": 0, "failed": 0, "held": 0})
        held = (row.get("route") or "page") != "page"
        entry["held" if held else ("sent" if row.get("ok") else "failed")] += 1
    return sorted(counts.values(), key=lambda e: (-(e["sent"] + e["failed"] + e["held"]), e["bot"], e["source"]))


def held(since: str, routes: tuple[str, ...] = ("digest", "board")) -> list[dict[str, Any]]:
    return [r for r in _read_rows(since) if (r.get("route") or "page") in routes]


def last_digest_utc() -> str:
    sent = [r["sent_utc"] for r in _read_rows(_since(dt.timedelta(days=14))) if r.get("kind") == "digest" and r.get("ok")]
    return max(sent) if sent else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read the Telegram send log (read-only).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_recent = sub.add_parser("recent")
    p_recent.add_argument("--hours", type=float, default=24)
    p_recent.add_argument("--bot", default="", choices=("",) + BOTS)
    p_sum = sub.add_parser("summary")
    p_sum.add_argument("--days", type=float, default=7)
    p_held = sub.add_parser("held")
    p_held.add_argument("--hours", type=float, default=24)
    p_route = sub.add_parser("route")
    p_route.add_argument("--source", required=True)
    p_route.add_argument("--text", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "recent":
        for r in recent(args.hours, args.bot):
            route = r.get("route") or "page"
            flag = ("ok " if r.get("ok") else "ERR") if route == "page" else route[:3]
            print(f"{r['sent_utc']} {flag} {r['bot']} {r['source']} [{r.get('kind', '')}] {r.get('text', '')}"
                  + (f"  ({r['error']})" if r.get("error") else ""))
    elif args.cmd == "held":
        counts: dict[tuple[str, str], int] = {}
        for r in held(_since(dt.timedelta(hours=args.hours))):
            key = (r.get("route") or "", r.get("label") or r.get("source") or "")
            counts[key] = counts.get(key, 0) + 1
        for (route, label), n in sorted(counts.items(), key=lambda kv: (kv[0][0], -kv[1])):
            print(f"{n:5d}  {route:6}  {label}")
    elif args.cmd == "route":
        route, label = route_for(args.source, args.text)
        print(f"{route}  {label}".rstrip())
    else:
        for e in summary(args.days):
            print(f"{e['sent']:5d} sent {e['failed']:3d} failed {e['held']:4d} held  {e['bot']}  {e['source']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
