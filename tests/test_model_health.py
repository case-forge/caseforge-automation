import datetime as dt
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from monitoring.model_health import build_health_snapshot, choose_fallback, classify_model_result


MODEL_OPTIONS = {
    "Auto": {"provider": "auto", "command": []},
    "Codex Mini": {"provider": "codex_mini", "command": ["python3", "--version"]},
    "Codex": {"provider": "codex", "command": ["python3", "--version"]},
    "Gemini": {"provider": "gemini", "command": ["definitely-missing-caseforge-cli"]},
}


def test_classifies_rate_limit_and_headers():
    row = classify_model_result(
        "Codex",
        MODEL_OPTIONS["Codex"],
        returncode=1,
        stderr="429 rate limit exceeded\nx-ratelimit-reset-requests: 1s",
    )

    assert row["status"] == "rate_limited"
    assert not row["available"]
    assert row["rate_limit"]["x-ratelimit-reset-requests"] == "1s"


def test_classifies_deprecated_model_not_found():
    row = classify_model_result(
        "Codex",
        MODEL_OPTIONS["Codex"],
        returncode=1,
        stderr="The model gpt-old does not exist or you do not have access to it",
    )

    assert row["status"] == "deprecated_not_found"
    assert not row["available"]


def test_snapshot_covers_all_configured_models_and_cli_missing():
    snapshot = build_health_snapshot(MODEL_OPTIONS)

    assert set(snapshot) == {"Codex Mini", "Codex", "Gemini"}
    assert snapshot["Gemini"]["status"] == "cli_missing"
    assert not snapshot["Gemini"]["available"]


def test_manual_outage_gets_fallback():
    future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    snapshot = build_health_snapshot(
        MODEL_OPTIONS,
        provider_state={"model_outages": {"Codex": {"unavailable_until": future, "reason": "Hit usage limit"}}},
    )

    assert snapshot["Codex"]["status"] == "rate_limited"
    assert snapshot["Codex"]["current_fallback"] == "Codex Mini"
    assert choose_fallback("Codex", snapshot, configured_order=list(MODEL_OPTIONS)) == "Codex Mini"


def test_provider_family_uses_latest_status_for_codex_variants():
    options = {
        "Auto": {"provider": "auto", "command": []},
        "Codex Mini": {"provider": "codex_mini", "command": ["python3", "--version"]},
        "Codex": {"provider": "codex", "command": ["python3", "--version"]},
        "Codex Demo": {"provider": "codex_demo", "command": ["python3", "--version"]},
    }
    snapshot = build_health_snapshot(
        options,
        provider_state={
            "providers": {
                "codex_mini": {
                    "last_terminal_state": "timed_out",
                    "last_error_category": "provider-busy",
                    "last_seen_utc": "2026-05-11T15:03:14Z",
                },
                "codex": {
                    "last_terminal_state": "completed",
                    "last_error_category": "",
                    "last_seen_utc": "2026-05-15T13:42:19Z",
                },
            }
        },
        now=dt.datetime(2026, 5, 15, 14, 0, tzinfo=dt.timezone.utc),
    )

    assert snapshot["Codex Mini"]["status"] == "available"
    assert snapshot["Codex"]["status"] == "available"
    assert snapshot["Codex Demo"]["status"] == "available"


def test_stale_timeout_history_does_not_make_model_currently_unavailable():
    snapshot = build_health_snapshot(
        {
            "Auto": {"provider": "auto", "command": []},
            "Claude": {"provider": "claude", "command": ["python3", "--version"]},
            "Claude Demo": {"provider": "claude_demo", "command": ["python3", "--version"]},
        },
        provider_state={
            "providers": {
                "claude_demo": {
                    "last_terminal_state": "timed_out",
                    "last_error_category": "provider-busy",
                    "last_seen_utc": "2026-05-07T14:18:52Z",
                },
            }
        },
        stored_health={
            "models": {
                "Claude Demo": {
                    "available": False,
                    "status": "timeout",
                    "reason": "Provider timed out.",
                    "last_failure_utc": "2026-05-07T14:18:52Z",
                }
            }
        },
        now=dt.datetime(2026, 5, 15, 14, 0, tzinfo=dt.timezone.utc),
    )

    assert snapshot["Claude"]["status"] == "available"
    assert snapshot["Claude Demo"]["status"] == "available"
