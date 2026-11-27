from __future__ import annotations

import importlib

import pytest

apa = importlib.import_module("tools.monitoring.az_process_alert")


def _ps_output(rows):
    header = "    PID  ELAPSED COMMAND"
    lines = [header] + [f"{pid} {etimes} {args}" for pid, etimes, args in rows]
    return "\n".join(lines) + "\n"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    calls = []

    def fake_ping(base, slug, *, fail, message):
        calls.append({"base": base, "slug": slug, "fail": fail, "message": message})
        return True

    monkeypatch.setattr(apa, "_ping", fake_ping)
    return calls


def _fake_run(stdout):
    class _Result:
        pass

    def fake(*_args, **_kwargs):
        r = _Result()
        r.stdout = stdout
        return r

    return fake


def test_skips_entirely_when_ping_base_not_set(monkeypatch, no_network):
    monkeypatch.delenv("CASEFORGE_HEALTHCHECKS_PING_BASE", raising=False)
    result = apa.run(hostname="testbox")
    assert result["skipped"]
    assert no_network == []


def test_no_az_processes_pings_all_thresholds_as_success(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(apa.subprocess, "run", _fake_run(_ps_output([
        ("100", "5", "/usr/bin/python3 -m pytest"),
        ("101", "600", "/usr/sbin/sshd -D"),
    ])))
    result = apa.run(hostname="testbox")
    assert result["stuck_az_processes"] == 0
    assert len(no_network) == 3
    assert all(not call["fail"] for call in no_network)
    assert {call["slug"] for call in no_network} == {
        "az-storm-testbox-1", "az-storm-testbox-20", "az-storm-testbox-100",
    }


def test_ignores_az_processes_still_within_the_normal_runtime_window(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(apa.subprocess, "run", _fake_run(_ps_output([
        ("200", "3", "/usr/bin/az keyvault secret show --vault-name example-firm-kv"),
    ])))
    result = apa.run(hostname="testbox")
    assert result["stuck_az_processes"] == 0


def test_matches_the_underlying_python_process_not_just_the_bash_wrapper(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(apa.subprocess, "run", _fake_run(_ps_output([
        ("300", "999", "/usr/bin/python3 /usr/lib/python3/dist-packages/azure_cli/__main__.py"),
    ])))
    result = apa.run(hostname="testbox")
    assert result["stuck_az_processes"] == 1


def test_one_stuck_process_breaches_only_the_lowest_threshold(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(apa.subprocess, "run", _fake_run(_ps_output([
        ("400", "45", "/usr/bin/az login --service-principal"),
    ])))
    apa.run(hostname="testbox")
    breached = {c["slug"]: c["fail"] for c in no_network}
    assert breached["az-storm-testbox-1"] is True
    assert breached["az-storm-testbox-20"] is False
    assert breached["az-storm-testbox-100"] is False


def test_a_real_storm_breaches_every_threshold(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    rows = [(str(1000 + i), "300", "/usr/bin/az keyvault secret show") for i in range(150)]
    monkeypatch.setattr(apa.subprocess, "run", _fake_run(_ps_output(rows)))
    result = apa.run(hostname="testbox")
    assert result["stuck_az_processes"] == 150
    assert all(c["fail"] for c in no_network)


def test_slug_is_prefixed_with_hostname_to_avoid_fleet_collisions(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(apa.subprocess, "run", _fake_run(_ps_output([])))
    apa.run(hostname="prod-1")
    assert {c["slug"] for c in no_network} == {
        "az-storm-prod-1-1", "az-storm-prod-1-20", "az-storm-prod-1-100",
    }
