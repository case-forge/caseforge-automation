#!/usr/bin/env python3
"Tiered disk-usage alerting via the self-hosted Healthchecks instance."
from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import disk_space
from healthchecks_ping import ping as _ping

THRESHOLDS = (70, 80, 90)


def disk_usage_percent(path: str) -> float:
    return round(disk_space.used_pct(path), 1)


def _slug(hostname: str, threshold: int) -> str:
    return f"disk-{hostname}-{threshold}"


def run(path: str = "/", hostname: str | None = None) -> dict:
    base = os.environ.get("CASEFORGE_HEALTHCHECKS_PING_BASE", "").strip().rstrip("/")
    hostname = hostname or socket.gethostname()
    pct = disk_usage_percent(path)
    message = f"{path} at {pct}% used"

    result = {"path": path, "percent_used": pct, "hostname": hostname, "pinged": {}}
    if not base:
        result["skipped"] = "CASEFORGE_HEALTHCHECKS_PING_BASE not set"
        return result

    for threshold in THRESHOLDS:
        slug = _slug(hostname, threshold)
        breached = pct >= threshold
        ok = _ping(base, slug, fail=breached, message=message)
        result["pinged"][slug] = {"breached": breached, "ok": ok}

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default="/", help="Filesystem path to check (default: /)")
    args = parser.parse_args()
    result = run(path=args.path)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
