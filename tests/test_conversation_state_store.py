from __future__ import annotations

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil.goose import conversation_state_store as store
from vergil.goose.goose_routing import ConversationSafetyState


def teardown_function(_fn):
    store._states.clear()


def test_get_or_create_with_no_session_id_returns_a_fresh_state():
    state = store.get_or_create(None)
    assert isinstance(state, ConversationSafetyState)
    assert state.poisoned is False

    state2 = store.get_or_create("")
    assert state2 is not state


def test_get_or_create_with_an_unseen_session_id_returns_a_fresh_state():
    state = store.get_or_create("goose_neverseen")
    assert isinstance(state, ConversationSafetyState)


def test_save_then_get_or_create_returns_the_same_object():
    state = ConversationSafetyState()
    state.poisoned = True
    store.save("goose_abc", state)
    fetched = store.get_or_create("goose_abc")
    assert fetched is state
    assert fetched.poisoned is True


def test_save_with_no_session_id_is_a_no_op():
    before = len(store._states)
    store.save(None, ConversationSafetyState())
    store.save("", ConversationSafetyState())
    assert len(store._states) == before


def test_different_session_ids_stay_independent():
    state_a = ConversationSafetyState()
    state_a.poisoned = True
    state_b = ConversationSafetyState()

    store.save("goose_a", state_a)
    store.save("goose_b", state_b)

    assert store.get_or_create("goose_a").poisoned is True
    assert store.get_or_create("goose_b").poisoned is False


def test_store_is_bounded_and_evicts_oldest_first(monkeypatch):
    monkeypatch.setattr(store, "_MAX_ENTRIES", 3)
    for i in range(5):
        store.save(f"goose_{i}", ConversationSafetyState())

    assert len(store._states) == 3
    assert "goose_0" not in store._states
    assert "goose_1" not in store._states
    assert "goose_4" in store._states


def test_re_saving_an_existing_session_id_refreshes_its_recency(monkeypatch):
    monkeypatch.setattr(store, "_MAX_ENTRIES", 2)
    state_a = ConversationSafetyState()
    store.save("goose_a", state_a)
    store.save("goose_b", ConversationSafetyState())
    store.save("goose_a", state_a)
    store.save("goose_c", ConversationSafetyState())

    assert "goose_a" in store._states
    assert "goose_b" not in store._states
    assert "goose_c" in store._states
