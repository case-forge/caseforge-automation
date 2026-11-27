#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
import datetime as dt
import subprocess

SERVICES = [
    {"name": "cloudflared", "unit": "cloudflared.service", "scope": "system",
     "label": "Cloudflare tunnel (public route into caseforge-chat/webhooks)"},
]


def utc_now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _systemctl_env(scope: str) -> dict[str, str] | None:
    if scope != "user":
        return None
    env = os.environ.copy()
    runtime_dir = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    env.setdefault("XDG_RUNTIME_DIR", runtime_dir)
    bus_path = Path(runtime_dir) / "bus"
    if bus_path.exists():
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={bus_path}")
    return env


def check_active(unit: str, scope: str, timeout: float = 5.0) -> tuple[bool, str]:
    args = ["systemctl"]
    if scope == "user":
        args.append("--user")
    args.extend(["is-active", unit])
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=_systemctl_env(scope))
        state = (proc.stdout or "").strip() or (proc.stderr or "").strip() or "unknown"
        return state == "active", state
    except subprocess.TimeoutExpired:
        return False, "systemctl timed out"
    except Exception as exc:
        return False, type(exc).__name__


def restart_service(unit: str, scope: str, timeout: float = 30.0) -> tuple[bool, str]:
    args = ["systemctl"]
    if scope == "user":
        args.append("--user")
    args.extend(["restart", unit])
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=_systemctl_env(scope))
        if proc.returncode == 0:
            return True, "restarted"
        return False, (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[:300]
    except subprocess.TimeoutExpired:
        return False, "systemctl restart timed out"
    except Exception as exc:
        return False, type(exc).__name__


def read_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
