from __future__ import annotations

import importlib

import pytest

dua = importlib.import_module("tools.monitoring.disk_usage_alert")


def _disk_usage(total, used):
    def fake(_path):
        free = total - used
        return type("V", (), {"f_blocks": total, "f_bfree": free, "f_bavail": free, "f_frsize": 1})()
    return fake


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    calls = []

    def fake_ping(base, slug, *, fail, message):
        calls.append({"base": base, "slug": slug, "fail": fail, "message": message})
        return True

    monkeypatch.setattr(dua, "_ping", fake_ping)
    return calls


def test_skips_entirely_when_ping_base_not_set(monkeypatch, no_network):
    monkeypatch.delenv("CASEFORGE_HEALTHCHECKS_PING_BASE", raising=False)
    result = dua.run(hostname="testbox")
    assert result["skipped"]
    assert no_network == []


def test_low_usage_pings_all_three_thresholds_as_success(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(dua.disk_space.os, "statvfs", _disk_usage(100, 50))
    dua.run(hostname="testbox")
    assert len(no_network) == 3
    assert all(not call["fail"] for call in no_network)
    assert {call["slug"] for call in no_network} == {
        "disk-testbox-70", "disk-testbox-80", "disk-testbox-90",
    }


def test_75_percent_breaches_only_the_70_threshold(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(dua.disk_space.os, "statvfs", _disk_usage(100, 75))
    dua.run(hostname="testbox")
    breached = {c["slug"]: c["fail"] for c in no_network}
    assert breached["disk-testbox-70"] is True
    assert breached["disk-testbox-80"] is False
    assert breached["disk-testbox-90"] is False


def test_95_percent_breaches_all_three_thresholds(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(dua.disk_space.os, "statvfs", _disk_usage(100, 95))
    dua.run(hostname="testbox")
    assert all(c["fail"] for c in no_network)


def test_slug_is_prefixed_with_hostname_to_avoid_fleet_collisions(monkeypatch, no_network):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(dua.disk_space.os, "statvfs", _disk_usage(100, 10))
    dua.run(hostname="prod-1")
    assert {c["slug"] for c in no_network} == {
        "disk-prod-1-70", "disk-prod-1-80", "disk-prod-1-90",
    }
