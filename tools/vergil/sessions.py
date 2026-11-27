from __future__ import annotations

import datetime as dt
import shutil
import time
from pathlib import Path

SHARED_STATE_FILES = frozenset({"model-health.json", "model-outages.json", "sql-cooldown.json"})


def load_valid_usernames(secrets_file: Path) -> set[str]:
    if not secrets_file.exists():
        return set()
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    try:
        with open(secrets_file, "rb") as handle:
            cfg = tomllib.load(handle)
    except Exception:
        return set()
    usernames = (cfg.get("credentials", {}) or {}).get("usernames") or {}
    return {str(name).lower() for name in usernames}


def owner_of_session_file(name: str) -> str:
    if name in SHARED_STATE_FILES:
        return ""
    if name.endswith("-sessions"):
        return name[: -len("-sessions")]
    if "." in name:
        return name.split(".", 1)[0]
    return ""


def orphaned_session_files(session_dir: Path, valid_usernames: set[str]) -> dict[str, list[Path]]:
    if not valid_usernames or not session_dir.exists():
        return {}
    orphaned: dict[str, list[Path]] = {}
    for path in session_dir.iterdir():
        owner = owner_of_session_file(path.name)
        if owner and owner.lower() not in valid_usernames:
            orphaned.setdefault(owner, []).append(path)
    return {owner: sorted(paths) for owner, paths in sorted(orphaned.items())}


def delete_orphaned_session_files(paths: list[Path], session_dir: Path) -> tuple[int, list[str]]:
    session_root = session_dir.resolve()
    deleted = 0
    errors: list[str] = []
    for path in paths:
        try:
            resolved = path.resolve()
            if resolved.parent != session_root:
                errors.append(f"{path.name}: outside the session directory, skipped")
                continue
            if resolved.is_dir():
                shutil.rmtree(resolved)
            else:
                resolved.unlink(missing_ok=True)
            deleted += 1
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    return deleted, errors


def expired_session_files(archive_dir: Path, ttl_days: int, *, now: float | None = None) -> list[Path]:
    if ttl_days <= 0 or not archive_dir.exists():
        return []
    import json

    cutoff = (time.time() if now is None else now) - ttl_days * 86400
    expired: list[Path] = []
    for path in sorted(archive_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if bool(data.get("starred", False)):
            continue
        stamp = path.stat().st_mtime
        updated = str(data.get("updated_utc") or "").strip()
        if updated:
            try:
                stamp = dt.datetime.fromisoformat(updated.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
        if stamp < cutoff:
            expired.append(path)
    return expired


def prune_expired_sessions(archive_dir: Path, ttl_days: int, *, now: float | None = None) -> int:
    pruned = 0
    for path in expired_session_files(archive_dir, ttl_days, now=now):
        try:
            path.unlink(missing_ok=True)
            pruned += 1
        except OSError:
            continue
    return pruned


def prune_expired_sessions_throttled(
    archive_dir: Path,
    ttl_days: int,
    *,
    key: str,
    state: dict[str, float],
    interval_seconds: float,
    now: float | None = None,
) -> int:
    if ttl_days <= 0:
        return 0
    stamp = time.time() if now is None else now
    if stamp - state.get(key, 0.0) < interval_seconds:
        return 0
    state[key] = stamp
    return prune_expired_sessions(archive_dir, ttl_days, now=stamp)
