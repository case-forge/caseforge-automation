from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Optional

from vergil.goose import conversation_log
from vergil.goose.goose_routing import ConversationSafetyState

_MAX_ENTRIES = 500

_lock = threading.Lock()
_states: "OrderedDict[str, ConversationSafetyState]" = OrderedDict()


def get_or_create(session_id: Optional[str]) -> ConversationSafetyState:
    if not session_id:
        return ConversationSafetyState()
    with _lock:
        state = _states.get(session_id)
        if state is not None:
            _states.move_to_end(session_id)
            return state
    return ConversationSafetyState()


def save(session_id: Optional[str], state: ConversationSafetyState) -> None:
    if not session_id:
        return
    with _lock:
        _states[session_id] = state
        _states.move_to_end(session_id)
        while len(_states) > _MAX_ENTRIES:
            _states.popitem(last=False)


_bindings: "OrderedDict[str, tuple[str, str]]" = OrderedDict()


def session_belongs_to(session_id: Optional[str], anchor: Optional[str], user: Optional[str]) -> bool:
    if not session_id:
        return False
    binding = (str(anchor or "").strip(), str(user or "").strip())
    with _lock:
        known = _bindings.get(session_id)
        if known is not None:
            _bindings.move_to_end(session_id)
            return known == binding
    saved = conversation_log.binding(session_id)
    if saved is None:
        bind_session(session_id, anchor, user)
        return True
    with _lock:
        _bind_locked(session_id, saved)
    return saved == binding


_typed_text: "OrderedDict[str, tuple[set[str], set[str]]]" = OrderedDict()


def note_user_text(session_id: str, addresses: set[str], references: set[str]) -> tuple[set[str], set[str]]:
    with _lock:
        have_addresses, have_references = _typed_text.get(session_id, (set(), set()))
        totals = (have_addresses | addresses, have_references | references)
        _typed_text[session_id] = totals
        _typed_text.move_to_end(session_id)
        while len(_typed_text) > _MAX_ENTRIES:
            _typed_text.popitem(last=False)
    return totals


def bind_session(session_id: str, anchor: Optional[str], user: Optional[str]) -> None:
    with _lock:
        _bind_locked(session_id, (str(anchor or "").strip(), str(user or "").strip()))
    conversation_log.bind(session_id, anchor, user)


def _bind_locked(session_id: str, binding: tuple[str, str]) -> None:
    _bindings[session_id] = binding
    _bindings.move_to_end(session_id)
    while len(_bindings) > _MAX_ENTRIES * 4:
        _bindings.popitem(last=False)
