from __future__ import annotations

import importlib

import pytest

hp = importlib.import_module("tools.monitoring.healthchecks_ping")


@pytest.fixture(autouse=True)
def _no_leaked_heartbeats():
    yield
    for slug in list(hp._HEARTBEAT_THREADS):
        hp.stop_heartbeat(slug)


def test_ping_succeeds_on_first_attempt(monkeypatch):
    calls = []

    def fake_post(url, message):
        calls.append(url)
        return True

    monkeypatch.setattr(hp, "_post", fake_post)
    assert hp.ping("http://caseforge:8000/ping/key", "disk-caseforge-70", fail=False, message="ok") is True
    assert calls == ["http://caseforge:8000/ping/key/disk-caseforge-70?create=1"]


def test_fail_suffix_is_appended_when_fail_true(monkeypatch):
    calls = []
    monkeypatch.setattr(hp, "_post", lambda url, message: calls.append(url) or True)
    hp.ping("http://caseforge:8000/ping/key", "disk-caseforge-90", fail=True, message="critical")
    assert calls == ["http://caseforge:8000/ping/key/disk-caseforge-90/fail?create=1"]


def test_falls_back_to_loopback_when_hostname_unreachable(monkeypatch):
    attempted = []

    def fake_post(url, message):
        attempted.append(url)
        return "127.0.0.1" in url

    monkeypatch.setattr(hp, "_post", fake_post)
    result = hp.ping("http://caseforge:8000/ping/key", "disk-caseforge-70", fail=False, message="ok")
    assert result is True
    assert attempted == [
        "http://caseforge:8000/ping/key/disk-caseforge-70?create=1",
        "http://127.0.0.1:8000/ping/key/disk-caseforge-70?create=1",
    ]


def test_returns_false_when_both_attempts_fail(monkeypatch):
    monkeypatch.setattr(hp, "_post", lambda url, message: False)
    assert hp.ping("http://caseforge:8000/ping/key", "disk-caseforge-70", fail=False, message="ok") is False


def test_no_fallback_when_already_loopback(monkeypatch):
    attempted = []
    monkeypatch.setattr(hp, "_post", lambda url, message: attempted.append(url) or False)
    hp.ping("http://127.0.0.1:8000/ping/key", "disk-caseforge-70", fail=False, message="ok")
    assert attempted == ["http://127.0.0.1:8000/ping/key/disk-caseforge-70?create=1"]



def test_start_heartbeat_is_a_noop_without_base_url(monkeypatch):
    monkeypatch.delenv("CASEFORGE_HEALTHCHECKS_PING_BASE", raising=False)
    assert hp.start_heartbeat("noop-job") is None


def test_start_heartbeat_pings_repeatedly(monkeypatch):
    import time

    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    calls = []
    monkeypatch.setattr(hp, "_post", lambda url, message: calls.append(url) or True)
    hp._HEARTBEAT_THREADS.pop("repeat-job", None)
    thread = hp.start_heartbeat("repeat-job", interval_seconds=0.05)
    assert thread is not None
    time.sleep(0.18)
    assert len(calls) >= 2
    assert all(c == "http://caseforge:8000/ping/key/repeat-job?create=1" for c in calls)


def test_start_heartbeat_is_idempotent_per_slug(monkeypatch):
    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    monkeypatch.setattr(hp, "_post", lambda url, message: True)
    hp._HEARTBEAT_THREADS.pop("idempotent-job", None)
    first = hp.start_heartbeat("idempotent-job", interval_seconds=5.0)
    second = hp.start_heartbeat("idempotent-job", interval_seconds=5.0)
    assert first is second


def test_stop_heartbeat_ends_the_thread_and_its_pings(monkeypatch):
    import time

    monkeypatch.setenv("CASEFORGE_HEALTHCHECKS_PING_BASE", "http://caseforge:8000/ping/key")
    calls = []
    monkeypatch.setattr(hp, "_post", lambda url, message: calls.append(url) or True)
    thread = hp.start_heartbeat("stoppable-job", interval_seconds=0.02)
    time.sleep(0.1)
    hp.stop_heartbeat("stoppable-job")

    assert not thread.is_alive()
    assert "stoppable-job" not in hp._HEARTBEAT_THREADS
    settled = len(calls)
    time.sleep(0.1)
    assert len(calls) == settled, "a stopped heartbeat must not ping again"

    restarted = hp.start_heartbeat("stoppable-job", interval_seconds=5.0)
    assert restarted is not thread and restarted.is_alive()


def test_stop_heartbeat_on_an_unknown_slug_is_a_noop():
    hp.stop_heartbeat("never-started")
