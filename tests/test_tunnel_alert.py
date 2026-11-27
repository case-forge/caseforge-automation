
import importlib

ta = importlib.import_module("tools.monitoring.tunnel_alert")


def test_services_no_longer_includes_code_tunnel():
    names = {s["name"] for s in ta.SERVICES}
    assert names == {"cloudflared"}


def test_restart_service_invokes_systemctl(monkeypatch):
    calls = []

    class FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append(args)
        return FakeProc()

    monkeypatch.setattr(ta.subprocess, "run", fake_run)
    ok, detail = ta.restart_service("cloudflared.service", "system")
    assert ok is True
    assert calls[0] == ["systemctl", "restart", "cloudflared.service"]

    ok, detail = ta.restart_service("code-tunnel.service", "user")
    assert calls[1] == ["systemctl", "--user", "restart", "code-tunnel.service"]


def test_read_write_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    ta.write_state(path, {"cloudflared_last_repair_epoch": 123.0})
    assert ta.read_state(path) == {"cloudflared_last_repair_epoch": 123.0}


def test_read_state_missing_file_returns_empty_dict(tmp_path):
    assert ta.read_state(tmp_path / "missing.json") == {}
