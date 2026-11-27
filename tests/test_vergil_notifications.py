from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from vergil import notifications as notif

NOW = dt.datetime(2026, 8, 6, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(autouse=True)
def _isolated_seen_file(tmp_path, monkeypatch):
    monkeypatch.setattr(notif, "SEEN_PATH", tmp_path / "notifications-seen.json")


def _job(status: str, *, job_id: str = "abc123", updated: str = "2026-08-06T11:00:00Z") -> dict:
    return {
        "job_id": job_id,
        "job_type": "client-care-letter",
        "status": status,
        "updated_utc": updated,
        "payload": {"client_name": "Jane Doe"},
        "state": {"word_url": "https://example.invalid/letter.docx"},
    }




def test_parse_stamp_accepts_trailing_z_and_returns_aware():
    parsed = notif.parse_stamp("2026-08-06T11:00:00Z")
    assert parsed == dt.datetime(2026, 8, 6, 11, 0, tzinfo=dt.timezone.utc)


def test_parse_stamp_assumes_utc_for_a_naive_stamp():
    assert notif.parse_stamp("2026-08-06T11:00:00").tzinfo is dt.timezone.utc


@pytest.mark.parametrize("value", ["", None, "not a date", "  "])
def test_parse_stamp_returns_none_for_unusable_input(value):
    assert notif.parse_stamp(value) is None




def test_job_notifications_announce_finished_jobs():
    items = notif.job_notifications(
        [_job("done")],
        describe=lambda job: str(job["payload"]["client_name"]),
        link_for=lambda job: str(job["state"]["word_url"]),
    )
    assert len(items) == 1
    assert items[0]["severity"] == "success"
    assert "Jane Doe" in items[0]["text"]
    assert items[0]["link"].endswith("letter.docx")


@pytest.mark.parametrize("status", ["queued", "running"])
def test_job_notifications_ignore_a_job_still_in_flight(status):
    items = notif.job_notifications(
        [_job(status)], describe=lambda job: "", link_for=lambda job: ""
    )
    assert items == []


def test_job_notifications_mark_a_failure_as_an_error():
    items = notif.job_notifications(
        [_job("failed")], describe=lambda job: "", link_for=lambda job: ""
    )
    assert items[0]["severity"] == "error"


def test_job_notifications_skip_a_job_with_no_usable_timestamp():
    job = _job("done")
    job["updated_utc"] = ""
    job["created_utc"] = ""
    items = notif.job_notifications([job], describe=lambda j: "", link_for=lambda j: "")
    assert items == []


def test_job_notifications_tolerate_non_dict_entries():
    items = notif.job_notifications(
        ["nonsense", None, _job("done")], describe=lambda j: "", link_for=lambda j: ""
    )
    assert len(items) == 1




def test_supervisor_notifications_use_the_payload_generation_time():
    payload = {
        "generated_at": "2026-08-06T11:30:00Z",
        "alerts": [{"key": "a", "severity": "red", "title": "Queue stalled", "summary": "x"}],
    }
    items = notif.supervisor_notifications(payload)
    assert items[0]["timestamp"] == dt.datetime(2026, 8, 6, 11, 30, tzinfo=dt.timezone.utc)
    assert items[0]["severity"] == "red"


def test_supervisor_notifications_empty_when_there_are_no_alerts():
    assert notif.supervisor_notifications({"alerts": [], "generated_at": "2026-08-06T11:30:00Z"}) == []




def test_sort_notifications_puts_the_newest_first():
    older = {"id": "1", "timestamp": NOW - dt.timedelta(hours=2), "severity": "info"}
    newer = {"id": "2", "timestamp": NOW, "severity": "info"}
    assert [item["id"] for item in notif.sort_notifications([older, newer])] == ["2", "1"]


def test_sort_notifications_breaks_a_timestamp_tie_on_severity():
    info = {"id": "info", "timestamp": NOW, "severity": "info"}
    red = {"id": "red", "timestamp": NOW, "severity": "red"}
    assert notif.sort_notifications([info, red])[0]["id"] == "red"


def test_sort_notifications_respects_the_limit():
    items = [{"id": str(n), "timestamp": NOW - dt.timedelta(minutes=n), "severity": "info"} for n in range(10)]
    assert len(notif.sort_notifications(items, limit=3)) == 3




def test_last_seen_is_none_before_the_tray_has_ever_been_opened():
    assert notif.last_seen("sam") is None


def test_mark_seen_then_last_seen_round_trips():
    notif.mark_seen("sam", when=NOW)
    assert notif.last_seen("sam") == NOW


def test_seen_state_is_per_user():
    notif.mark_seen("sam", when=NOW)
    assert notif.last_seen("jordan") is None


def test_mark_seen_survives_a_new_process_because_it_is_on_disk():
    notif.mark_seen("sam", when=NOW)
    assert notif.SEEN_PATH.is_file()
    assert "sam" in notif.SEEN_PATH.read_text(encoding="utf-8")


def test_mark_seen_ignores_a_blank_username():
    notif.mark_seen("   ", when=NOW)
    assert not notif.SEEN_PATH.exists()


def test_mark_seen_does_not_raise_when_the_file_cannot_be_written(monkeypatch, tmp_path):
    monkeypatch.setattr(notif, "SEEN_PATH", tmp_path / "nope" / "seen.json")

    def _boom(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(Path, "mkdir", _boom)
    notif.mark_seen("sam", when=NOW)


def test_last_seen_tolerates_a_corrupt_file():
    notif.SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    notif.SEEN_PATH.write_text("{not json", encoding="utf-8")
    assert notif.last_seen("sam") is None




def test_unseen_returns_everything_for_a_user_who_never_opened_the_tray():
    items = [{"id": "1", "timestamp": NOW}]
    assert notif.unseen(items, None) == items


def test_unseen_excludes_items_at_or_before_the_marker():
    items = [
        {"id": "old", "timestamp": NOW - dt.timedelta(hours=1)},
        {"id": "same", "timestamp": NOW},
        {"id": "new", "timestamp": NOW + dt.timedelta(minutes=1)},
    ]
    assert [item["id"] for item in notif.unseen(items, NOW)] == ["new"]


def test_marking_seen_clears_the_badge():
    items = notif.sort_notifications(
        notif.job_notifications([_job("done")], describe=lambda j: "", link_for=lambda j: "")
    )
    assert notif.unseen(items, notif.last_seen("sam")) == items

    notif.mark_seen("sam", when=NOW)

    assert notif.unseen(items, notif.last_seen("sam")) == []
