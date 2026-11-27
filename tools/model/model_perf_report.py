#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    rank = max(1, -(-len(sorted_values) * pct // 100))
    return round(float(sorted_values[int(rank) - 1]), 4)


def _round(value: float, ndigits: int = 1) -> float:
    return round(float(value), ndigits)


def build_model_performance(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    events = list(events)
    total = len(events)

    by_provider: dict[str, dict[str, Any]] = {}
    by_model: dict[tuple[str, str], dict[str, Any]] = {}
    failover_legs: dict[tuple[str, str], int] = {}
    served_after_failover = 0
    all_failed = 0

    for ev in events:
        provider = str(ev.get("provider") or "none")
        model = str(ev.get("selected_model") or "")
        state = str(ev.get("final_state") or "")
        completed = state == "completed"
        elapsed = float(ev.get("elapsed_seconds") or 0.0)
        attempts = []
        payload = ev.get("payload")
        if isinstance(payload, Mapping):
            raw = payload.get("attempts")
            if isinstance(raw, list):
                attempts = raw

        pg = by_provider.setdefault(
            provider,
            {"provider": provider, "events": 0, "completed": 0, "failed": 0, "_lat": []},
        )
        pg["events"] += 1
        if completed:
            pg["completed"] += 1
            pg["_lat"].append(elapsed)
        else:
            pg["failed"] += 1

        mg = by_model.setdefault(
            (model, provider),
            {"selected_model": model, "provider": provider, "events": 0, "completed": 0, "failed": 0, "_lat": []},
        )
        mg["events"] += 1
        mg["completed" if completed else "failed"] += 1
        if completed:
            mg["_lat"].append(elapsed)

        if not completed:
            all_failed += 1
        elif attempts:
            first_backend = str(attempts[0].get("backend") or "")
            if first_backend and first_backend != provider:
                served_after_failover += 1
                failover_legs[(first_backend, provider)] = failover_legs.get((first_backend, provider), 0) + 1

    def _finish(group: dict[str, Any]) -> dict[str, Any]:
        lat = sorted(group.pop("_lat"))
        group["served_share_pct"] = _round(100.0 * group["events"] / total) if total else 0.0
        group["error_rate_pct"] = _round(100.0 * group["failed"] / group["events"]) if group["events"] else 0.0
        group["latency_p50"] = _percentile(lat, 50)
        group["latency_p95"] = _percentile(lat, 95)
        group["mean_latency"] = _round(sum(lat) / len(lat), 3) if lat else 0.0
        return group

    providers = sorted((_finish(g) for g in by_provider.values()), key=lambda g: g["events"], reverse=True)
    models = sorted((_finish(g) for g in by_model.values()), key=lambda g: g["events"], reverse=True)

    return {
        "total_events": total,
        "by_provider": providers,
        "by_model": models,
        "fallback": {
            "served_after_failover": served_after_failover,
            "failover_rate_pct": _round(100.0 * served_after_failover / total) if total else 0.0,
            "all_failed": all_failed,
            "by_failover": sorted(
                ({"from_backend": frm, "to_backend": to, "count": n} for (frm, to), n in failover_legs.items()),
                key=lambda f: f["count"],
                reverse=True,
            ),
        },
    }


def render(report: Mapping[str, Any], *, window_label: str) -> str:
    lines = [
        f"\n== Model backend performance — {window_label} "
        f"({report['total_events']} runs) ==\n",
    ]
    if not report["total_events"]:
        lines.append("No deterministic model runs recorded in this window.\n")
        return "\n".join(lines)

    lines.append(f"{'backend':<10}{'runs':>6}{'share%':>8}{'err%':>7}{'p50s':>8}{'p95s':>8}{'mean':>8}")
    for p in report["by_provider"]:
        lines.append(
            f"{p['provider']:<10}{p['events']:>6}{p['served_share_pct']:>8.1f}"
            f"{p['error_rate_pct']:>7.1f}{p['latency_p50']:>8.2f}{p['latency_p95']:>8.2f}{p['mean_latency']:>8.2f}"
        )

    fb = report["fallback"]
    lines.append(
        f"\nfailover: {fb['served_after_failover']} runs served by a fallback "
        f"after the primary failed ({fb['failover_rate_pct']:.1f}% of runs); "
        f"{fb['all_failed']} runs had no backend serve at all."
    )
    for leg in fb["by_failover"]:
        lines.append(f"  {leg['from_backend']} -> {leg['to_backend']}: {leg['count']}")

    lines.append("\nby model:")
    lines.append(f"  {'model':<26}{'backend':<10}{'runs':>6}{'p50s':>8}{'p95s':>8}")
    for m in report["by_model"][:12]:
        lines.append(
            f"  {m['selected_model'][:25]:<26}{m['provider']:<10}{m['events']:>6}"
            f"{m['latency_p50']:>8.2f}{m['latency_p95']:>8.2f}"
        )
    lines.append(
        "\nread: high failover% or rising local p95/err% is the signal to retune "
        "the engine map (try qwen3:30b on MODEL_SMALL, or pull work back to paid).\n"
    )
    return "\n".join(lines)


def _fetch_events(*, days: int, date_value: str) -> list[dict[str, Any]]:
    import telemetry_sqlite

    kwargs: dict[str, Any] = {"limit": 1_000_000}
    if date_value:
        kwargs["date_value"] = date_value
    else:
        kwargs["date_from"] = (dt.date.today() - dt.timedelta(days=max(0, days))).isoformat()
    return telemetry_sqlite.list_model_context_events(**kwargs)


def _emit_telemetry(report: Mapping[str, Any], window_label: str) -> None:
    payload = {
        "event_name": "model-perf-report",
        "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files_read": [],
        "files_written": [],
        "metrics": {
            "window": window_label,
            "total_events": report["total_events"],
            "failover_rate_pct": report["fallback"]["failover_rate_pct"],
            "all_failed": report["fallback"]["all_failed"],
            "providers": {p["provider"]: p["events"] for p in report["by_provider"]},
        },
    }
    try:
        here = Path(__file__).resolve().parent
        subprocess.run(
            [sys.executable, str(here / "telemetry_sqlite.py"),
             "runtime-event", "--payload-json", json.dumps(payload)],
            check=False, capture_output=True, timeout=15,
        )
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Model backend performance report (§9).")
    parser.add_argument("--days", type=int, default=7, help="Window size in days (default 7)")
    parser.add_argument("--date", default="", help="Single day YYYY-MM-DD (overrides --days)")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table")
    parser.add_argument("--no-telemetry", action="store_true")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    events = _fetch_events(days=args.days, date_value=args.date)
    report = build_model_performance(events)
    window_label = f"date {args.date}" if args.date else f"last {args.days}d"
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report, window_label=window_label))
    if not args.no_telemetry:
        _emit_telemetry(report, window_label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
