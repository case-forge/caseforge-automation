
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPERS = ("run-calendar-finder.sh", "run-obligation-poll.sh")

STUB_PYTHON = """#!/usr/bin/env bash
echo "TELEMETRY_ROOT=${CASEFORGE_TELEMETRY_ROOT:-unset}"
echo "OPS_DB=${CASEFORGE_OPS_DB:-unset}"
"""


def _run(tmp_path: Path, wrapper: str, luks_file: Path | None):
    root = tmp_path / "repo"
    (root / "tools").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "tools" / wrapper, root / "tools" / wrapper)
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    stub = stub_dir / "python3"
    stub.write_text(STUB_PYTHON, encoding="utf-8")
    stub.chmod(0o755)
    env = {
        "PATH": f"{stub_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "CASEFORGE_LUKS_PATHS_FILE": str(luks_file if luks_file else tmp_path / "no-such-luks-paths.env"),
    }
    proc = subprocess.run(
        ["bash", str(root / "tools" / wrapper), "--dry-run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    seen = dict(line.split("=", 1) for line in proc.stdout.splitlines() if line.startswith(("TELEMETRY_ROOT=", "OPS_DB=")))
    return seen, root


@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_wrapper_exports_the_luks_paths_to_the_job(tmp_path: Path, wrapper: str) -> None:
    luks = tmp_path / "luks-paths.env"
    luks.write_text(
        'export CASEFORGE_TELEMETRY_ROOT="/fake/encrypted/telemetry"\n'
        'export CASEFORGE_OPS_DB="/fake/encrypted/ops/caseforge-ops.sqlite3"\n',
        encoding="utf-8",
    )

    seen, root = _run(tmp_path, wrapper, luks)

    assert seen["TELEMETRY_ROOT"] == "/fake/encrypted/telemetry"
    assert seen["OPS_DB"] == "/fake/encrypted/ops/caseforge-ops.sqlite3"
    assert list((root / "telemetry").glob("*.log")), "the wrapper's own log capture must still run"


@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_wrapper_without_the_file_is_a_no_op(tmp_path: Path, wrapper: str) -> None:
    seen, root = _run(tmp_path, wrapper, None)

    assert seen["OPS_DB"] == "unset"
    if wrapper == "run-obligation-poll.sh":
        assert seen["TELEMETRY_ROOT"] == str(root / "telemetry")
    else:
        assert seen["TELEMETRY_ROOT"] == "unset"


def test_obligation_poll_default_does_not_override_the_luks_root(tmp_path: Path) -> None:
    luks = tmp_path / "luks-paths.env"
    luks.write_text('export CASEFORGE_TELEMETRY_ROOT="/fake/encrypted/telemetry"\n', encoding="utf-8")

    seen, root = _run(tmp_path, "run-obligation-poll.sh", luks)

    assert seen["TELEMETRY_ROOT"] != str(root / "telemetry")
    assert seen["TELEMETRY_ROOT"] == "/fake/encrypted/telemetry"
