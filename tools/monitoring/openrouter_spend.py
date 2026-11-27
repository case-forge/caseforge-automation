#!/usr/bin/env python3
"openrouter_spend.py — cached daily OpenRouter spend/credit fetch."
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import env_config
DEFAULT_STATE_PATH = REPO_ROOT / "telemetry" / "openrouter-spend.json"
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_AGE_HOURS = 24.0
MAX_HISTORY = 90
MIN_DELTA_GAP_HOURS = 20.0

CREDITS_URL = "https://openrouter.ai/api/v1/credits"
KEY_URL = "https://openrouter.ai/api/v1/key"


class OpenRouterFetchError(Exception):
    "A failed OpenRouter request. The message is always sanitised by"


def utc_now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso(value: str) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _sanitize_error(exc: Exception) -> str:
    "Short, safe description of a request failure."
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTPError {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        reason_type = type(exc.reason).__name__ if exc.reason is not None else ""
        return f"URLError {reason_type}".strip()
    return type(exc).__name__


def _get_json(url: str, api_key: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except Exception as exc:
        raise OpenRouterFetchError(_sanitize_error(exc)) from None
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise OpenRouterFetchError(f"bad JSON response ({type(exc).__name__})") from None


def _looks_masked(label: str, api_key: str) -> bool:
    "True only if ``label`` cannot be the raw key."
    if not label:
        return False
    if api_key and api_key in label:
        return False
    if api_key and len(label) >= len(api_key):
        return False
    return True


def fetch_spend(*, api_key: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    "Fetch current spend/credit numbers from OpenRouter. Stdlib only."
    key = api_key if api_key is not None else env_config.get("OPENROUTER_API_KEY")
    if not key:
        raise OpenRouterFetchError("OPENROUTER_API_KEY not set")

    credits_body = _get_json(CREDITS_URL, key, timeout)
    key_body = _get_json(KEY_URL, key, timeout)

    credits_data = credits_body.get("data") if isinstance(credits_body, dict) else None
    key_data = key_body.get("data") if isinstance(key_body, dict) else None
    credits_data = credits_data if isinstance(credits_data, dict) else {}
    key_data = key_data if isinstance(key_data, dict) else {}

    def _num(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _num_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    key_label = ""
    raw_label = key_data.get("label")
    if isinstance(raw_label, str) and _looks_masked(raw_label, key):
        key_label = raw_label

    return {
        "total_credits": _num(credits_data.get("total_credits")),
        "total_usage": _num(credits_data.get("total_usage")),
        "key_usage": _num(key_data.get("usage")),
        "key_label": key_label,
        "key_limit": _num_or_none(key_data.get("limit")),
        "key_limit_remaining": _num_or_none(key_data.get("limit_remaining")),
        "fetched_at": utc_now_z(),
    }


def _read_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _compute_delta(history: list[dict[str, Any]]) -> float | None:
    "key_usage delta between the two most recent samples, if they are at"
    if len(history) < 2:
        return None
    latest, prior = history[-1], history[-2]
    latest_dt = _parse_iso(str(latest.get("fetched_at", "")))
    prior_dt = _parse_iso(str(prior.get("fetched_at", "")))
    if latest_dt is None or prior_dt is None:
        return None
    gap_hours = (latest_dt - prior_dt).total_seconds() / 3600.0
    if gap_hours < MIN_DELTA_GAP_HOURS:
        return None
    try:
        return float(latest["key_usage"]) - float(prior["key_usage"])
    except (KeyError, TypeError, ValueError):
        return None


def refresh_if_stale(
    state_path: Path | str = DEFAULT_STATE_PATH,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    *,
    force: bool = False,
) -> dict[str, Any]:
    "Read the cached state, refetching only if missing/stale/forced."
    path = Path(state_path)
    state = _read_state(path)
    history = list(state.get("history") or [])

    fetched_at = str(state.get("fetched_at") or "")
    last_dt = _parse_iso(fetched_at) if fetched_at else None
    now = dt.datetime.now(dt.timezone.utc)
    stale = force or last_dt is None or (now - last_dt).total_seconds() / 3600.0 >= max_age_hours
    if not stale:
        return state

    try:
        sample = fetch_spend()
    except OpenRouterFetchError as exc:
        state["last_error"] = str(exc)
        state["last_error_at"] = utc_now_z()
        _write_state(path, state)
        return state

    history.append(sample)
    history = history[-MAX_HISTORY:]
    spent_last_24h = _compute_delta(history)

    new_state = dict(state)
    new_state.update(
        {
            "schema": "caseforge.openrouter-spend.v1",
            "fetched_at": sample["fetched_at"],
            "total_credits": sample["total_credits"],
            "total_usage": sample["total_usage"],
            "key_usage": sample["key_usage"],
            "key_label": sample["key_label"],
            "key_limit": sample.get("key_limit"),
            "key_limit_remaining": sample.get("key_limit_remaining"),
            "spent_last_24h": spent_last_24h,
            "history": history,
        }
    )
    _write_state(path, new_state)
    return new_state


def _format_summary(state: dict[str, Any]) -> str:
    total_credits = state.get("total_credits")
    total_usage = state.get("total_usage")
    remaining = None
    try:
        if total_credits is not None and total_usage is not None:
            remaining = float(total_credits) - float(total_usage)
    except (TypeError, ValueError):
        remaining = None
    return (
        "openrouter-spend: "
        f"fetched_at={state.get('fetched_at') or 'never'} "
        f"total_credits={state.get('total_credits')} "
        f"total_usage={state.get('total_usage')} "
        f"remaining={remaining} "
        f"spent_last_24h={state.get('spent_last_24h')} "
        f"key_limit={state.get('key_limit')} "
        f"key_limit_remaining={state.get('key_limit_remaining')} "
        f"last_error={state.get('last_error') or 'none'}"
    )


OCR_ROUTE_LABEL = "ocr-escalation"
OCR_MAX_CALLS_PER_HOUR = 200
OCR_MAX_COST_PER_HOUR_USD = 0.50
OCR_MIN_REMAINING_FRACTION = 0.25
DEFAULT_OCR_STATE_PATH = REPO_ROOT / "telemetry" / "ocr-spend-watch.json"


def ocr_hour_stats(rows: list[dict[str, Any]], now: dt.datetime, *, window_hours: float = 1.0) -> tuple[int, float]:
    "``(calls, cost_usd)`` of ``ocr-escalation`` rows recorded in the last ``window_hours``."
    cutoff = now - dt.timedelta(hours=window_hours)
    calls, cost = 0, 0.0
    for row in rows:
        if str(row.get("route_label") or "") != OCR_ROUTE_LABEL:
            continue
        when = _parse_iso(str(row.get("recorded_at") or ""))
        if when is None or when < cutoff or when > now + dt.timedelta(minutes=5):
            continue
        calls += 1
        try:
            cost += float(row.get("estimated_cost_usd") or 0.0)
        except (TypeError, ValueError):
            pass
    return calls, round(cost, 6)


def evaluate_ocr_watch(calls: int, cost: float, limit: float | None, remaining: float | None) -> list[str]:
    "Problems as short sorted-stable strings; empty when all is well. Numbers only, no client data."
    problems: list[str] = []
    if calls > OCR_MAX_CALLS_PER_HOUR:
        problems.append(f"{calls} OCR vision calls in the last hour (limit {OCR_MAX_CALLS_PER_HOUR})")
    if cost > OCR_MAX_COST_PER_HOUR_USD:
        problems.append(f"OCR vision cost ${cost:.2f} in the last hour (limit ${OCR_MAX_COST_PER_HOUR_USD:.2f})")
    if limit and remaining is not None and limit > 0 and remaining / limit < OCR_MIN_REMAINING_FRACTION:
        problems.append(f"OCR key has ${remaining:.2f} of its ${limit:.2f} limit left")
    return problems


def _ocr_rows(now: dt.datetime) -> list[dict[str, Any]]:
    import telemetry_sqlite

    return telemetry_sqlite.list_model_context_events(
        date_from=(now - dt.timedelta(hours=2)).date().isoformat(), limit=5000
    )


def _ocr_key_limits(timeout: float = DEFAULT_TIMEOUT) -> tuple[float | None, float | None]:
    key = env_config.get("OPENROUTER_OCR_API_KEY")
    if not key:
        raise OpenRouterFetchError("OPENROUTER_OCR_API_KEY not set")
    body = _get_json(KEY_URL, key, timeout)
    data = body.get("data") if isinstance(body, dict) else None
    data = data if isinstance(data, dict) else {}

    def _f(v: Any) -> float | None:
        try:
            return None if v is None else float(v)
        except (TypeError, ValueError):
            return None

    return _f(data.get("limit")), _f(data.get("limit_remaining"))


def run_ocr_watch(state_path: Path | str = DEFAULT_OCR_STATE_PATH, *, now: dt.datetime | None = None,
                  rows: list[dict[str, Any]] | None = None,
                  limits: tuple[float | None, float | None] | None = None,
                  send=None) -> list[str]:
    "One hourly pass. Speaks only when the problem set differs from the last pass; going quiet is silent."
    now = now or dt.datetime.now(dt.timezone.utc)
    path = Path(state_path)
    calls, cost = ocr_hour_stats(rows if rows is not None else _ocr_rows(now), now)
    try:
        limit, remaining = limits if limits is not None else _ocr_key_limits()
    except OpenRouterFetchError:
        limit, remaining = None, None
    problems = evaluate_ocr_watch(calls, cost, limit, remaining)
    signature = "|".join(sorted(_problem_kind(p) for p in problems))
    previous = str(_read_state(path).get("signature") or "")
    if problems and signature != previous:
        text = "CaseForge OCR spend watch: " + "; ".join(problems) + ". Check the OCR backlog; the OCR key has its own daily cap."
        if send is None:
            from monitoring import telegram_secretary_alert

            send = telegram_secretary_alert.send_ops_alert
        result = send(text)
        if isinstance(result, dict) and not result.get("sent"):
            return problems
    _write_state(path, {"signature": signature, "checked_at": now.isoformat(timespec="seconds"),
                        "calls": calls, "cost_usd": cost})
    return problems


def _problem_kind(problem: str) -> str:
    return "calls" if "calls" in problem else "cost" if "cost" in problem else "limit"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ocr-watch", action="store_true",
                        help="Hourly OCR escalation spend watch (needs OPENROUTER_OCR_API_KEY); pages only on change.")
    parser.add_argument("--force", action="store_true", help="Ignore cached freshness and refetch now.")
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH), help="State file path.")
    parser.add_argument(
        "--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS, help="Cache freshness window in hours."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.ocr_watch:
        problems = run_ocr_watch()
        print("ocr-spend-watch: " + ("; ".join(problems) if problems else "ok"))
        return 0
    state = refresh_if_stale(Path(args.state), max_age_hours=args.max_age_hours, force=bool(args.force))
    print(_format_summary(state))
    return 1 if state.get("last_error") and not state.get("fetched_at") else 0


if __name__ == "__main__":
    raise SystemExit(main())
