
from __future__ import annotations

import os

import pytest

from tools import env_config


@pytest.fixture()
def env_file(tmp_path, monkeypatch):
    path = tmp_path / "caseforge-env"
    monkeypatch.setenv("CASEFORGE_ENV_FILE", str(path))
    return path


def test_env_var_wins_over_file(env_file, monkeypatch):
    env_file.write_text("export DEMO_KEY='from-file'\n", encoding="utf-8")
    monkeypatch.setenv("DEMO_KEY", "from-env")
    assert env_config.get("DEMO_KEY") == "from-env"


def test_file_fallback_single_quoted(env_file, monkeypatch):
    monkeypatch.delenv("DEMO_KEY", raising=False)
    env_file.write_text("export DEMO_KEY='secret-value'\n", encoding="utf-8")
    assert env_config.get("DEMO_KEY") == "secret-value"


def test_file_fallback_double_quoted(env_file, monkeypatch):
    monkeypatch.delenv("DEMO_KEY", raising=False)
    env_file.write_text('export DEMO_KEY="secret-value"\n', encoding="utf-8")
    assert env_config.get("DEMO_KEY") == "secret-value"


def test_file_fallback_bare_value_without_export(env_file, monkeypatch):
    monkeypatch.delenv("DEMO_KEY", raising=False)
    env_file.write_text("DEMO_KEY=bare-value\n", encoding="utf-8")
    assert env_config.get("DEMO_KEY") == "bare-value"


def test_missing_file_returns_default(env_file, monkeypatch):
    monkeypatch.delenv("DEMO_KEY", raising=False)
    assert not env_file.exists()
    assert env_config.get("DEMO_KEY") == ""
    assert env_config.get("DEMO_KEY", default="fallback") == "fallback"


def test_comments_and_blank_lines_ignored(env_file, monkeypatch):
    monkeypatch.delenv("DEMO_KEY", raising=False)
    env_file.write_text(
        "# comment line\n"
        "\n"
        "   # indented comment\n"
        "export DEMO_KEY='real'\n",
        encoding="utf-8",
    )
    assert env_config.get("DEMO_KEY") == "real"


def test_last_assignment_wins(env_file, monkeypatch):
    monkeypatch.delenv("DEMO_KEY", raising=False)
    env_file.write_text(
        "export DEMO_KEY='first'\nexport DEMO_KEY='second'\n", encoding="utf-8"
    )
    assert env_config.get("DEMO_KEY") == "second"


def test_empty_env_value_falls_through_to_file(env_file, monkeypatch):
    env_file.write_text("export DEMO_KEY='from-file'\n", encoding="utf-8")
    monkeypatch.setenv("DEMO_KEY", "")
    assert env_config.get("DEMO_KEY") == "from-file"


def test_whitespace_only_env_value_falls_through(env_file, monkeypatch):
    env_file.write_text("export DEMO_KEY='from-file'\n", encoding="utf-8")
    monkeypatch.setenv("DEMO_KEY", "   ")
    assert env_config.get("DEMO_KEY") == "from-file"


def test_does_not_mutate_environ(env_file, monkeypatch):
    monkeypatch.delenv("DEMO_KEY", raising=False)
    env_file.write_text("export DEMO_KEY='from-file'\n", encoding="utf-8")
    env_config.get("DEMO_KEY")
    assert "DEMO_KEY" not in os.environ


def test_unknown_key_returns_default(env_file, monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    env_file.write_text("export DEMO_KEY='x'\n", encoding="utf-8")
    assert env_config.get("NOPE_KEY", default="dflt") == "dflt"


def test_malformed_lines_skipped(env_file, monkeypatch):
    monkeypatch.delenv("DEMO_KEY", raising=False)
    env_file.write_text(
        "not a shell line\n"
        "export\n"
        "export =broken\n"
        "export DEMO_KEY='ok'\n",
        encoding="utf-8",
    )
    assert env_config.get("DEMO_KEY") == "ok"
