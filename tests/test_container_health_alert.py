from __future__ import annotations

import importlib

import pytest

cha = importlib.import_module("tools.monitoring.container_health_alert")


class _FakeCompletedProcess:
    def __init__(self, returncode, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    calls = []

    def fake_ping(base, slug, *, fail, message):
        calls.append({"base": base, "slug": slug, "fail": fail, "message": message})
        return True

    monkeypatch.setattr(cha, "_ping", fake_ping)
    return calls


def _fake_inspect(status, health=None):
    payload = f'{{"Status":"{status}"' + (f',"Health":{{"Status":"{health}"}}' if health else "") + "}"

    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(0, stdout=payload)
    return fake_run


def test_skips_entirely_when_ping_base_not_set(monkeypatch, no_network):
    monkeypatch.delenv("CASEFORGE_HEALTHCHECKS_PING_BASE", raising=False)
    result = cha.run(["caseforge-postgres"], hostname="testbox")
    assert result["skipped"]
    assert no_network == []


def test_running_healthy_container_pings_success(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(cha.subprocess, "run", _fake_inspect("running", "healthy"))
    cha.run(["caseforge-postgres"], hostname="testbox")
    assert no_network == [{
        "base": "http://caseforge:8000/ping/key",
        "slug": "container-testbox-caseforge-postgres",
        "fail": False,
        "message": "status=running health=healthy",
    }]


def test_running_with_no_healthcheck_counts_as_healthy(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(cha.subprocess, "run", _fake_inspect("running"))
    cha.run(["caseforge-memos"], hostname="testbox")
    assert no_network[0]["fail"] is False


def test_exited_container_pings_fail(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(cha.subprocess, "run", _fake_inspect("exited"))
    cha.run(["caseforge-postgres"], hostname="testbox")
    assert no_network[0]["fail"] is True


def test_unhealthy_container_pings_fail(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(cha.subprocess, "run", _fake_inspect("running", "unhealthy"))
    cha.run(["caseforge-postgres"], hostname="testbox")
    assert no_network[0]["fail"] is True


def test_missing_container_pings_fail_not_a_crash(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")

    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(1, stdout="")
    monkeypatch.setattr(cha.subprocess, "run", fake_run)
    result = cha.run(["nonexistent-container"], hostname="testbox")
    assert no_network[0]["fail"] is True
    assert result["containers"]["nonexistent-container"]["exists"] is False


def test_multiple_containers_each_get_their_own_slug(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(cha.subprocess, "run", _fake_inspect("running"))
    cha.run(["caseforge-postgres", "caseforge-qdrant"], hostname="prod-1")
    assert {c["slug"] for c in no_network} == {
        "container-prod-1-caseforge-postgres", "container-prod-1-caseforge-qdrant",
    }


def _fake_is_active(state, returncode):
    def fake_run(cmd, **kwargs):
        assert cmd[:2] == ["systemctl", "is-active"]
        return _FakeCompletedProcess(returncode, stdout=state + "\n")
    return fake_run


def test_active_unit_pings_success_under_its_bare_slug(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(cha.subprocess, "run", _fake_is_active("active", 0))
    cha.run(["unit:cloudflared"], hostname="testbox")
    assert no_network == [{
        "base": "http://caseforge:8000/ping/key",
        "slug": "container-testbox-cloudflared",
        "fail": False,
        "message": "unit=active",
    }]


@pytest.mark.parametrize("state,code", [("failed", 3), ("inactive", 3), ("activating", 3)])
def test_a_unit_that_is_not_active_pings_fail(monkeypatch, no_network, state, code):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(cha.subprocess, "run", _fake_is_active(state, code))
    cha.run(["unit:cloudflared"], hostname="testbox")
    assert no_network[0]["fail"] is True


def test_an_instance_unit_name_gets_a_slug_without_the_at_sign(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return _FakeCompletedProcess(0, stdout="active\n")

    monkeypatch.setattr(cha.subprocess, "run", fake_run)
    cha.run(["unit:postgresql@16-main"], hostname="prod-1")
    assert seen == [["systemctl", "is-active", "postgresql@16-main.service"]]
    assert no_network[0]["slug"] == "container-prod-1-postgresql-16-main"
    assert no_network[0]["fail"] is False
