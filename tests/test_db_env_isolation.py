from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

SENTINEL_PG = "postgresql://sentinel-must-not-be-visible/db"
SENTINEL_AZURE = "Server=sentinel-must-not-be-visible;Database=x;"

INNER = '''
    import os

    def test_the_db_urls_are_not_visible():
        assert os.environ.get("CASEFORGE_CLIENTDB_PG_URL") is None
        assert os.environ.get("AZURE_SQL_CONNECTION_STRING") is None
'''


def _run(tmp_path: Path, inner: str) -> subprocess.CompletedProcess:
    test_file = tmp_path / "test_inner_db_env.py"
    test_file.write_text(textwrap.dedent(inner), encoding="utf-8")
    env = dict(os.environ)
    env["CASEFORGE_CLIENTDB_PG_URL"] = SENTINEL_PG
    env["AZURE_SQL_CONNECTION_STRING"] = SENTINEL_AZURE
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q", "-p", "no:cacheprovider",
         "--rootdir", str(REPO_ROOT), "-c", str(REPO_ROOT / "pyproject.toml")],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=180,
    )


@pytest.mark.slow
def test_the_sentinels_really_do_reach_a_subprocess_without_the_conftest(tmp_path):
    proof = '''
    import os

    def test_sentinels_are_visible():
        assert os.environ.get("CASEFORGE_CLIENTDB_PG_URL") == "postgresql://sentinel-must-not-be-visible/db"
        assert os.environ.get("AZURE_SQL_CONNECTION_STRING") == "Server=sentinel-must-not-be-visible;Database=x;"
    '''
    result = _run(tmp_path, proof)
    assert result.returncode == 0, (
        "the sentinel values did not reach the subprocess at all, so the absence "
        f"assertion below would be vacuous.\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.slow
def test_conftest_clears_both_db_urls_even_when_the_host_exports_them(tmp_path):
    test_file = tmp_path / "test_inner_db_env.py"
    test_file.write_text(textwrap.dedent(INNER), encoding="utf-8")
    env = dict(os.environ)
    env["CASEFORGE_CLIENTDB_PG_URL"] = SENTINEL_PG
    env["AZURE_SQL_CONNECTION_STRING"] = SENTINEL_AZURE
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT / "tests"), env.get("PYTHONPATH", "")]))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q", "-p", "no:cacheprovider", "-p", "conftest",
         "--rootdir", str(REPO_ROOT), "-c", str(REPO_ROOT / "pyproject.toml")],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, (
        "a test run with tests/conftest.py could still see the host's database connection "
        f"strings.\n{result.stdout}\n{result.stderr}"
    )
