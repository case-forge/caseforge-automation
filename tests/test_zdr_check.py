import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tools"))

from model import zdr_check
import model_backend as mb


def test_models_to_check_covers_every_openrouter_role():
    checked = zdr_check.models_to_check()
    for role in mb.ROLES:
        assert f"role:{role}" in checked
        assert checked[f"role:{role}"] == mb.model_for_role(role, backend="openrouter")
    assert checked["role:vision"] == mb.vision_model()


def test_check_one_reports_pass_on_success(monkeypatch):
    monkeypatch.setattr(mb, "_run_openrouter", lambda model, prompt, timeout: "OK")
    ok, detail = zdr_check.check_one("some/model")
    assert ok is True
    assert detail == "OK"


def test_check_one_reports_fail_with_reason_on_zdr_404(monkeypatch):
    def _boom(model, prompt, timeout):
        raise mb.ModelBackendError(f"openrouter:{model} HTTP 404: no ZDR-compliant provider")

    monkeypatch.setattr(mb, "_run_openrouter", _boom)
    ok, detail = zdr_check.check_one("some/model")
    assert ok is False
    assert "404" in detail


def test_main_exits_nonzero_when_any_model_fails(monkeypatch, capsys):
    monkeypatch.setattr(zdr_check, "models_to_check", lambda: {"role:small": "a", "role:large": "b"})

    def _fake_check(model_id, timeout=20.0):
        return (model_id != "b"), "detail"

    monkeypatch.setattr(zdr_check, "check_one", _fake_check)
    assert zdr_check.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "OK" in out


def test_main_exits_zero_when_all_pass(monkeypatch):
    monkeypatch.setattr(zdr_check, "models_to_check", lambda: {"role:small": "a"})
    monkeypatch.setattr(zdr_check, "check_one", lambda model_id, timeout=20.0: (True, "OK"))
    assert zdr_check.main([]) == 0


def test_main_json_output_is_parseable(monkeypatch, capsys):
    import json

    monkeypatch.setattr(zdr_check, "models_to_check", lambda: {"role:small": "a"})
    monkeypatch.setattr(zdr_check, "check_one", lambda model_id, timeout=20.0: (True, "OK"))
    zdr_check.main(["--json"])
    parsed = json.loads(capsys.readouterr().out)
    assert parsed == [{"label": "role:small", "model": "a", "zdr_ok": True, "detail": "OK"}]
