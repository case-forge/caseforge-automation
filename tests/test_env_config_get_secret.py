from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import env_config


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(env_config, "_kv_client", None)
    monkeypatch.setattr(env_config, "_kv_cache", {})
    yield


@pytest.fixture
def fake_vault(monkeypatch):
    calls = []

    class _FakeGot:
        def __init__(self, value):
            self.value = value

    class _FakeClient:
        def __init__(self, store):
            self._store = store

        def get_secret(self, name):
            calls.append(name)
            if name not in self._store:
                raise KeyError(name)
            return _FakeGot(self._store[name])

    store = {}
    monkeypatch.setattr(env_config, "_make_kv_client", lambda: _FakeClient(store))
    return {"store": store, "calls": calls}


def test_environment_override_wins_and_never_touches_the_vault(monkeypatch, fake_vault):
    monkeypatch.setenv("AZURE_SQL_PASSWORD", "from-env")
    secret = env_config.get_secret("azure-sql-password")
    assert secret.reveal() == "from-env"
    assert fake_vault["calls"] == []


def test_vault_backs_the_environment_and_caches_per_process(monkeypatch, fake_vault):
    monkeypatch.delenv("AZURE_SQL_PASSWORD", raising=False)
    monkeypatch.setattr(env_config, "_env_file_path", lambda: Path("/nonexistent"))
    fake_vault["store"]["azure-sql-password"] = "from-vault"
    a = env_config.get_secret("azure-sql-password")
    b = env_config.get_secret("azure-sql-password")
    assert a.reveal() == "from-vault"
    assert b is a, "second read must come from the per-process cache"
    assert fake_vault["calls"] == ["azure-sql-password"], "exactly one vault read"


def test_the_return_type_cannot_be_printed_by_accident(monkeypatch, fake_vault):
    monkeypatch.delenv("AZURE_SQL_PASSWORD", raising=False)
    monkeypatch.setattr(env_config, "_env_file_path", lambda: Path("/nonexistent"))
    fake_vault["store"]["azure-sql-password"] = "sensitive"
    secret = env_config.get_secret("azure-sql-password")
    assert "sensitive" not in str(secret)
    assert "sensitive" not in repr(secret)
    assert "sensitive" not in f"{secret}"


def test_failure_is_loud_and_names_the_fix(monkeypatch, fake_vault):
    monkeypatch.delenv("NO_SUCH_SECRET", raising=False)
    monkeypatch.setattr(env_config, "_env_file_path", lambda: Path("/nonexistent"))
    with pytest.raises(RuntimeError) as err:
        env_config.get_secret("no-such-secret")
    assert "az login" in str(err.value) or "Key Vault" in str(err.value)


def test_default_env_var_derivation_matches_the_loader_convention():
    import os
    os.environ["MY_TEST_SECRET"] = "x"
    try:
        assert env_config.get_secret("my-test-secret").reveal() == "x"
    finally:
        del os.environ["MY_TEST_SECRET"]


def test_an_explicit_env_var_name_is_honoured(monkeypatch, fake_vault):
    monkeypatch.setenv("CUSTOM_NAME", "custom-value")
    secret = env_config.get_secret("something-else", env_var="CUSTOM_NAME")
    assert secret.reveal() == "custom-value"
    assert fake_vault["calls"] == []
