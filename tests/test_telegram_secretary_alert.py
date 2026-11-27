from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

TOOLS_DIR = str(Path(__file__).resolve().parents[1] / "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import monitoring.telegram_secretary_alert as tsa


def test_alert_configured_false_when_env_unset(monkeypatch):
    monkeypatch.delenv("CASEFORGE_MONITOR_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CASEFORGE_MONITOR_TELEGRAM_CHAT_ID", raising=False)
    assert tsa.alert_configured() is False


def test_alert_configured_true_when_both_set(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_BOT_TOKEN", "test-token-not-real")
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_CHAT_ID", "12345")
    assert tsa.alert_configured() is True


def test_send_secretary_alert_not_configured_is_a_real_result_not_an_error(monkeypatch):
    monkeypatch.delenv("CASEFORGE_MONITOR_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CASEFORGE_MONITOR_TELEGRAM_CHAT_ID", raising=False)
    result = tsa.send_secretary_alert("A client is complaining about their CCL")
    assert result == {"sent": False, "reason": "not_configured"}


def test_send_secretary_alert_never_raises_on_network_failure(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_BOT_TOKEN", "test-token-not-real")
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_CHAT_ID", "12345")
    with patch.object(tsa.urllib.request, "urlopen", side_effect=RuntimeError("connection refused")):
        result = tsa.send_secretary_alert("hello")
    assert result["sent"] is False
    assert result["reason"] == "request_failed"


def test_send_secretary_alert_never_leaks_the_raw_token_in_a_failure_detail(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_BOT_TOKEN", "SUPER-SECRET-TOKEN-VALUE")
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_CHAT_ID", "12345")
    with patch.object(
        tsa.urllib.request, "urlopen", side_effect=RuntimeError("failed against bot SUPER-SECRET-TOKEN-VALUE")
    ):
        result = tsa.send_secretary_alert("hello")
    assert "SUPER-SECRET-TOKEN-VALUE" not in result.get("detail", "")


def test_send_secretary_alert_blocks_text_that_fails_the_safety_check(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_BOT_TOKEN", "test-token-not-real")
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_CHAT_ID", "12345")
    with patch.object(tsa.telegram_text_safety, "looks_unsafe", return_value=True):
        result = tsa.send_secretary_alert("anything")
    assert result == {"sent": False, "reason": "text_failed_safety_check"}


def test_cli_exits_nonzero_when_not_configured(monkeypatch, capsys):
    monkeypatch.delenv("CASEFORGE_MONITOR_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CASEFORGE_MONITOR_TELEGRAM_CHAT_ID", raising=False)
    assert tsa.main(["--critical", "rotate the Graph secrets"]) == 1
    assert "not_configured" in capsys.readouterr().err


def test_cli_exits_zero_and_sends_when_configured(monkeypatch):
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_BOT_TOKEN", "test-token-not-real")
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_CHAT_ID", "12345")
    with patch.object(tsa, "send_secretary_alert", return_value={"sent": True}) as send:
        assert tsa.main(["--critical", "rotate the Graph secrets"]) == 0
    assert send.call_args.args[0] == "CRITICAL: rotate the Graph secrets"


def _ops_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(tsa, "ops_bot_token", lambda: "ops-token")
    monkeypatch.setenv("CASEFORGE_MONITOR_TELEGRAM_CHAT_ID", "42")


def test_ops_alert_waits_out_the_two_minute_gap_instead_of_dropping(monkeypatch, tmp_path):
    _ops_env(monkeypatch, tmp_path)
    (tmp_path / "caseforge-alert").mkdir()
    (tmp_path / "caseforge-alert" / "ops_last_sent").write_text(str(tsa.time.time() - 30))
    slept = []
    monkeypatch.setattr(tsa.time, "sleep", slept.append)
    with patch.object(tsa, "send_secretary_alert", return_value={"sent": True}) as send:
        assert tsa.send_ops_alert("x") == {"sent": True}
    assert send.call_count == 1
    assert 85 < slept[0] <= 90


def test_ops_alert_sends_at_once_when_the_gap_has_passed(monkeypatch, tmp_path):
    _ops_env(monkeypatch, tmp_path)
    (tmp_path / "caseforge-alert").mkdir()
    (tmp_path / "caseforge-alert" / "ops_last_sent").write_text(str(tsa.time.time() - 500))
    slept = []
    monkeypatch.setattr(tsa.time, "sleep", slept.append)
    with patch.object(tsa, "send_secretary_alert", return_value={"sent": True}):
        tsa.send_ops_alert("x")
    assert slept == []
    assert float((tmp_path / "caseforge-alert" / "ops_last_sent").read_text()) > tsa.time.time() - 5


def test_ops_alert_failed_send_does_not_start_a_new_gap(monkeypatch, tmp_path):
    _ops_env(monkeypatch, tmp_path)
    monkeypatch.setattr(tsa.time, "sleep", lambda s: None)
    with patch.object(tsa, "send_secretary_alert", return_value={"sent": False, "reason": "request_failed"}):
        tsa.send_ops_alert("x")
    assert not (tmp_path / "caseforge-alert" / "ops_last_sent").exists()
