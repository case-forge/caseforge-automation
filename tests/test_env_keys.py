from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL = REPO_ROOT / "tools" / "maintenance" / "env_keys.py"
SECRET_VALUE = "planted-fake-value-for-env-keys-test"


def _load():
    spec = importlib.util.spec_from_file_location("env_keys", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load()


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text(f"HOST=smtp.resend.com\nAPI_KEY={SECRET_VALUE}\nPORT=465\n")
    return path


def test_list_never_prints_planted_value(tool, env_file: Path, capsys):
    sys.argv = ["env_keys.py", str(env_file)]
    tool.main()
    out = capsys.readouterr().out
    assert SECRET_VALUE not in out
    assert "API_KEY" in out
    assert str(len(SECRET_VALUE)) in out


def test_check_reports_presence_not_value(tool, env_file: Path, capsys):
    sys.argv = ["env_keys.py", str(env_file), "--check", "API_KEY"]
    rc = tool.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert SECRET_VALUE not in out
    assert "set (" in out


def test_check_missing_key_reports_not_set(tool, env_file: Path, capsys):
    sys.argv = ["env_keys.py", str(env_file), "--check", "NOT_A_REAL_KEY"]
    rc = tool.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "NOT SET" in out


def test_diff_keys_never_prints_values(tool, env_file: Path, tmp_path: Path, capsys):
    other = tmp_path / "other.env"
    other.write_text("HOST=smtp.resend.com\nEXTRA=whatever\n")
    sys.argv = ["env_keys.py", str(env_file), "--diff-keys", str(other)]
    tool.main()
    out = capsys.readouterr().out
    assert SECRET_VALUE not in out
    assert "API_KEY" in out
    assert "EXTRA" in out


def test_missing_file_refuses(tool, tmp_path: Path, capsys):
    sys.argv = ["env_keys.py", str(tmp_path / "nope.env")]
    rc = tool.main()
    assert rc == 1


def test_cli_subprocess_output_has_no_planted_value(env_file: Path):
    result = subprocess.run(
        [sys.executable, str(TOOL), str(env_file)],
        capture_output=True, text=True, check=True,
    )
    assert SECRET_VALUE not in result.stdout
    assert SECRET_VALUE not in result.stderr
