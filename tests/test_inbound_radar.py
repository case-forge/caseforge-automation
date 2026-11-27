
import datetime as dt
import json

from tools.monitoring import inbound_radar as ir

NOW = dt.datetime(2026, 6, 19, 12, 0, tzinfo=dt.timezone.utc)


def _rec(**kw):
    base = {
        "message_id": "M1",
        "status": "inserted",
        "subject": "DV referral",
        "name": "Jane Doe",
        "person_id": 1,
        "matter_id": 100,
        "ts": "2026-06-19T09:00:00+00:00",
    }
    base.update(kw)
    return base


def test_classify_splits_alert_vs_quiet():
    recs = [
        _rec(status="inserted"),
        _rec(status="already-in-sql"),
        _rec(status="name-extract-failed"),
        _rec(status="returning-client-review"),
    ]
    split = ir.classify(recs)
    assert len(split["alert"]) == 3
    assert len(split["quiet"]) == 1


def test_recent_referrals_windows_by_time():
    recs = [
        _rec(message_id="old", ts="2026-06-10T09:00:00+00:00"),
        _rec(message_id="new", ts="2026-06-19T09:00:00+00:00"),
    ]
    recent = ir.recent_referrals(NOW, window_hours=24, referrals=recs)
    ids = {r["message_id"] for r in recent}
    assert ids == {"new"}


def test_pii_safe_line_has_no_name_or_subject():
    line = ir.pii_safe_referral_line(_rec(status="inserted", matter_id=100))
    assert "Jane Doe" not in line
    assert "DV referral" not in line
    assert "New referrer referral" in line
    assert "100" in line


def test_recent_referrals_dedupes_identical_message_id():
    recs = [
        _rec(message_id="dup", ts="2026-06-19T09:00:00.000001+00:00"),
        _rec(message_id="dup", ts="2026-06-19T09:00:00.000073+00:00"),
    ]
    recent = ir.recent_referrals(NOW, window_hours=24, referrals=recs)
    assert len(recent) == 1
    alert = ir.classify(recent)["alert"]
    assert len(alert) == 1


def test_referral_key_prefers_message_id():
    assert ir.referral_key(_rec(message_id="ABC")) == "referral:ABC"
    no_id = _rec()
    no_id.pop("message_id")
    assert ir.referral_key(no_id).startswith("referral:")


def test_read_referrals_skips_malformed(tmp_path):
    p = tmp_path / "intake.jsonl"
    p.write_text(
        json.dumps(_rec(message_id="ok")) + "\n"
        "not json\n"
        "\n"
        + json.dumps(_rec(message_id="ok2")) + "\n",
        encoding="utf-8",
    )
    recs = ir.read_referrals(p)
    assert [r["message_id"] for r in recs] == ["ok", "ok2"]


def test_radar_summary_is_pii_safe(tmp_path):
    p = tmp_path / "intake.jsonl"
    p.write_text(
        json.dumps(_rec(message_id="M1", status="inserted", ts="2026-06-19T09:00:00+00:00")) + "\n"
        + json.dumps(_rec(message_id="M2", status="already-in-sql", ts="2026-06-19T10:00:00+00:00")) + "\n",
        encoding="utf-8",
    )
    summary = ir.radar_summary(NOW, path=p)
    assert summary["alert_count"] == 1
    assert summary["quiet_count"] == 1
    blob = " ".join(summary["alert_lines"])
    assert "Jane Doe" not in blob and "DV referral" not in blob
