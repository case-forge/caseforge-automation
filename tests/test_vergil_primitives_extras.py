from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil import primitives


def test_attempt_success_true_when_ok_and_text_emitted():
    assert primitives.attempt_success({"ok": True, "text_emitted": True}) is True


def test_attempt_success_false_when_ok_but_no_text_emitted():
    assert primitives.attempt_success({"ok": True, "text_emitted": False}) is False


def test_attempt_success_false_when_not_ok():
    assert primitives.attempt_success({"ok": False, "text_emitted": True}) is False


def test_attempt_success_false_for_missing_keys():
    assert primitives.attempt_success({}) is False


def test_submission_fingerprint_is_deterministic():
    a = primitives.submission_fingerprint("draft a CCL", [{"name": "file.pdf", "size": 100}])
    b = primitives.submission_fingerprint("draft a CCL", [{"name": "file.pdf", "size": 100}])
    assert a == b
    assert len(a) == 64


def test_submission_fingerprint_changes_with_prompt():
    a = primitives.submission_fingerprint("draft a CCL")
    b = primitives.submission_fingerprint("draft a closing letter")
    assert a != b


def test_submission_fingerprint_changes_with_attachments():
    a = primitives.submission_fingerprint("prompt", [{"name": "a.pdf", "size": 1}])
    b = primitives.submission_fingerprint("prompt", [{"name": "b.pdf", "size": 1}])
    assert a != b


def test_submission_fingerprint_ignores_attachment_order():
    a = primitives.submission_fingerprint(
        "prompt", [{"name": "a.pdf", "size": 1}, {"name": "b.pdf", "size": 2}]
    )
    b = primitives.submission_fingerprint(
        "prompt", [{"name": "a.pdf", "size": 1}, {"name": "b.pdf", "size": 2}]
    )
    assert a == b


def test_submission_fingerprint_no_attachments_defaults_to_empty_list():
    assert primitives.submission_fingerprint("prompt") == primitives.submission_fingerprint("prompt", None)
    assert primitives.submission_fingerprint("prompt") == primitives.submission_fingerprint("prompt", [])


def test_submission_fingerprint_strips_whitespace_from_prompt():
    assert primitives.submission_fingerprint("  hello  ") == primitives.submission_fingerprint("hello")


def test_submission_fingerprint_ignores_non_dict_attachment_entries():
    assert primitives.submission_fingerprint("prompt", ["not-a-dict"]) == primitives.submission_fingerprint("prompt", [])


def test_latest_user_index_returns_last_user_message_index():
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply 2"},
    ]
    assert primitives.latest_user_index(messages) == 2


def test_latest_user_index_returns_none_for_no_user_messages():
    messages = [{"role": "assistant", "content": "hello"}]
    assert primitives.latest_user_index(messages) is None


def test_latest_user_index_returns_none_for_empty_list():
    assert primitives.latest_user_index([]) is None


def test_latest_user_index_last_message_is_the_user_message():
    messages = [{"role": "assistant", "content": "hi"}, {"role": "user", "content": "bye"}]
    assert primitives.latest_user_index(messages) == 1


def test_ttl_cache_serves_a_second_call_without_recomputing():
    calls = []

    @primitives.ttl_cache(300)
    def load():
        calls.append(1)
        return {"n": len(calls)}

    assert load() == {"n": 1}
    assert load() == {"n": 1}
    assert len(calls) == 1


def test_ttl_cache_recomputes_once_the_window_has_passed(monkeypatch):
    calls = []
    now = [1000.0]
    monkeypatch.setattr(primitives.time, "monotonic", lambda: now[0])

    @primitives.ttl_cache(300)
    def load():
        calls.append(1)
        return len(calls)

    assert load() == 1
    now[0] += 299
    assert load() == 1, "still inside the window"
    now[0] += 2
    assert load() == 2, "past the window, must recompute"


def test_ttl_cache_returns_a_copy_so_a_mutating_caller_cannot_poison_it():

    @primitives.ttl_cache(300)
    def load():
        return {"boards": [{"code": "2", "wording": "original"}]}

    first = load()
    first["boards"][0]["wording"] = "CLOBBERED"
    first["boards"].append({"code": "9"})

    second = load()
    assert second == {"boards": [{"code": "2", "wording": "original"}]}


def test_ttl_cache_keys_on_arguments():
    @primitives.ttl_cache(300)
    def load(limit=10):
        return limit * 2

    assert load(3) == 6
    assert load(5) == 10
    assert load(limit=3) == 6


def test_ttl_cache_clear_forces_a_recompute():
    calls = []

    @primitives.ttl_cache(300)
    def load():
        calls.append(1)
        return len(calls)

    assert load() == 1
    load.cache_clear()
    assert load() == 2


def test_ttl_cache_uses_a_monotonic_clock_not_the_wall_clock(monkeypatch):
    import datetime as _dt

    calls = []
    now = [500.0]
    monkeypatch.setattr(primitives.time, "monotonic", lambda: now[0])

    class _FrozenClock(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("ttl_cache must not consult the wall clock")

    monkeypatch.setattr(primitives.dt, "datetime", _FrozenClock)

    @primitives.ttl_cache(60)
    def load():
        calls.append(1)
        return len(calls)

    assert load() == 1
    now[0] += 61
    assert load() == 2
