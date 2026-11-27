#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GBP_PER_USD = 0.79


def _read_events(days: int) -> list[dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import telemetry_sqlite

    date_from = (dt.date.today() - dt.timedelta(days=max(0, days))).isoformat()
    return telemetry_sqlite.list_model_context_events(date_from=date_from, limit=1_000_000)


def _summarise(rows: list[dict]) -> dict:
    total_cost = 0.0
    total_input = 0
    total_output = 0
    by_model: dict[str, dict] = defaultdict(lambda: {"runs": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0})
    by_day: dict[str, float] = defaultdict(float)
    costed_runs = 0

    for row in rows:
        model = row.get("selected_model") or row.get("provider") or "unknown"
        cost = float(row.get("estimated_cost_usd", 0) or 0)
        inp = int(row.get("input_tokens", 0) or 0)
        out = int(row.get("output_tokens", 0) or 0)

        by_model[model]["runs"] += 1
        by_model[model]["cost_usd"] += cost
        by_model[model]["input_tokens"] += inp
        by_model[model]["output_tokens"] += out

        total_cost += cost
        total_input += inp
        total_output += out
        if cost > 0:
            costed_runs += 1

        day = str(row.get("recorded_at", ""))[:10]
        by_day[day] += cost

    return {
        "total_runs": len(rows),
        "costed_runs": costed_runs,
        "total_cost_usd": round(total_cost, 4),
        "total_cost_gbp": round(total_cost * GBP_PER_USD, 4),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "by_model": {k: {**v, "cost_usd": round(v["cost_usd"], 4)} for k, v in sorted(by_model.items())},
        "by_day": dict(sorted(by_day.items())),
    }


def _format_report(summary: dict, days: int) -> str:
    lines = [
        f"# AI Cost Summary - last {days} days",
        f"",
        f"**Total runs:** {summary['total_runs']}  "
        f"({summary['costed_runs']} with token data)",
        f"**Total cost:** ${summary['total_cost_usd']:.4f} USD  "
        f"/ £{summary['total_cost_gbp']:.4f} GBP",
        f"**Tokens:** {summary['total_input_tokens']:,} in  "
        f"/ {summary['total_output_tokens']:,} out",
        f"",
        f"## By model",
    ]
    for model, data in summary["by_model"].items():
        lines.append(
            f"- **{model}**: {data['runs']} runs  "
            f"· ${data['cost_usd']:.4f}  "
            f"· {data['input_tokens']:,} in / {data['output_tokens']:,} out"
        )
    lines += ["", "## Daily spend (USD)"]
    for day, cost in summary["by_day"].items():
        bar = "█" * max(1, int(cost * 200)) if cost > 0 else "-"
        lines.append(f"- {day}: ${cost:.4f}  {bar}")
    if not summary["by_day"]:
        lines.append("- No costed runs yet (token data requires recent runs with Claude)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AI cost summary from model_context_events telemetry")
    parser.add_argument("--days", type=int, default=7, help="Look-back window in days (default: 7)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Output raw JSON")
    args = parser.parse_args()

    rows = _read_events(args.days)
    if not rows:
        print(f"No model_context_events in the last {args.days} days.", file=sys.stderr)
        return 0

    summary = _summarise(rows)

    if args.as_json:
        print(json.dumps(summary, indent=2))
    else:
        print(_format_report(summary, args.days))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
