
import importlib
import json

clg = importlib.import_module("tools.monitoring.crash_loop_guard")


def _patch_units(monkeypatch, units_by_scope, fields_by_key):
    def fake_list_service_units(scope, timeout):
        return list(units_by_scope.get(scope, []))

    def fake_show_unit(scope, unit, timeout):
        return dict(fields_by_key.get(f"{scope}:{unit}", {}))

    monkeypatch.setattr(clg, "list_service_units", fake_list_service_units)
    monkeypatch.setattr(clg, "show_unit", fake_show_unit)


def test_no_baseline_high_absolute_restarts_is_flagged(monkeypatch, tmp_path):
    _patch_units(
        monkeypatch,
        {"system": ["qdrant.service"], "user": []},
        {"system:qdrant.service": {"NRestarts": "52718", "ActiveState": "activating", "SubState": "auto-restart"}},
    )
    state_path = tmp_path / "state.json"
    payload = clg.evaluate(state_path=state_path, auto_stop=False)
    assert payload["overall"] == "red"
    assert len(payload["findings"]) == 1
    finding = payload["findings"][0]
    assert finding["unit"] == "qdrant.service"
    assert finding["reason"] == "absolute_first_seen"


def test_no_baseline_low_absolute_restarts_is_not_flagged(monkeypatch, tmp_path):
    _patch_units(
        monkeypatch,
        {"system": ["cron.service"], "user": []},
        {"system:cron.service": {"NRestarts": "2", "ActiveState": "active", "SubState": "running"}},
    )
    state_path = tmp_path / "state.json"
    payload = clg.evaluate(state_path=state_path, absolute_restart_floor=20, auto_stop=False)
    assert payload["overall"] == "green"
    assert payload["findings"] == []


def test_small_delta_since_last_run_is_not_flagged(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"system:foo.service": {"nrestarts": 100, "observed_utc": "2026-07-24T10:00:00Z"}}),
        encoding="utf-8",
    )
    _patch_units(
        monkeypatch,
        {"system": ["foo.service"], "user": []},
        {"system:foo.service": {"NRestarts": "101", "ActiveState": "active", "SubState": "running"}},
    )
    payload = clg.evaluate(state_path=state_path, restart_delta_threshold=3, auto_stop=False)
    assert payload["overall"] == "green"
    assert payload["findings"] == []


def test_large_delta_since_last_run_is_flagged_even_with_low_absolute_count(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps({"system:foo.service": {"nrestarts": 2, "observed_utc": "2026-07-24T10:00:00Z"}}),
        encoding="utf-8",
    )
    _patch_units(
        monkeypatch,
        {"system": ["foo.service"], "user": []},
        {"system:foo.service": {"NRestarts": "8", "ActiveState": "activating", "SubState": "auto-restart"}},
    )
    payload = clg.evaluate(state_path=state_path, restart_delta_threshold=3, absolute_restart_floor=20, auto_stop=False)
    assert payload["overall"] == "red"
    assert payload["findings"][0]["reason"] == "restart_delta"
    assert payload["findings"][0]["restart_delta"] == 6


def test_state_is_persisted_for_next_run(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    _patch_units(
        monkeypatch,
        {"system": ["foo.service"], "user": []},
        {"system:foo.service": {"NRestarts": "5", "ActiveState": "active", "SubState": "running"}},
    )
    clg.evaluate(state_path=state_path, absolute_restart_floor=20, auto_stop=False)
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["system:foo.service"]["nrestarts"] == 5


def test_auto_stop_only_fires_past_the_auto_stop_floor(monkeypatch, tmp_path):
    stopped = []

    def fake_stop_unit(scope, unit, timeout):
        stopped.append((scope, unit))
        return True, "stopped"

    monkeypatch.setattr(clg, "stop_unit", fake_stop_unit)
    _patch_units(
        monkeypatch,
        {"system": ["low.service", "runaway.service"], "user": []},
        {
            "system:low.service": {"NRestarts": "25", "ActiveState": "activating", "SubState": "auto-restart"},
            "system:runaway.service": {"NRestarts": "500", "ActiveState": "activating", "SubState": "auto-restart"},
        },
    )
    state_path = tmp_path / "state.json"
    payload = clg.evaluate(
        state_path=state_path,
        absolute_restart_floor=20,
        auto_stop=True,
        auto_stop_floor=200,
    )
    assert stopped == [("system", "runaway.service")]
    by_unit = {f["unit"]: f for f in payload["findings"]}
    assert by_unit["low.service"]["auto_stop"]["attempted"] is False
    assert by_unit["runaway.service"]["auto_stop"] == {"attempted": True, "ok": True, "detail": "stopped"}


def test_timer_triggered_oneshot_failing_every_run_is_flagged(monkeypatch, tmp_path):
    _patch_units(
        monkeypatch,
        {"system": ["idemili-mail-intake-reconcile.service"], "user": []},
        {
            "system:idemili-mail-intake-reconcile.service": {
                "NRestarts": "0",
                "ActiveState": "failed",
                "SubState": "failed",
                "Result": "exit-code",
            }
        },
    )
    state_path = tmp_path / "state.json"
    payload = clg.evaluate(state_path=state_path, auto_stop=False)
    assert payload["overall"] == "red"
    assert len(payload["findings"]) == 1
    finding = payload["findings"][0]
    assert finding["unit"] == "idemili-mail-intake-reconcile.service"
    assert finding["reason"] == "failed_state"
    assert finding["nrestarts"] == 0


def test_no_findings_when_nothing_is_flapping(monkeypatch, tmp_path):
    _patch_units(
        monkeypatch,
        {"system": ["healthy.service"], "user": ["also-healthy.service"]},
        {
            "system:healthy.service": {"NRestarts": "0", "ActiveState": "active", "SubState": "running"},
            "user:also-healthy.service": {"NRestarts": "0", "ActiveState": "active", "SubState": "running"},
        },
    )
    state_path = tmp_path / "state.json"
    payload = clg.evaluate(state_path=state_path, auto_stop=False)
    assert payload["overall"] == "green"
    assert payload["units_scanned"] == 2


def test_zero_units_scanned_is_unavailable_not_green(monkeypatch, tmp_path):
    _patch_units(monkeypatch, {"system": [], "user": []}, {})
    state_path = tmp_path / "state.json"
    payload = clg.evaluate(state_path=state_path, auto_stop=False)
    assert payload["overall"] == "unavailable"
    assert payload["units_scanned"] == 0


def test_unavailable_run_does_not_overwrite_prior_report(monkeypatch, tmp_path):
    _patch_units(monkeypatch, {"system": [], "user": []}, {})
    state_path = tmp_path / "state.json"
    out_path = tmp_path / "crash-loop-guard.json"
    prior = {"overall": "red", "findings": [{"unit": "real-finding.service"}]}
    out_path.write_text(json.dumps(prior), encoding="utf-8")

    monkeypatch.setattr(
        clg,
        "parse_args",
        lambda: __import__("argparse").Namespace(
            out=str(out_path),
            state=str(state_path),
            no_write=False,
            json=True,
            timeout=5.0,
            restart_delta_threshold=clg.DEFAULT_RESTART_DELTA_THRESHOLD,
            absolute_restart_floor=clg.DEFAULT_ABSOLUTE_RESTART_FLOOR,
            auto_stop_floor=clg.DEFAULT_AUTO_STOP_FLOOR,
            auto_stop=False,
            fail_on_red=False,
        ),
    )
    clg.main()
    assert json.loads(out_path.read_text(encoding="utf-8")) == prior
