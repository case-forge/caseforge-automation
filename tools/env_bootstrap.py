
from __future__ import annotations

import getpass
import os
import re
import shlex
import socket
import subprocess
import sys
from pathlib import Path
from typing import Iterable


EXPORT_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def repo_root_from_file(path: str | Path) -> Path:
    current = Path(path).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or (candidate / "AGENTS.md").exists():
            return candidate
    return Path(__file__).resolve().parent.parent


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if line.startswith("export "):
            try:
                parts = shlex.split(line, posix=True)
            except ValueError:
                parts = []
            for part in parts[1:]:
                match = EXPORT_RE.match(part)
                if match:
                    values[match.group(1)] = match.group(2)
            continue
        match = EXPORT_RE.match(line)
        if match:
            values[match.group(1)] = match.group(2).strip("'\"")
    return values


def load_repo_secrets(
    *,
    repo_root: str | Path | None = None,
    secrets_path: str | Path | None = None,
    required_keys: Iterable[str] = (),
    force: bool = False,
) -> list[str]:

    required = [str(key).strip() for key in required_keys if str(key).strip()]
    if required and all(os.getenv(key, "").strip() for key in required) and not force:
        return []
    root = Path(repo_root) if repo_root is not None else repo_root_from_file(__file__)
    override = os.environ.get("CASEFORGE_ENV_FILE", "").strip()
    if secrets_path is not None:
        path = Path(secrets_path)
    elif override:
        path = Path(override)
    else:
        path = root / ".secrets" / "caseforge-env"
    loaded: list[str] = []
    for key, value in parse_env_file(path).items():
        if required and key not in required:
            continue
        if not force and os.getenv(key, ""):
            continue
        os.environ[key] = value
        loaded.append(key)
    return loaded


_REPO_ROOT = Path(__file__).resolve().parent.parent


_SAVED_BY_SHA: list[str] = []


def saved_by_label() -> str:
    if not _SAVED_BY_SHA:
        try:
            sha = subprocess.run(["git", "-C", str(_REPO_ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            sha = ""
        _SAVED_BY_SHA.append(sha or "unknown")
    entry = " ".join([Path(sys.argv[0]).name, *sys.argv[1:2]]).strip()
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = "unknown"
    parts = [f"host={socket.gethostname()}", f"user={user}", f"checkout={_REPO_ROOT.name}@{_SAVED_BY_SHA[0]}", f"entry={entry}"]
    actor = (os.environ.get("ACTOR_LABEL") or "").strip()
    if actor:
        parts.append(f"actor={actor}")
    return " ".join(parts)


GENERIC_MODEL_LABELS = {"", "claude code", "codex", "none"}


def agent_identity() -> dict[str, str]:
    label = os.environ.get("CASEFORGE_MODEL_LABEL", "")
    model = re.sub(r"\[[^\]]*\]$", "", os.environ.get("ANTHROPIC_MODEL", "").strip())
    if model and label.strip().lower() in GENERIC_MODEL_LABELS:
        label = model
    identity = {"model_label": label}
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    if session:
        identity["agent_session_id"] = session
    return identity
