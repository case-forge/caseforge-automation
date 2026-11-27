import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from model import model_perf_report as mpr


def _ev(provider, final_state, elapsed, attempts):
    return {
        "provider": provider,
        "selected_model": f"{provider}-model",
        "final_state": final_state,
        "elapsed_seconds": elapsed,
        "payload": {"attempts": attempts},
    }


def _attempt(backend, ok):
    return {"backend": backend, "ok": ok}


def test_empty_events_is_safe():
    report = mpr.build_model_performance([])
    assert report["total_events"] == 0
    assert report["by_provider"] == []
    assert report["fallback"]["failover_rate_pct"] == 0.0


def test_served_share_and_counts():
    events = [
        _ev("llamacpp", "completed", 2.0, [_attempt("llamacpp", True)]),
        _ev("llamacpp", "completed", 3.0, [_attempt("llamacpp", True)]),
        _ev("codex", "completed", 5.0, [_attempt("codex", True)]),
    ]
    report = mpr.build_model_performance(events)
    assert report["total_events"] == 3
    by = {p["provider"]: p for p in report["by_provider"]}
    assert by["llamacpp"]["events"] == 2
    assert round(by["llamacpp"]["served_share_pct"], 1) == 66.7
    assert round(by["codex"]["served_share_pct"], 1) == 33.3


def test_latency_percentiles():
    events = [
        _ev("llamacpp", "completed", float(s), [_attempt("llamacpp", True)])
        for s in (1, 2, 3, 4, 100)
    ]
    by = {p["provider"]: p for p in mpr.build_model_performance(events)["by_provider"]}
    assert by["llamacpp"]["latency_p50"] == 3.0
    assert by["llamacpp"]["latency_p95"] == 100.0


def test_error_rate_counts_failed_rows():
    events = [
        _ev("llamacpp", "completed", 2.0, [_attempt("llamacpp", True)]),
        _ev("none", "failed", 45.0, [_attempt("llamacpp", False)]),
    ]
    report = mpr.build_model_performance(events)
    by = {p["provider"]: p for p in report["by_provider"]}
    assert by["none"]["failed"] == 1
    assert by["none"]["error_rate_pct"] == 100.0
    assert report["fallback"]["all_failed"] == 1


def test_failover_is_detected_as_cost_leak():
    events = [
        _ev("codex", "completed", 6.0, [_attempt("llamacpp", False), _attempt("codex", True)]),
        _ev("llamacpp", "completed", 2.0, [_attempt("llamacpp", True)]),
    ]
    report = mpr.build_model_performance(events)
    assert report["fallback"]["served_after_failover"] == 1
    assert report["fallback"]["failover_rate_pct"] == 50.0
    legs = {(f["from_backend"], f["to_backend"]): f["count"] for f in report["fallback"]["by_failover"]}
    assert legs[("llamacpp", "codex")] == 1


def test_failover_rate_excludes_clean_serves():
    events = [_ev("llamacpp", "completed", 2.0, [_attempt("llamacpp", True)]) for _ in range(4)]
    assert mpr.build_model_performance(events)["fallback"]["failover_rate_pct"] == 0.0


def test_render_is_string_and_mentions_providers():
    events = [_ev("llamacpp", "completed", 2.0, [_attempt("llamacpp", True)])]
    report = mpr.build_model_performance(events)
    text = mpr.render(report, window_label="last 7d")
    assert isinstance(text, str)
    assert "llamacpp" in text
    assert "last 7d" in text


def test_the_report_runs_as_a_script_from_the_repo_root():
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    done = subprocess.run([sys.executable, str(root / "tools" / "model" / "model_perf_report.py"), "--no-telemetry", "--days", "1"],
                          cwd=root, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-800:]
    assert "Model backend performance" in done.stdout
