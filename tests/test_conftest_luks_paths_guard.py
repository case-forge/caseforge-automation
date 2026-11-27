
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import ops_db

REAL_LUKS_PATHS = Path("/etc/caseforge-automation/luks-paths.env")


def test_the_loaded_ops_db_does_not_point_at_the_real_file() -> None:
    assert ops_db.LUKS_PATHS_ENV_FILE != REAL_LUKS_PATHS
    assert not ops_db.LUKS_PATHS_ENV_FILE.exists()
    assert ops_db.read_luks_paths_env("CASEFORGE_TELEMETRY_ROOT") == ""
    assert ops_db.read_luks_paths_env("CASEFORGE_OPS_DB") == ""


def test_the_environment_points_shell_readers_at_an_absent_file() -> None:
    value = os.environ["CASEFORGE_LUKS_PATHS_FILE"]
    assert value and Path(value) != REAL_LUKS_PATHS
    assert not Path(value).exists()


def test_a_module_imported_fresh_binds_to_the_absent_file() -> None:
    spec = importlib.util.spec_from_file_location("ops_db_fresh_copy", REPO_ROOT / "tools" / "ops_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.LUKS_PATHS_ENV_FILE == Path(os.environ["CASEFORGE_LUKS_PATHS_FILE"])
    assert module.read_luks_paths_env("CASEFORGE_OPS_DB") == ""


def test_a_test_that_needs_a_fake_file_can_still_set_its_own(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "luks-paths.env"
    fake.write_text("CASEFORGE_TELEMETRY_ROOT=/fake/encrypted/telemetry\n", encoding="utf-8")
    monkeypatch.setattr(ops_db, "LUKS_PATHS_ENV_FILE", fake)
    assert ops_db.read_luks_paths_env("CASEFORGE_TELEMETRY_ROOT") == "/fake/encrypted/telemetry"
