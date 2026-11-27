#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

import sys

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from telemetry_sqlite import resolve_db_path


REPO_ROOT = Path(__file__).resolve().parents[2]
MONITOR_ROOT = REPO_ROOT / "telemetry"
TELEMETRY_DB = resolve_db_path()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a daily progress digest from telemetry.")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Local date in YYYY-MM-DD format.")
    parser.add_argument("--output", default="", help="Optional output markdown path.")
    parser.add_argument("--write", action="store_true", help="Write to --output instead of stdout.")
    return parser.parse_args()


def _load_runtime_events(date_text: str) -> List[Dict[str, Any]]:
    if TELEMETRY_DB.exists():
        conn = sqlite3.connect(str(TELEMETRY_DB))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT timestamp, event_name, runtime_label, model_label, command_text,
                       files_read_json, files_written_json, sections_skipped_json, metrics_json
                FROM runtime_activation_events
                WHERE substr(timestamp, 1, 10) = ?
                ORDER BY timestamp
                """,
                (date_text,),
            ).fetchall()
        finally:
            conn.close()
        events: List[Dict[str, Any]] = []
        for row in rows:
            events.append(
                {
                    "timestamp": str(row["timestamp"] or ""),
                    "event_name": str(row["event_name"] or ""),
                    "runtime_label": str(row["runtime_label"] or ""),
                    "model_label": str(row["model_label"] or ""),
                    "command_text": str(row["command_text"] or ""),
                    "files_read": _json_loads(row["files_read_json"], []),
                    "files_written": _json_loads(row["files_written_json"], []),
                    "sections_skipped": _json_loads(row["sections_skipped_json"], []),
                    "metrics": _json_loads(row["metrics_json"], {}),
                }
            )
        return events

    events_path = MONITOR_ROOT / "runtime-activation-events.jsonl"
    if not events_path.exists():
        return []

    events = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if str(row.get("timestamp", "")).strip()[:10] != date_text:
            continue
        events.append(
            {
                "timestamp": str(row.get("timestamp", "") or ""),
                "event_name": str(row.get("event_name", "") or ""),
                "runtime_label": str(row.get("runtime_label", "") or ""),
                "model_label": str(row.get("model_label", "") or ""),
                "command_text": str(row.get("command", "") or ""),
                "files_read": list(row.get("files_read", []) or []),
                "files_written": list(row.get("files_written", []) or []),
                "sections_skipped": list(row.get("sections_skipped", []) or []),
                "metrics": dict(row.get("metrics", {}) or {}),
            }
        )
    return sorted(events, key=lambda item: item["timestamp"])


def _json_loads(raw: Any, default: Any) -> Any:
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _time_text(timestamp: str) -> str:
    text = str(timestamp or "").strip()
    if len(text) >= 16:
        return text[11:16]
    return text


def _weekly_review(date_text: str) -> Dict[str, Any] | None:
    review_path = MONITOR_ROOT / "weekly-reviews" / f"{date_text}-startup-review.json"
    if not review_path.exists():
        return None
    try:
        return json.loads(review_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _latest_adjustment_for(date_text: str) -> Dict[str, Any] | None:
    proposal_path = MONITOR_ROOT / "adjustment-proposals" / "latest-startup-adjustment.json"
    if not proposal_path.exists():
        return None
    try:
        payload = json.loads(proposal_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if str(payload.get("review_date", "")).strip() != date_text:
        return None
    return payload


def _root_card_paths(events: Iterable[Dict[str, Any]]) -> List[str]:
    return []


def _printed_pdfs(events: Iterable[Dict[str, Any]]) -> List[str]:
    printed: List[str] = []
    for event in events:
        if event.get("event_name") != "print-email-pdf":
            continue
        for path in event.get("files_written", []):
            path_text = str(path)
            if path_text.lower().endswith(".pdf"):
                printed.append(path_text)
    return printed


def _startup_lines(events: List[Dict[str, Any]]) -> List[str]:
    startup = [event for event in events if event.get("event_name") == "startup-check"]
    if not startup:
        return ["- No startup telemetry was recorded for this date."]

    full_runs = sum(1 for event in startup if str(event.get("metrics", {}).get("startup_profile", "")).strip() == "Full")
    watch_runs = sum(1 for event in startup if str(event.get("metrics", {}).get("startup_profile", "")).strip() == "Watch")
    graph_failures = sum(1 for event in startup if event.get("metrics", {}).get("graph_startup_success") is False)
    graph_elevation = sum(1 for event in startup if bool(event.get("metrics", {}).get("graph_requires_elevation", False)))
    max_priority_queue = max((int(event.get("metrics", {}).get("startup_priority_queue", 0) or 0) for event in startup), default=0)
    root_cards = _root_card_paths(startup)
    billing_rows = sum(int(event.get("metrics", {}).get("startup_email_billing_rows_added", 0) or 0) for event in startup)
    saved_ai = sum(int(event.get("metrics", {}).get("startup_email_filing_saved_by_ai", 0) or 0) for event in startup)
    unmatched = sum(int(event.get("metrics", {}).get("startup_email_filing_unmatched", 0) or 0) for event in startup)
    bundle_updates = sum(int(event.get("metrics", {}).get("startup_bundle_todo_updated", 0) or 0) for event in startup)
    latest_run = startup[-1]

    lines = [
        f"- Startup telemetry logged {len(startup)} run(s): {full_runs} full and {watch_runs} watch.",
        f"- Graph startup failed {graph_failures} time(s) and required elevated/outside-sandbox rerun {graph_elevation} time(s).",
        f"- SQL/live-status matter refreshes observed for {len(root_cards)} unique matter(s).",
        f"- Startup email filing saved {saved_ai} item(s) by AI, added {billing_rows} billing row(s), and left {unmatched} unmatched item(s).",
    ]
    if bundle_updates > 0:
        lines.append(f"- Bundle / hearing To Do sync updated {bundle_updates} item(s).")
    if max_priority_queue > 0:
        lines.append(f"- Largest actionable startup queue seen today: {max_priority_queue}.")

    failure_classes = Counter(
        str(event.get("metrics", {}).get("graph_failure_class", "")).strip()
        for event in startup
        if str(event.get("metrics", {}).get("graph_failure_class", "")).strip()
    )
    if failure_classes:
        pairs = ", ".join(f"{key}={value}" for key, value in sorted(failure_classes.items()))
        lines.append(f"- Graph failure classes seen: {pairs}.")

    lines.append(
        f"- Latest startup run recorded at {_time_text(latest_run.get('timestamp', ''))} with email source "
        f"`{latest_run.get('metrics', {}).get('email_source', '')}`."
    )
    return lines


def _output_lines(events: List[Dict[str, Any]]) -> List[str]:
    printed = _printed_pdfs(events)
    if not printed:
        return ["- No printed PDF outputs were recorded in runtime telemetry for this date."]
    lines = [f"- Telemetry captured {len(printed)} printed PDF output(s):"]
    for path in printed[:12]:
        lines.append(f"- `{path}`")
    if len(printed) > 12:
        lines.append(f"- Plus {len(printed) - 12} more printed PDF output(s).")
    return lines


def _event_coverage_lines(events: List[Dict[str, Any]]) -> List[str]:
    if not events:
        return ["- No runtime activation events were available for this date."]
    counts = Counter(str(event.get("event_name", "")).strip() for event in events if str(event.get("event_name", "")).strip())
    pieces = ", ".join(f"`{name}`={count}" for name, count in sorted(counts.items()))
    return [
        f"- Runtime activation events captured: {len(events)}.",
        f"- Event breakdown: {pieces}.",
        "- Telemetry covers scripted work and logged outputs, but it will miss unlogged chat-only analysis, pasted notes, and any task that did not call the runtime logger.",
    ]


def _review_lines(date_text: str) -> List[str]:
    review = _weekly_review(date_text)
    proposal = _latest_adjustment_for(date_text)
    if not review:
        return ["- No derived weekly startup review file exists for this date."]

    lines = [
        f"- Weekly review window: {review.get('window_start', '')} to {review.get('window_end', '')}.",
        f"- Review totals: {review.get('run_counts', {}).get('total', 0)} startup run(s), "
        f"{review.get('graph_failure_count', 0)} Graph failure(s), "
        f"{review.get('graph_requires_elevation_count', 0)} elevation-required run(s), "
        f"{review.get('root_card_refresh_failures', 0)} root-card refresh failure(s).",
    ]

    failure_classes = review.get("graph_failure_classes", {}) or {}
    if isinstance(failure_classes, dict) and failure_classes:
        pairs = ", ".join(f"{key}={value}" for key, value in sorted(failure_classes.items()))
        lines.append(f"- Review failure classes: {pairs}.")

    proposals = list((proposal or {}).get("proposals", []) or [])
    if proposals:
        lines.append("- Top adjustment proposals:")
        for item in proposals[:4]:
            lines.append(f"- `{item.get('id', '')}`: {item.get('action', '')}")
    else:
        lines.append("- No adjustment proposals were recorded for this review date.")
    return lines


def build_markdown(date_text: str) -> str:
    events = _load_runtime_events(date_text)
    generated_local = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# {date_text} Progress",
        "",
        "> Rebuilt from runtime telemetry as a short human-readable digest. Telemetry remains the raw audit trail.",
        "",
        "## Session Summary",
    ]
    lines.extend(_event_coverage_lines(events))
    lines.extend(
        [
            "",
            "## Startup / Monitor",
            *_startup_lines(events),
            "",
            "## Recorded Outputs",
            *_output_lines(events),
            "",
            "## Friday Self-Reflection",
            *_review_lines(date_text),
            "",
            "## Limits",
            "- This digest is suitable for handover and management-facing progress checks, but it is not a substitute for the raw telemetry or the exact source files.",
            "- If a task was explored in chat or via ad-hoc shell commands without a runtime activation event, it may be absent here and should be added manually before final sign-off.",
            "",
            f"_Generated locally: {generated_local}_",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    markdown = build_markdown(args.date)
    if args.write:
        if not args.output:
            raise SystemExit("--write requires --output")
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
