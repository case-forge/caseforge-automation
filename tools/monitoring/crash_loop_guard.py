#!/usr/bin/env python3
"Generic systemd crash-loop detector."

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_TOOLS_DIR = str(Path(__file__).resolve().parents[1])
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from atomic_json import atomic_write_json


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "telemetry" / "crash-loop-guard.json"
DEFAULT_STATE = REPO_ROOT / "telemetry" / "crash-loop-guard-state.json"

DEFAULT_RESTART_DELTA_THRESHOLD = 3
DEFAULT_ABSOLUTE_RESTART_FLOOR = 20
DEFAULT_AUTO_STOP_FLOOR = 200


def utc_now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_command(args: list[str], timeout: float, *, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=env,
        )
        return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        return {"returncode": 124, "stdout": exc.stdout or "", "stderr": exc.stderr or "", "timed_out": True}
    except FileNotFoundError as exc:
        return {"returncode": 127, "stdout": "", "stderr": str(exc), "timed_out": False}


def _user_env() -> dict[str, str]:
    env = os.environ.copy()
    runtime_dir = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    env.setdefault("XDG_RUNTIME_DIR", runtime_dir)
    bus_path = Path(runtime_dir) / "bus"
    if bus_path.exists():
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={bus_path}")
    return env


def list_service_units(scope: str, timeout: float) -> list[str]:
    args = ["systemctl"]
    env = None
    if scope == "user":
        args.append("--user")
        env = _user_env()
    args.extend(["list-units", "--all", "--type=service", "--plain", "--no-legend"])
    result = run_command(args, timeout, env=env)
    if result["returncode"] != 0:
        return []
    units = []
    for line in result["stdout"].splitlines():
        parts = line.split()
        if parts:
            units.append(parts[0])
    return units


def parse_systemctl_show(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def show_unit(scope: str, unit: str, timeout: float) -> dict[str, str]:
    args = ["systemctl"]
    env = None
    if scope == "user":
        args.append("--user")
        env = _user_env()
    args.extend(
        ["show", unit, "--property=NRestarts,ActiveState,SubState,Result,LoadState,ActiveEnterTimestamp", "--no-pager"]
    )
    result = run_command(args, timeout, env=env)
    return parse_systemctl_show(result["stdout"])


def _load_state(state_path: Path) -> dict[str, Any]:
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state_path: Path, state: dict[str, Any]) -> None:
    atomic_write_json(state_path, state)


def stop_unit(scope: str, unit: str, timeout: float) -> tuple[bool, str]:
    args = ["systemctl"]
    env = None
    if scope == "user":
        args.append("--user")
        env = _user_env()
    args.extend(["stop", unit])
    result = run_command(args, timeout, env=env)
    if result["returncode"] == 0:
        return True, "stopped"
    return False, (result["stderr"] or result["stdout"] or "systemctl stop failed").strip()[:300]


def evaluate(
    *,
    timeout: float = 5.0,
    state_path: Path = DEFAULT_STATE,
    restart_delta_threshold: int = DEFAULT_RESTART_DELTA_THRESHOLD,
    absolute_restart_floor: int = DEFAULT_ABSOLUTE_RESTART_FLOOR,
    auto_stop: bool = False,
    auto_stop_floor: int = DEFAULT_AUTO_STOP_FLOOR,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    current = now or dt.datetime.now(dt.timezone.utc)
    prev_state = _load_state(state_path)
    new_state: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []
    scanned = 0

    for scope in ("system", "user"):
        for unit in list_service_units(scope, timeout):
            scanned += 1
            key = f"{scope}:{unit}"
            fields = show_unit(scope, unit, timeout)
            try:
                nrestarts = int(fields.get("NRestarts", "0") or 0)
            except ValueError:
                nrestarts = 0

            prev = prev_state.get(key) or {}
            prev_nrestarts = int(prev.get("nrestarts", 0) or 0)
            prev_observed = prev.get("observed_utc", "")
            delta = max(0, nrestarts - prev_nrestarts) if prev else 0
            elapsed_seconds = None
            if prev_observed:
                try:
                    prev_dt = dt.datetime.fromisoformat(str(prev_observed).replace("Z", "+00:00"))
                    elapsed_seconds = max(0, int((current - prev_dt).total_seconds()))
                except ValueError:
                    elapsed_seconds = None

            new_state[key] = {"nrestarts": nrestarts, "observed_utc": utc_now_z()}

            is_flapping_now = delta >= restart_delta_threshold
            is_runaway_absolute = not prev and nrestarts >= absolute_restart_floor
            is_failed_now = fields.get("ActiveState", "") == "failed"
            if not (is_flapping_now or is_runaway_absolute or is_failed_now):
                continue

            if is_flapping_now:
                reason = "restart_delta"
            elif is_runaway_absolute:
                reason = "absolute_first_seen"
            else:
                reason = "failed_state"

            finding = {
                "scope": scope,
                "unit": unit,
                "nrestarts": nrestarts,
                "restart_delta": delta,
                "elapsed_seconds": elapsed_seconds,
                "active_state": fields.get("ActiveState", ""),
                "sub_state": fields.get("SubState", ""),
                "result": fields.get("Result", ""),
                "reason": reason,
                "auto_stop": {"attempted": False},
            }

            if auto_stop and nrestarts >= auto_stop_floor:
                ok, detail = stop_unit(scope, unit, timeout)
                finding["auto_stop"] = {"attempted": True, "ok": ok, "detail": detail}

            findings.append(finding)

    _write_state(state_path, new_state)

    if scanned == 0:
        overall = "unavailable"
    else:
        overall = "red" if findings else "green"
    payload = {
        "schema": "caseforge.crash-loop-guard.v1",
        "timestamp_utc": utc_now_z(),
        "overall": overall,
        "units_scanned": scanned,
        "findings": findings,
        "thresholds": {
            "restart_delta_threshold": restart_delta_threshold,
            "absolute_restart_floor": absolute_restart_floor,
            "auto_stop_floor": auto_stop_floor,
            "auto_stop_enabled": auto_stop,
        },
    }
    return payload


def write_payload(payload: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def record_telemetry(payload: dict[str, Any], out_path: Path | None) -> None:
    try:
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from telemetry_sqlite import record_runtime_event, record_state_snapshot

        record_runtime_event(
            {
                "timestamp": payload["timestamp_utc"],
                "event_name": "crash-loop-guard",
                "runtime_label": os.getenv("CASEFORGE_RUNTIME_LABEL", ""),
                "model_label": os.getenv("CASEFORGE_MODEL_LABEL", ""),
                "command": "tools/monitoring/crash_loop_guard.py",
                "files_read": [],
                "files_written": [safe_relative(out_path)] if out_path else [],
                "metrics": {
                    "overall": payload["overall"],
                    "units_scanned": payload["units_scanned"],
                    "finding_count": len(payload["findings"]),
                },
            }
        )
        if out_path:
            record_state_snapshot("crash_loop_guard", safe_relative(out_path), payload, observed_utc=payload["timestamp_utc"])
    except Exception:
        return


def print_human(payload: dict[str, Any]) -> None:
    print(f"overall: {payload['overall']} (scanned {payload['units_scanned']} service units)")
    for item in payload["findings"]:
        stop = item.get("auto_stop") or {}
        stop_bit = f" auto_stop={'ok' if stop.get('ok') else 'failed'}" if stop.get("attempted") else ""
        print(
            f"  [{item['reason']}] {item['scope']}:{item['unit']} "
            f"NRestarts={item['nrestarts']} delta={item['restart_delta']} "
            f"state={item['active_state']}/{item['sub_state']}{stop_bit}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--restart-delta-threshold", type=int, default=DEFAULT_RESTART_DELTA_THRESHOLD)
    parser.add_argument("--absolute-restart-floor", type=int, default=DEFAULT_ABSOLUTE_RESTART_FLOOR)
    parser.add_argument("--auto-stop-floor", type=int, default=DEFAULT_AUTO_STOP_FLOOR)
    parser.add_argument(
        "--auto-stop",
        action="store_true",
        help="Stop (never disable) units that are unambiguous runaways (NRestarts past --auto-stop-floor). "
        "Off by default, same convention as tunnel_health.py's --auto-repair: manual/inspection runs never "
        "have side effects, only an opted-in cron invocation does.",
    )
    parser.add_argument("--fail-on-red", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = evaluate(
        timeout=max(args.timeout, 1.0),
        state_path=Path(args.state),
        restart_delta_threshold=args.restart_delta_threshold,
        absolute_restart_floor=args.absolute_restart_floor,
        auto_stop=bool(args.auto_stop),
        auto_stop_floor=args.auto_stop_floor,
    )
    out_path = None if args.no_write else Path(args.out)
    if out_path and payload["overall"] != "unavailable":
        write_payload(payload, out_path)
        record_telemetry(payload, out_path)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_human(payload)
        if payload["overall"] == "unavailable":
            print(
                "  (no systemd/D-Bus visibility in this environment -- likely running inside a "
                "container; left any prior real report on disk untouched instead of overwriting it "
                "with a false green)"
            )
    if args.fail_on_red and payload["overall"] == "red":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
