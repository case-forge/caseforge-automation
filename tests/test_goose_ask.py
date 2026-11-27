from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from vergil.goose import goose_ask as ga


def test_translate_goose_action_to_tool_call():
    raw = {"kind": "action", "tool_name": "caseforge_ops__search_clients", "action": {"query": "Anna"}, "call_id": "call_1"}
    assert ga.translate_goose_event(raw) == (
        "tool_call",
        {"tool": "caseforge_ops__search_clients", "input": {"query": "Anna"}, "input_digest": ga._digest({"query": "Anna"}), "call_id": "call_1"},
    )


def test_translate_goose_action_defaults_call_id_to_empty_string_when_absent():
    raw = {"kind": "action", "tool_name": "caseforge_ops__search_clients", "action": {"query": "Anna"}}
    assert ga.translate_goose_event(raw) == (
        "tool_call",
        {"tool": "caseforge_ops__search_clients", "input": {"query": "Anna"}, "input_digest": ga._digest({"query": "Anna"}), "call_id": ""},
    )


def test_translate_goose_observation_to_tool_result():
    raw = {
        "kind": "observation",
        "tool_name": "caseforge_ops__search_clients",
        "observation": {"content": [{"type": "text", "text": "a.txt"}], "is_error": False},
        "call_id": "call_1",
    }
    assert ga.translate_goose_event(raw) == (
        "tool_result",
        {"tool": "caseforge_ops__search_clients", "content": [], "call_id": "call_1"},
    )


def test_translate_goose_errored_observation_to_tool_error():
    raw = {
        "kind": "observation",
        "tool_name": "caseforge_ops__search_clients",
        "observation": {"content": [], "is_error": True},
        "call_id": "call_1",
    }
    assert ga.translate_goose_event(raw) == ("tool_error", {"tool": "caseforge_ops__search_clients", "call_id": "call_1"})


def test_translate_goose_message_to_delta():
    raw = {"kind": "message", "text": "hello"}
    assert ga.translate_goose_event(raw) == ("delta", {"text": "hello"})


def test_translate_goose_message_strips_em_dashes():
    raw = {"kind": "message", "text": "one thing—another thing"}
    assert ga.translate_goose_event(raw) == ("delta", {"text": "one thing, another thing"})


def test_translate_goose_run_done_to_done():
    assert ga.translate_goose_event({"kind": "run.done"}) == ("done", {})


def test_translate_goose_run_error_to_a_fixed_message():
    assert ga.translate_goose_event({"kind": "run.error"}) == ("error", {"message": "Vergil backend unavailable"})


def test_translate_goose_unrecognised_kind_returns_none():
    assert ga.translate_goose_event({"kind": "something_else"}) is None


def test_stream_vergil_answer_goose_translates_and_filters():
    raw_events = [
        {"kind": "action", "tool_name": "caseforge_ops__search_clients", "action": {"query": "Anna"}, "call_id": "call_1"},
        {
            "kind": "observation",
            "tool_name": "caseforge_ops__search_clients",
            "observation": {"content": [], "is_error": False},
            "call_id": "call_1",
        },
        {"kind": "message", "text": "hello"},
        {"kind": "run.done"},
    ]
    with patch.object(ga.goose_client, "stream_session_events", return_value=iter(raw_events)):
        results = list(ga.stream_vergil_answer_goose("goose_abc"))
    assert results == [
        ("tool_call", {"tool": "caseforge_ops__search_clients", "input": {"query": "Anna"}, "input_digest": ga._digest({"query": "Anna"}), "call_id": "call_1"}),
        ("tool_result", {"tool": "caseforge_ops__search_clients", "content": [], "call_id": "call_1"}),
        ("delta", {"text": "hello"}),
        ("done", {}),
    ]


def test_stream_vergil_answer_goose_stops_after_terminal_error():
    raw_events = [
        {"kind": "run.error"},
        {"kind": "message", "text": "should never be reached"},
    ]
    with patch.object(ga.goose_client, "stream_session_events", return_value=iter(raw_events)):
        results = list(ga.stream_vergil_answer_goose("goose_abc"))
    assert results == [("error", {"message": "Vergil backend unavailable"})]
