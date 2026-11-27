from __future__ import annotations

import os
from pathlib import Path

DEFAULT_FLAGS_FILE = "/etc/caseforge-automation/flags.env"
FLAGS_FILE_ENV = "CASEFORGE_FLAGS_FILE"


def parse_flags_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_flags_env(path: str | os.PathLike[str] | None = None) -> dict[str, str]:
    target = Path(path or os.environ.get(FLAGS_FILE_ENV) or DEFAULT_FLAGS_FILE)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return {}
    applied: dict[str, str] = {}
    for key, value in parse_flags_env(text).items():
        if key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied


def flag_value(name: str, path: str | os.PathLike[str] | None = None) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        text = Path(path or os.environ.get(FLAGS_FILE_ENV) or DEFAULT_FLAGS_FILE).read_text(encoding="utf-8")
    except OSError:
        return ""
    return parse_flags_env(text).get(name, "").strip()
