
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPERS = {
    "run-calendar-finder.sh": "calendar-finder",
    "run-obligation-poll.sh": "obligation-poll",
}

STUB_PYTHON = """#!/usr/bin/env bash
echo "stub-stdout $*"
echo "stub-stderr" >&2
exit "${STUB_RC:-0}"
"""


def _run(tmp_path: Path, wrapper: str, rc: int, extra_env: dict[str, str] | None = None):
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
        "STUB_RC": str(rc),
        "CASEFORGE_LUKS_PATHS_FILE": str(tmp_path / "luks-paths-absent.env"),
        **(extra_env or {}),
    }
    proc = subprocess.run(
        ["bash", str(root / "tools" / wrapper), "--dry-run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return proc, root / "telemetry" / f"{WRAPPERS[wrapper]}.log"


@pytest.mark.parametrize("wrapper", sorted(WRAPPERS))
@pytest.mark.parametrize("rc", [0, 3])
def test_wrapper_logs_output_and_keeps_exit_code(wrapper: str, rc: int, tmp_path: Path) -> None:
    proc, log = _run(tmp_path, wrapper, rc)
    slug = WRAPPERS[wrapper]

    assert proc.returncode == rc, proc.stderr
    assert "stub-stdout" in proc.stdout and "stub-stderr" not in proc.stdout
    assert "stub-stderr" in proc.stderr

    text = log.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert f"] {slug} start" in lines[0], lines[0]
    assert lines[0].startswith("[") and "Z]" in lines[0], "run header must carry a UTC timestamp"
    assert "stub-stdout" in text and "stub-stderr" in text
    assert f"{slug} exit rc={rc}" in text


@pytest.mark.parametrize("wrapper", sorted(WRAPPERS))
def test_wrapper_log_is_size_capped(wrapper: str, tmp_path: Path) -> None:
    log = tmp_path / "repo" / "telemetry" / f"{WRAPPERS[wrapper]}.log"
    log.parent.mkdir(parents=True)
    log.write_text("old\n" * 100, encoding="utf-8")

    proc, log = _run(tmp_path, wrapper, 0, {"CASEFORGE_WRAPPER_LOG_MAX_BYTES": "100"})

    assert proc.returncode == 0, proc.stderr
    rotated = log.with_name(log.name + ".1")
    assert rotated.read_text(encoding="utf-8") == "old\n" * 100
    assert "old" not in log.read_text(encoding="utf-8")


@pytest.mark.parametrize("wrapper", sorted(WRAPPERS))
def test_wrapper_log_under_cap_is_appended(wrapper: str, tmp_path: Path) -> None:
    log = tmp_path / "repo" / "telemetry" / f"{WRAPPERS[wrapper]}.log"
    log.parent.mkdir(parents=True)
    log.write_text("previous run\n", encoding="utf-8")

    proc, log = _run(tmp_path, wrapper, 0)

    assert proc.returncode == 0, proc.stderr
    assert log.read_text(encoding="utf-8").startswith("previous run\n")
    assert not log.with_name(log.name + ".1").exists()


def test_wrappers_hardcode_no_repo_path() -> None:
    for wrapper in WRAPPERS:
        text = (REPO_ROOT / "tools" / wrapper).read_text(encoding="utf-8")
        assert "/root/caseforge-automation" not in text and "/home/" not in text, wrapper
        assert "set -x" not in text and "bash -x" not in text, wrapper
