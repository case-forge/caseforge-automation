from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil import runtime_control as rc


def test_env_admin_is_permitted_regardless_of_user_record(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CASEFORGE_CHAT_ADMIN_USERS", "solicitor@firm.example.test, other@example.test")
    assert rc.restart_permitted("solicitor@firm.example.test", {}) is True


def test_env_admin_check_is_case_and_space_insensitive(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CASEFORGE_CHAT_ADMIN_USERS", " Solicitor@Example.Test ")
    assert rc.restart_permitted("solicitor@example.test", {}) is True


def test_user_with_admin_role_is_permitted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CASEFORGE_CHAT_ADMIN_USERS", raising=False)
    users = {"caseworker": {"roles": ["admin"]}}
    assert rc.restart_permitted("caseworker", users) is True


def test_user_with_supervisor_role_is_permitted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CASEFORGE_CHAT_ADMIN_USERS", raising=False)
    users = {"caseworker": {"roles": "supervisor"}}
    assert rc.restart_permitted("caseworker", users) is True


def test_ordinary_user_is_not_permitted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CASEFORGE_CHAT_ADMIN_USERS", raising=False)
    users = {"caseworker": {"roles": ["fee-earner"]}}
    assert rc.restart_permitted("caseworker", users) is False


def test_unknown_username_is_not_permitted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CASEFORGE_CHAT_ADMIN_USERS", raising=False)
    assert rc.restart_permitted("nobody", {}) is False


def test_a_developer_is_also_an_admin_but_an_admin_is_not_a_developer(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CASEFORGE_CHAT_ADMIN_USERS", "admin@example.test")
    monkeypatch.setenv("CASEFORGE_DEV_USERS", " Dev@Example.Test ")
    assert rc.is_env_dev("dev@example.test") and rc.is_env_admin("dev@example.test")
    assert rc.is_env_admin("admin@example.test") and not rc.is_env_dev("admin@example.test")
    assert not rc.is_env_dev("") and not rc.is_env_dev("someone@example.test")


def test_no_developer_when_the_variable_is_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CASEFORGE_DEV_USERS", raising=False)
    monkeypatch.setenv("CASEFORGE_CHAT_ADMIN_USERS", "admin@example.test")
    assert rc.env_dev_users() == set() and not rc.is_env_dev("admin@example.test")


def test_kill_is_a_no_op_once_the_run_has_finished():
    run = {"finished": True}
    rc.kill_active_process(run, "timed out after 60s")
    assert "cancel_reason" not in run
    assert "cancel_requested" not in run


def test_kill_records_reason_and_marks_cancel_requested():
    run: dict = {}
    rc.kill_active_process(run, "user cancelled")
    assert run["cancel_reason"] == "user cancelled"
    assert run["cancel_requested"] is True
    assert run["timeout_requested"] is False


def test_kill_sets_timeout_requested_when_reason_starts_with_timed_out():
    run: dict = {}
    rc.kill_active_process(run, "Timed out after 300s")
    assert run["timeout_requested"] is True


def test_kill_prefers_process_group_over_process_object(monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setattr(rc.os, "killpg", lambda pgid, sig: calls.append((pgid, sig)))
    proc = MagicMock()
    run = {"pgid": 4242, "process": proc}

    rc.kill_active_process(run, "user cancelled")

    assert calls == [(4242, rc.signal.SIGTERM)]
    proc.terminate.assert_not_called()


def test_kill_falls_back_to_process_terminate_when_no_pgid():
    proc = MagicMock()
    run = {"process": proc}
    rc.kill_active_process(run, "user cancelled")
    proc.terminate.assert_called_once()


def test_kill_swallows_process_lookup_error(monkeypatch: pytest.MonkeyPatch):
    def _raise(pgid, sig):
        raise ProcessLookupError()

    monkeypatch.setattr(rc.os, "killpg", _raise)
    run = {"pgid": 999999, "process": MagicMock()}
    rc.kill_active_process(run, "already gone")


def test_kill_swallows_unexpected_errors_from_terminate():
    proc = MagicMock()
    proc.terminate.side_effect = RuntimeError("boom")
    run = {"process": proc}
    rc.kill_active_process(run, "user cancelled")


def test_populates_missing_graph_env_vars(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rc.os, "environ", {})
    rc.ensure_graph_env_for_current_process({"GRAPH_TENANT_ID": "tenant-fixture"})
    assert os.environ == {"GRAPH_TENANT_ID": "tenant-fixture"}


def test_does_not_overwrite_an_existing_env_var(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rc.os, "environ", {"GRAPH_TENANT_ID": "already-set"})
    rc.ensure_graph_env_for_current_process({"GRAPH_TENANT_ID": "fixture-value"})
    assert os.environ["GRAPH_TENANT_ID"] == "already-set"


def test_ignores_blank_and_unrecognised_keys(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rc.os, "environ", {})
    rc.ensure_graph_env_for_current_process({"GRAPH_TENANT_ID": "   ", "NOT_A_GRAPH_KEY": "value"})
    assert os.environ == {}


def test_populates_every_known_graph_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rc.os, "environ", {})
    env = {
        "GRAPH_TENANT_ID": "1",
        "GRAPH_MAILBOX_UPN": "2",
        "GRAPH_FILES_CLIENT_ID": "3",
        "GRAPH_FILES_CLIENT_SECRET": "4",
        "GRAPH_MAIL_CLIENT_ID": "5",
        "GRAPH_MAIL_CLIENT_SECRET": "6",
        "GRAPH_CLIENT_ID": "7",
        "GRAPH_CLIENT_SECRET": "8",
        "SHAREPOINT_CLIENT_FILES_SITE_ID": "9",
    }
    rc.ensure_graph_env_for_current_process(env)
    assert os.environ == env
