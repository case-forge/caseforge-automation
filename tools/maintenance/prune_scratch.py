#!/usr/bin/env python3
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

SCRATCH_ROOTS = ("telemetry", "tmp", "artifacts")

PROTECTED_SUFFIXES = (".sqlite3", ".db", ".db-wal", ".db-shm", ".sqlite3-wal", ".sqlite3-shm")
PROTECTED_NAMES = (".gitkeep", "state.json")


@dataclasses.dataclass(frozen=True)
class PruneRule:

    directory: str
    age_days: int
    pattern: str = "*"


DEFAULT_RULES: tuple[PruneRule, ...] = (
    PruneRule("telemetry/graph-api-calls-archive", age_days=30),
    PruneRule("telemetry/ai-cron-responses", age_days=30),
    PruneRule("telemetry/graph-api-calls", age_days=14, pattern="*.jsonl"),
    PruneRule("tmp", age_days=14),
)


@dataclasses.dataclass
class Candidate:
    path: str
    size_bytes: int
    age_days: int
    rule: str


def _is_protected(path: Path) -> bool:
    name = path.name
    if name in PROTECTED_NAMES:
        return True
    if name.startswith("latest") or name.endswith("-active.json"):
        return True
    if any(name.endswith(suffix) for suffix in PROTECTED_SUFFIXES):
        return True
    return False


def _within_scratch_root(resolved: Path) -> bool:
    for root in SCRATCH_ROOTS:
        root_path = (REPO_ROOT / root).resolve()
        try:
            resolved.relative_to(root_path)
            return True
        except ValueError:
            continue
    return False


def _iter_files(directory: Path, pattern: str) -> Iterable[Path]:
    if not directory.is_dir():
        return
    for path in directory.rglob(pattern):
        yield path


def build_plan(
    rules: Iterable[PruneRule] = DEFAULT_RULES,
    *,
    now: dt.datetime | None = None,
    min_age_days: int | None = None,
    repo_root: Path = REPO_ROOT,
) -> list[Candidate]:
    now = now or dt.datetime.now(dt.timezone.utc)
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for rule in rules:
        age_threshold = max(rule.age_days, min_age_days or 0)
        directory = repo_root / rule.directory
        if not _within_scratch_root(directory.resolve()):
            continue
        for path in _iter_files(directory, rule.pattern):
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            if not _within_scratch_root(resolved):
                continue
            if _is_protected(path):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            mtime = dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc)
            age_days = (now - mtime).days
            if age_days < age_threshold:
                continue
            rel = str(path.relative_to(repo_root))
            if rel in seen:
                continue
            seen.add(rel)
            candidates.append(
                Candidate(path=rel, size_bytes=stat.st_size, age_days=age_days, rule=rule.directory)
            )
    return candidates


def summarise(candidates: list[Candidate]) -> dict[str, Any]:
    by_rule: dict[str, dict[str, int]] = {}
    for cand in candidates:
        bucket = by_rule.setdefault(cand.rule, {"files": 0, "bytes": 0})
        bucket["files"] += 1
        bucket["bytes"] += cand.size_bytes
    total_bytes = sum(c.size_bytes for c in candidates)
    return {
        "files": len(candidates),
        "bytes": total_bytes,
        "mib": round(total_bytes / 1048576, 1),
        "by_rule": by_rule,
    }


def apply_plan(candidates: list[Candidate], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    deleted = 0
    freed = 0
    errors: list[str] = []
    for cand in candidates:
        path = (repo_root / cand.path)
        resolved = path.resolve()
        if path.is_symlink() or not _within_scratch_root(resolved) or _is_protected(path):
            errors.append(f"refused:{cand.path}")
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            deleted += 1
            freed += size
        except OSError as exc:
            errors.append(f"{cand.path}:{exc}")
    return {"deleted": deleted, "freed_bytes": freed, "freed_mib": round(freed / 1048576, 1), "errors": errors}


def _emit_telemetry(metrics: dict[str, Any]) -> None:
    try:
        from telemetry_sqlite import record_runtime_event, utc_now_z
    except Exception:
        return
    try:
        record_runtime_event(
            {
                "timestamp": utc_now_z(),
                "event_name": "prune-scratch",
                "runtime_label": os.getenv("CASEFORGE_RUNTIME_LABEL", "prune-scratch"),
                "model_label": os.getenv("CASEFORGE_MODEL_LABEL", ""),
                "command": "tools/maintenance/prune_scratch.py --apply",
                "files_read": list(SCRATCH_ROOTS),
                "files_written": [],
                "metrics": metrics,
            }
        )
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run-first pruner for gitignored scratch/rotation logs."
    )
    parser.add_argument("--apply", action="store_true", help="Delete files. Without this, print a dry-run plan.")
    parser.add_argument("--min-age-days", type=int, default=None, help="Raise every rule's minimum age to at least this.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    candidates = build_plan(min_age_days=args.min_age_days)
    summary = summarise(candidates)

    result: dict[str, Any] = {"applied": bool(args.apply), "plan": summary}
    if args.apply:
        applied = apply_plan(candidates)
        result["result"] = applied
        _emit_telemetry({**summary, **applied, "status": "errors" if applied["errors"] else "success"})

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    verb = "Deleted" if args.apply else "Would free"
    print(f"prune_scratch: {summary['files']} files · {summary['mib']} MiB ({verb.lower()})")
    for rule, bucket in sorted(summary["by_rule"].items(), key=lambda kv: kv[1]["bytes"], reverse=True):
        print(f"  {rule}: {bucket['files']} files · {round(bucket['bytes'] / 1048576, 1)} MiB")
    if args.apply:
        applied = result["result"]
        print(f"{verb}: {applied['deleted']} files · {applied['freed_mib']} MiB freed")
        if applied["errors"]:
            print(f"  refused/errors: {len(applied['errors'])}")
    else:
        print("Dry-run only. Re-run with --apply to delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
