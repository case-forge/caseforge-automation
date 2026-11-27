
from __future__ import annotations

import datetime as dt
import importlib
from pathlib import Path

import pytest

poll = importlib.import_module("products.ikoro.obligation_poll")

NOW = dt.datetime(2026, 6, 19, tzinfo=dt.timezone.utc)

_RED_ROW = {
    "matter_id": 999,
    "matter_ref": "TEST999",
    "client": "Confidential Clientname",
    "order_status": "FL404B received 01.05.2026",
    "awaiting_next_step": "send_to_client",
    "next_hearing_text": "",
    "service_status": "",
    "status_changed_at": "2026-05-01",
}


@pytest.fixture(autouse=True)
def _lock_path(monkeypatch, tmp_path):
    monkeypatch.setattr(poll, "LOCK_PATH", tmp_path / "obligation_poll.lock")


@pytest.fixture(autouse=True)
def _state_path(monkeypatch, tmp_path):
    monkeypatch.setattr(poll, "STATE_PATH", tmp_path / "obligation_alert_state.json")


@pytest.fixture
def _isolate(monkeypatch):
    monkeypatch.setattr(poll.clientdb_sql, "list_open_obligation_rows", lambda: [])
    sent: list[str] = []
    monkeypatch.setattr(
        poll.telegram_secretary_alert, "send_ops_alert", lambda text, **kw: sent.append(text) or {"sent": True}
    )
    return sent


def test_first_poll_with_nothing_overdue_sends_nothing(monkeypatch, _isolate):
    result = poll.run_poll(now=NOW)
    assert result["overdue"] == 0
    assert result["alerted"] is False
    assert _isolate == []


def test_overdue_sends_a_pii_safe_message(monkeypatch, _isolate):
    monkeypatch.setattr(poll.clientdb_sql, "list_open_obligation_rows", lambda: [dict(_RED_ROW)])

    result = poll.run_poll(now=NOW)

    assert result["overdue"] == 1
    assert result["alerted"] is True
    assert len(_isolate) == 1
    assert "Confidential Clientname" not in _isolate[0]
    assert "TEST999" in _isolate[0]


def test_an_unchanged_overdue_set_is_not_resent(monkeypatch, _isolate):
    monkeypatch.setattr(poll.clientdb_sql, "list_open_obligation_rows", lambda: [dict(_RED_ROW)])

    poll.run_poll(now=NOW)
    second = poll.run_poll(now=NOW)

    assert second["alerted"] is False
    assert len(_isolate) == 1


def test_clearing_sends_one_cleared_message(monkeypatch, _isolate):
    rows = [dict(_RED_ROW)]
    monkeypatch.setattr(poll.clientdb_sql, "list_open_obligation_rows", lambda: rows)
    poll.run_poll(now=NOW)
    rows.clear()

    cleared = poll.run_poll(now=NOW)
    again = poll.run_poll(now=NOW)

    assert cleared["alerted"] is True
    assert _isolate[-1] == "Overdue obligations cleared."
    assert again["alerted"] is False
    assert len(_isolate) == 2


def test_a_failed_send_is_retried_next_poll(monkeypatch):
    monkeypatch.setattr(poll.clientdb_sql, "list_open_obligation_rows", lambda: [dict(_RED_ROW)])
    outcomes = iter([{"sent": False, "reason": "http_error:500"}, {"sent": True}])
    monkeypatch.setattr(poll.telegram_secretary_alert, "send_ops_alert", lambda text, **kw: next(outcomes))

    first = poll.run_poll(now=NOW)
    second = poll.run_poll(now=NOW)

    assert first["alerted"] is False
    assert second["alerted"] is True


def test_dry_run_never_sends(monkeypatch, _isolate):
    monkeypatch.setattr(poll.clientdb_sql, "list_open_obligation_rows", lambda: [dict(_RED_ROW)])

    result = poll.run_poll(now=NOW, dry_run=True)

    assert result["dry_run"] is True
    assert _isolate == []




def test_acquire_lock_returns_handle_when_free(tmp_path, monkeypatch):
    monkeypatch.setattr(poll, "LOCK_PATH", tmp_path / "obligation_poll.lock")
    handle = poll._acquire_lock()
    assert handle is not None
    handle.close()


def test_acquire_lock_returns_none_when_already_held(tmp_path, monkeypatch):
    monkeypatch.setattr(poll, "LOCK_PATH", tmp_path / "obligation_poll.lock")
    first = poll._acquire_lock()
    assert first is not None
    try:
        second = poll._acquire_lock()
        assert second is None
    finally:
        first.close()


def test_acquire_lock_available_again_after_release(tmp_path, monkeypatch):
    monkeypatch.setattr(poll, "LOCK_PATH", tmp_path / "obligation_poll.lock")
    first = poll._acquire_lock()
    assert first is not None
    first.close()
    second = poll._acquire_lock()
    assert second is not None
    second.close()


def test_main_skips_when_lock_already_held(tmp_path, monkeypatch, _isolate, capsys):
    monkeypatch.setattr(poll, "LOCK_PATH", tmp_path / "obligation_poll.lock")
    holder = poll._acquire_lock()
    assert holder is not None
    try:
        rc = poll.main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "already_running" in out
    finally:
        holder.close()


def test_main_runs_and_releases_lock_for_next_call(tmp_path, monkeypatch, _isolate):
    monkeypatch.setattr(poll, "LOCK_PATH", tmp_path / "obligation_poll.lock")
    rc1 = poll.main(["--dry-run"])
    rc2 = poll.main(["--dry-run"])
    assert rc1 == 0 and rc2 == 0


def test_the_module_does_not_relock_a_file_the_harness_already_holds(monkeypatch, tmp_path):
    lock = tmp_path / "obligation_poll.lock"
    monkeypatch.setattr(poll, "LOCK_PATH", lock)
    monkeypatch.setenv("CASEFORGE_JOB_LOCK_FILE", str(lock))

    handle = poll._acquire_lock()

    assert handle is not None, "must not report already-running when it is our own harness"
    assert handle is poll._HARNESS_LOCK_SENTINEL


def test_closing_the_sentinel_does_not_drop_the_harness_lock():
    assert poll._HARNESS_LOCK_SENTINEL.close() is None


def test_a_different_jobs_lock_does_not_suppress_our_own(monkeypatch, tmp_path):
    monkeypatch.setattr(poll, "LOCK_PATH", tmp_path / "obligation_poll.lock")
    monkeypatch.setenv("CASEFORGE_JOB_LOCK_FILE", str(tmp_path / "some-other-job.lock"))

    handle = poll._acquire_lock()

    assert handle is not poll._HARNESS_LOCK_SENTINEL
    assert handle is not None
    handle.close()


def test_a_genuine_concurrent_run_is_still_blocked(monkeypatch, tmp_path):
    lock = tmp_path / "obligation_poll.lock"
    monkeypatch.setattr(poll, "LOCK_PATH", lock)
    monkeypatch.delenv("CASEFORGE_JOB_LOCK_FILE", raising=False)

    first = poll._acquire_lock()
    assert first is not None

    import subprocess, sys as _sys, textwrap
    probe = subprocess.run(
        [_sys.executable, "-c", textwrap.dedent(f"""
            import fcntl
            h = open({str(lock)!r}, "w")
            try:
                fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
                print("ACQUIRED")
            except OSError:
                print("BLOCKED")
        """)],
        capture_output=True, text=True,
    )
    assert probe.stdout.strip() == "BLOCKED", "a real second run must still be excluded"
    first.close()


def test_the_harness_exports_the_lock_path():
    harness = (Path(__file__).resolve().parent.parent / "tools" / "lib" / "job-harness.sh").read_text(encoding="utf-8")
    assert "export CASEFORGE_JOB_LOCK_FILE" in harness


def test_ops_alerts_use_the_counsel_bot_and_fall_back_to_the_secretary_bot(monkeypatch):
    tg = poll.telegram_secretary_alert
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_BOT_TOKEN", "secretary-token")
    monkeypatch.delenv("CASEFORGE_COUNSEL_TELEGRAM_BOT_TOKEN", raising=False)
    assert tg.ops_bot_token() == "secretary-token"
    monkeypatch.setenv("CASEFORGE_COUNSEL_TELEGRAM_BOT_TOKEN", "counsel-token")
    assert tg.ops_bot_token() == "counsel-token"
    assert tg.bot_token() == "secretary-token"
