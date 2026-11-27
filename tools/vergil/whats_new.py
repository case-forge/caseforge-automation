#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import threading
from pathlib import Path
from typing import Any

LIMIT = 50
SCAN = 2000
MARKER = "Shown-to-users:"
_LINE_RE = re.compile(r"^\s*Shown-to-users:\s*(.+?)\s*$", re.MULTILINE)
_FIELD, _RECORD = "\x1f", "\x1e"
_NOTHING = {"none", "n/a", "na", "-", "nothing", "no"}

_LOCK = threading.Lock()
_CACHE: dict[str, list[dict[str, str]]] = {}


def _git(root: Path | None, *args: str) -> str:
    cwd = root or Path(__file__).resolve().parent
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10, check=True).stdout


def repo_root() -> Path:
    return Path(_git(None, "rev-parse", "--show-toplevel").strip())


def parse_log(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in text.split(_RECORD):
        parts = record.strip("\n").split(_FIELD)
        if len(parts) != 3:
            continue
        sha, date, body = (p.strip() for p in parts)
        for match in _LINE_RE.finditer(body):
            note = " ".join(match.group(1).split())[:500]
            if note.rstrip(".").lower() in _NOTHING:
                continue
            note = note[:1].upper() + note[1:]
            if note and note not in seen:
                seen.add(note)
                items.append({"sha": sha, "date": date, "note": note})
    return items


def notes(root: Path | None = None, *, limit: int = LIMIT) -> dict[str, Any]:
    try:
        base = root or repo_root()
        head = _git(base, "rev-parse", "HEAD").strip()
    except Exception:
        return {"head": "", "items": []}
    with _LOCK:
        cached = _CACHE.get(f"{base}:{head}")
    if cached is None:
        try:
            log = _git(base, "log", f"-n{SCAN}", f"--grep={MARKER}", "--fixed-strings", f"--format=%H{_FIELD}%cI{_FIELD}%B{_RECORD}", "HEAD")
            cached = parse_log(log)
        except Exception:
            cached = []
        with _LOCK:
            _CACHE.clear()
            _CACHE[f"{base}:{head}"] = cached
    return {"head": head, "items": cached[:limit]}
