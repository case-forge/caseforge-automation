from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable


class CaseforgeCLIError(Exception):

    def __init__(self, code: str, message: str, *, details: dict | None = None, tool: str = ""):
        super().__init__(f"{tool}: {code}: {message}" if tool else f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}
        self.tool = tool


class CLIUsageError(CaseforgeCLIError):
    pass


class CLIInputRejectedError(CaseforgeCLIError):
    pass


class CLIBuildError(CaseforgeCLIError):
    pass


class CLIRepoNotFound(CaseforgeCLIError):
    pass


class CLIVersionMismatch(CaseforgeCLIError):
    pass


class UnsupportedInputTypeError(CLIInputRejectedError):
    pass


class PostcodeOutsideEnglandWalesError(CLIInputRejectedError):
    pass


class PostcodeUnknownError(CLIInputRejectedError):
    pass


_EXIT_CODE_CLASSES: dict[int, type[CaseforgeCLIError]] = {
    1: CLIBuildError,
    2: CLIUsageError,
    3: CLIInputRejectedError,
}

_NAMED_ERROR_CLASSES: dict[str, type[CaseforgeCLIError]] = {
    "unsupported_input_type": UnsupportedInputTypeError,
    "postcode_outside_england_wales": PostcodeOutsideEnglandWalesError,
    "postcode_invalid": PostcodeUnknownError,
    "postcode_unknown_area": PostcodeUnknownError,
    "postcode_special_gir": PostcodeUnknownError,
    "postcode_special_bfpo": PostcodeUnknownError,
}


def node_bin() -> str:
    return shutil.which("node") or "node"


def resolve_repo(*, env_var: str, merged_relpath: str, standalone_dirname: str, entry_relpath: str) -> Path:
    override = os.environ.get(env_var, "").strip()
    if override:
        return Path(override).expanduser()
    merged = Path.home() / "caseforge-website" / merged_relpath
    if (merged / entry_relpath).is_file():
        return merged
    standalone = Path.home() / standalone_dirname
    if (standalone / entry_relpath).is_file():
        return standalone
    nested = standalone / merged_relpath
    if (nested / entry_relpath).is_file():
        return nested
    return standalone


def run_cli_json(
    argv: list[str],
    *,
    tool: str,
    cwd: Path | None,
    timeout: float,
    preexec_fn: Callable[[], None] | None = None,
) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [node_bin(), *argv],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            preexec_fn=preexec_fn,
        )
    except subprocess.TimeoutExpired as exc:
        raise CLIBuildError("wrapper_timeout", f"{tool} timed out after {timeout}s", tool=tool) from exc
    except FileNotFoundError as exc:
        raise CLIRepoNotFound("wrapper_spawn_failed", f"could not run {tool} ({exc})", tool=tool) from exc

    stdout = proc.stdout.strip()
    try:
        payload = json.loads(stdout) if stdout else None
    except ValueError:
        payload = None

    if not isinstance(payload, dict) or "ok" not in payload:
        raise CLIBuildError(
            "wrapper_unparseable_output",
            f"{tool} produced no parseable --json object (exit {proc.returncode})",
            details={
                "stdout": stdout[:2000],
                "stderr": proc.stderr.strip()[:2000],
                "returncode": proc.returncode,
            },
            tool=tool,
        )

    if payload.get("ok") is True:
        return payload

    error = payload.get("error") or {}
    code = str(error.get("code") or "unknown_error")
    message = str(error.get("message") or "")
    details = error.get("details") or {}
    cls = _NAMED_ERROR_CLASSES.get(code, _EXIT_CODE_CLASSES.get(proc.returncode, CaseforgeCLIError))
    raise cls(code, message, details=details, tool=tool)


def check_version(argv_prefix: list[str], *, tool: str, cwd: Path | None, expected: str | None) -> str:
    try:
        proc = subprocess.run(
            [node_bin(), *argv_prefix, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(cwd) if cwd else None,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise CLIRepoNotFound("version_check_failed", f"{tool} --version failed ({exc})", tool=tool) from exc

    version = proc.stdout.strip()
    if proc.returncode != 0 or not version:
        raise CLIRepoNotFound(
            "version_check_failed",
            f"{tool} --version exited {proc.returncode}: {proc.stderr.strip()[:500]}",
            tool=tool,
        )
    if expected and version != expected:
        raise CLIVersionMismatch(
            "version_mismatch",
            f"{tool} is {version}, this wrapper expects {expected}",
            details={"actual": version, "expected": expected},
            tool=tool,
        )
    return version
