from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

SOURCE_URL = "https://www.gov.uk/bank-holidays.json"
DIVISION = "england-and-wales"
SNAPSHOT = Path(__file__).with_name("bank_holidays.json")


def _state_path() -> Path:
    base = os.environ.get("CASEFORGE_STATE_DIR") or str(Path.home() / ".local" / "state" / "val")
    return Path(base) / "bank-holidays.json"


def _read(path: Path) -> list[dict[str, str]]:
    try:
        events = json.loads(path.read_text(encoding="utf-8")).get("events", [])
    except (OSError, ValueError):
        return []
    return [e for e in events if isinstance(e, dict) and e.get("date") and e.get("title")]


def holidays() -> dict[str, str]:
    events = _read(_state_path()) or _read(SNAPSHOT)
    return {str(e["date"]): str(e["title"]) for e in events}


def name_on(day: dt.date | str) -> str:
    return holidays().get(day.isoformat() if isinstance(day, dt.date) else str(day)[:10], "")


def between(first: dt.date | str, last: dt.date | str) -> dict[str, str]:
    lo, hi = str(first)[:10], str(last)[:10]
    return {d: n for d, n in sorted(holidays().items()) if lo <= d <= hi}


def refresh(fetch: Any = None) -> int:
    from atomic_json import atomic_write_json

    if fetch is None:
        with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    else:
        payload = fetch()
    events = [
        {"date": e["date"], "title": e["title"] + (" (substitute)" if "ubstitute" in str(e.get("notes", "")) else "")}
        for e in payload[DIVISION]["events"]
    ]
    if len(events) < 20:
        raise ValueError("too few bank holidays in the answer; the old copy is kept")
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, {"source": SOURCE_URL, "division": DIVISION, "events": events})
    return len(events)


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--refresh":
        print(f"bank holidays: {refresh()} events")
        return 0
    for arg in argv:
        print(name_on(arg) or "-")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main(sys.argv[1:]))
