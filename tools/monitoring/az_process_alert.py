#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from healthchecks_ping import ping as _ping

STUCK_AFTER_SECONDS = 30

THRESHOLDS = (1, 20, 100)

_AZ_CMDLINE_RE = re.compile(r"/usr/bin/az\b|azure[-_]cli")


def stuck_az_processes(stuck_after_seconds: int = STUCK_AFTER_SECONDS) -> int:
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,etimes,args"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return 0
    count = 0
    for line in out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        _pid, etimes, args = parts
        if not _AZ_CMDLINE_RE.search(args):
            continue
        try:
            if int(etimes) >= stuck_after_seconds:
                count += 1
        except ValueError:
            continue
    return count


def _slug(hostname: str, threshold: int) -> str:
    return f"az-storm-{hostname}-{threshold}"


def run(hostname: str | None = None) -> dict:
    base = os.environ.get("CASEFORGE_HEALTHCHECKS_PING_BASE", "").strip().rstrip("/")
    hostname = hostname or socket.gethostname()
    stuck = stuck_az_processes()
    message = f"{stuck} az process(es) stuck >{STUCK_AFTER_SECONDS}s"

    result = {"stuck_az_processes": stuck, "hostname": hostname, "pinged": {}}
    if not base:
        result["skipped"] = "CASEFORGE_HEALTHCHECKS_PING_BASE not set"
        return result

    for threshold in THRESHOLDS:
        slug = _slug(hostname, threshold)
        breached = stuck >= threshold
        ok = _ping(base, slug, fail=breached, message=message)
        result["pinged"][slug] = {"breached": breached, "ok": ok}
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
