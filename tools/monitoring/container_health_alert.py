#!/usr/bin/env python3
"Alert if an expected Docker container isn't running+healthy."
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from healthchecks_ping import ping as _ping


def container_status(name: str) -> dict:
    "Inspect one container. Never raises -- a missing/errored container"
    result = subprocess.run(
        ["docker", "inspect", name, "--format", "{{json .State}}"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        return {"exists": False, "healthy": False, "detail": "not found"}
    try:
        state = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"exists": True, "healthy": False, "detail": "unparseable docker inspect output"}
    status = state.get("Status", "")
    health = (state.get("Health") or {}).get("Status")
    healthy = status == "running" and health in (None, "healthy")
    detail = f"status={status}" + (f" health={health}" if health else "")
    return {"exists": True, "healthy": healthy, "detail": detail}


def unit_status(name: str) -> dict:
    "Inspect one systemd unit. Never raises -- an absent or failed unit is"
    unit = name if "." in name else f"{name}.service"
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"exists": False, "healthy": False, "detail": f"systemctl failed: {type(exc).__name__}"}
    state = (result.stdout or "").strip() or "unknown"
    return {"exists": state != "unknown", "healthy": state == "active", "detail": f"unit={state}"}


def run(containers: list[str], hostname: str | None = None) -> dict:
    base = os.environ.get("CASEFORGE_HEALTHCHECKS_PING_BASE", "").strip().rstrip("/")
    hostname = hostname or socket.gethostname()

    result = {"hostname": hostname, "containers": {}}
    if not base:
        result["skipped"] = "CASEFORGE_HEALTHCHECKS_PING_BASE not set"
        return result

    for name in containers:
        if name.startswith("unit:"):
            name = name[len("unit:"):]
            status = unit_status(name)
        else:
            status = container_status(name)
        slug = f"container-{hostname}-" + re.sub(r"[^A-Za-z0-9_-]+", "-", name)
        ok = _ping(base, slug, fail=not status["healthy"], message=status["detail"])
        result["containers"][name] = {**status, "pinged_ok": ok}

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "containers", nargs="+",
        help="Container names to check, e.g. caseforge-qdrant documenso-documenso-1; unit:<name> checks a systemd unit, e.g. unit:cloudflared",
    )
    args = parser.parse_args()
    print(run(args.containers))
    return 0


if __name__ == "__main__":
    sys.exit(main())
