from __future__ import annotations

import os
import tempfile
from pathlib import Path

RENDER_DIR_ENV = "VERGIL_RENDER_DIR"
RENDER_ROOT_ENV = "VERGIL_RENDER_ROOT"
EXTRA_ROOTS_ENV = "VERGIL_LOCAL_ROOTS"

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

OUTSIDE_ROOTS_ERROR = "That file is outside the folder this tool may use."


def render_root() -> Path:
    override = os.environ.get(RENDER_ROOT_ENV, "").strip()
    root = Path(override) if override else Path(tempfile.gettempdir()) / f"vergil-renders-{os.getuid()}"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def session_render_dir(session_id: str) -> Path:
    safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_") or "session"
    path = render_root() / safe
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def allowed_roots() -> list[Path]:
    session_dir = os.environ.get(RENDER_DIR_ENV, "").strip()
    if session_dir:
        roots = [Path(session_dir)]
    else:
        roots = [render_root(), _REPO_ROOT / "tmp", _REPO_ROOT / "artifacts"]
        roots += [Path(p) for p in os.environ.get(EXTRA_ROOTS_ENV, "").split(os.pathsep) if p.strip()]
    return [Path(os.path.realpath(r)) for r in roots]


def resolve_within_roots(raw: str | os.PathLike) -> Path | None:
    try:
        real = Path(os.path.realpath(raw))
    except (OSError, ValueError):
        return None
    return real if any(real.is_relative_to(root) for root in allowed_roots()) else None


def default_output_dir() -> Path:
    session_dir = os.environ.get(RENDER_DIR_ENV, "").strip()
    path = Path(session_dir) if session_dir else render_root()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path
