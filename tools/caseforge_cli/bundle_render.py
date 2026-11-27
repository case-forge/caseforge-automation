#!/usr/bin/env python3
from __future__ import annotations

import os
import resource
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATE_SCRIPT = Path(__file__).resolve().parent / "bundletool_validate.mjs"

for sub in ("tools",):
    p = str(REPO_ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from vergil import chat_session, confined_paths
from caseforge_cli.base import CaseforgeCLIError
from caseforge_cli.bundletool import BundleToolCLI
from caseforge_cli.pdf_inputs import prepared_inputs

_RENDER_TIMEOUT_SECONDS = 300
_VALIDATE_TIMEOUT_SECONDS = 30

_RENDER_MEMORY_FLOOR_MB = 4096
_RENDER_MEMORY_CEILING_MB = 6144
_RENDER_MEMORY_BASE_MB = _RENDER_MEMORY_FLOOR_MB
_RENDER_MEMORY_ENV = "BUNDLETOOL_RENDER_MEMORY_MB"
_MEMORY_FAILURE_MARKERS = (
    "allocation failed",
    "out of memory",
    "enomem",
    "heap limit",
    "could not allocate memory",
    "unable to grow",
)
_MEMORY_FAILURE_RETURNCODES = (-5, -6, -9, 133, 134, 137)


def _box_memory_mb() -> int:
    try:
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def _default_base_mb() -> int:
    box = _box_memory_mb()
    if not box:
        return _RENDER_MEMORY_BASE_MB
    return max(_RENDER_MEMORY_FLOOR_MB, min(_RENDER_MEMORY_CEILING_MB, box // 3))


def _render_memory_limit_bytes(docs: Path) -> int:
    try:
        base_mb = int(os.environ.get(_RENDER_MEMORY_ENV, "") or _default_base_mb())
    except ValueError:
        base_mb = _default_base_mb()
    input_bytes = 0
    try:
        input_bytes = sum(f.stat().st_size for f in docs.iterdir() if f.is_file())
    except OSError:
        pass
    return base_mb * 1024 * 1024 + 4 * input_bytes


def _retry_limit_bytes(limit_bytes: int) -> int:
    box = _box_memory_mb()
    bigger = limit_bytes * 2
    return bigger if box and bigger <= box * 1024 * 1024 // 2 else 0


def _cap_memory(limit_bytes: int) -> Callable[[], None]:
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_DATA, (limit_bytes, limit_bytes))

    return apply


def _hit_memory_cap(returncode: int | None, stderr: str) -> bool:
    if returncode == 0:
        return False
    stderr = (stderr or "").lower()
    return returncode in _MEMORY_FAILURE_RETURNCODES or any(m in stderr for m in _MEMORY_FAILURE_MARKERS)


def _bundletool_repo() -> Path:
    override = os.environ.get("BUNDLETOOL_REPO_PATH", "").strip()
    if override:
        return Path(override)
    merged = Path.home() / "caseforge-website" / "bundletool"
    if (merged / "scripts" / "build-cli.mjs").is_file():
        return merged
    return Path.home() / "bundletool"


def _node_bin() -> str:
    return shutil.which("node") or "node"


def _missing_repo_error(repo: Path) -> dict:
    return chat_session.failure(
        f"bundletool checkout not found at {repo} -- set BUNDLETOOL_REPO_PATH or "
        "clone https://github.com/case-forge/bundletool to that path and run npm install.",
        plain="The bundle tool isn't set up on this server. Tell the team.",
        where="bundletool",
    )


@chat_session.refuse_when_anchored
def validate_bundle_manifest(manifest_path: str) -> dict:
    repo = _bundletool_repo()
    if not (repo / "scripts").is_dir():
        return _missing_repo_error(repo)
    path = confined_paths.resolve_within_roots(manifest_path)
    if path is None or not path.is_file():
        return {"error": f"File not found: {manifest_path}"}
    try:
        proc = subprocess.run(
            [_node_bin(), str(VALIDATE_SCRIPT), str(repo), str(path)],
            capture_output=True,
            text=True,
            timeout=_VALIDATE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return chat_session.failure(f"validator timed out: {exc}", exc, where="validate_bundle_manifest")
    import json as _json

    try:
        return _json.loads(proc.stdout.strip() or "{}")
    except ValueError:
        return chat_session.failure(
            f"validator produced no parseable output: {proc.stdout!r} {proc.stderr!r}",
            where="validate_bundle_manifest",
        )


@chat_session.refuse_when_anchored
def render_bundle(manifest_path: str, docs_dir: str, output_path: str, force: bool = False) -> dict:
    repo = _bundletool_repo()
    if not (repo / "scripts" / "build-cli.mjs").is_file():
        return _missing_repo_error(repo)
    manifest = confined_paths.resolve_within_roots(manifest_path)
    if manifest is None or not manifest.is_file():
        return {"error": f"File not found: {manifest_path}"}
    docs = confined_paths.resolve_within_roots(docs_dir)
    if docs is None or not docs.is_dir():
        return {"error": f"Directory not found: {docs_dir}"}
    output = confined_paths.resolve_within_roots(output_path)
    if output is None:
        return {"error": confined_paths.OUTSIDE_ROOTS_ERROR}
    limit_bytes = _render_memory_limit_bytes(docs)
    try:
        cli = BundleToolCLI(repo)
        with prepared_inputs(manifest, docs) as prepared:
            limit_bytes = _render_memory_limit_bytes(prepared.docs_dir)
            try:
                payload = cli.render(
                    prepared.manifest,
                    prepared.docs_dir,
                    output,
                    force=force,
                    timeout=_RENDER_TIMEOUT_SECONDS,
                    preexec_fn=_cap_memory(limit_bytes),
                )
            except CaseforgeCLIError as first:
                details = first.details if isinstance(first.details, dict) else {}
                bigger = _retry_limit_bytes(limit_bytes)
                if not bigger or not _hit_memory_cap(details.get("returncode"), f"{first.message} {details.get('stderr', '')}"):
                    raise
                limit_bytes = bigger
                payload = cli.render(
                    prepared.manifest,
                    prepared.docs_dir,
                    output,
                    force=force,
                    timeout=_RENDER_TIMEOUT_SECONDS,
                    preexec_fn=_cap_memory(limit_bytes),
                )
    except CaseforgeCLIError as exc:
        return _render_failure(exc, limit_bytes)
    if prepared.converted and isinstance(payload, dict):
        payload = {**payload, "converted": prepared.converted}
    if chat_session.in_chat():
        return {"ok": True, "message": "The bundle was built."}
    return payload


def _render_failure(exc: CaseforgeCLIError, limit_bytes: int) -> dict:
    details = exc.details if isinstance(exc.details, dict) else {}
    if exc.code == "wrapper_timeout":
        failed = chat_session.failure(f"build-cli.mjs timed out after {_RENDER_TIMEOUT_SECONDS}s", exc, where="render_bundle")
        return {"ok": False, **failed}
    returncode = details.get("returncode")
    if _hit_memory_cap(returncode, f"{exc.message} {details.get('stderr', '')}"):
        failed = chat_session.failure(
            f"build-cli.mjs failed (exit {returncode}) in a way consistent with its {limit_bytes // (1024 * 1024)} MB "
            f"memory cap; a document may be malformed or oversized -- raise {_RENDER_MEMORY_ENV} only if the bundle "
            "is genuinely large. An OOM kill or unrelated abort produces the same exit codes, so this is not proven.",
            exc,
            where="render_bundle",
            plain="The bundle couldn't be built because one of the documents is too large or malformed. Tell the team.",
        )
        return {"ok": False, **failed}
    failed = chat_session.failure(f"{exc.code}: {exc.message}", exc, where="render_bundle")
    if chat_session.in_chat():
        return {"ok": False, **failed}
    return {"ok": False, **failed, "code": exc.code, "details": details}
