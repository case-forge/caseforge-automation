#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import env_names

REPO_ROOT = Path(__file__).resolve().parents[2]
STAMP_DIRNAME = "job-stamps"
SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
MESSAGE_LIMIT = 200
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def stamp_dir(root: Path | str | None = None) -> Path:
    base = Path(root) if root else Path(os.environ.get(env_names.TELEMETRY_ROOT) or REPO_ROOT / "telemetry")
    return base / STAMP_DIRNAME


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def record(slug: str, ok: bool, message: str = "", *, root: Path | str | None = None, now: dt.datetime | None = None) -> bool:
    if not SLUG.match(str(slug or "")):
        return False
    when = (now or _now()).strftime(TIME_FORMAT)
    try:
        directory = stamp_dir(root)
        if ok:
            _write(directory / f"{slug}.ok", when + "\n")
        else:
            _write(directory / f"{slug}.fail", when + "\n" + " ".join(str(message).split())[:MESSAGE_LIMIT] + "\n")
    except OSError:
        return False
    return True


def _read_time(path: Path) -> dt.datetime | None:
    try:
        first = path.read_text(encoding="utf-8").splitlines()[0].strip()
        return dt.datetime.strptime(first, TIME_FORMAT).replace(tzinfo=dt.timezone.utc)
    except (OSError, IndexError, ValueError):
        return None


def read(slug: str, *, root: Path | str | None = None) -> dict:
    directory = stamp_dir(root)
    message = ""
    try:
        lines = (directory / f"{slug}.fail").read_text(encoding="utf-8").splitlines()
        message = lines[1].strip() if len(lines) > 1 else ""
    except OSError:
        pass
    return {"ok_at": _read_time(directory / f"{slug}.ok"), "fail_at": _read_time(directory / f"{slug}.fail"), "message": message}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2 or args[1] not in ("ok", "fail"):
        print("usage: job_stamp.py <slug> ok|fail [message]", file=sys.stderr)
        return 2
    return 0 if record(args[0], args[1] == "ok", " ".join(args[2:])) else 1


if __name__ == "__main__":
    sys.exit(main())
