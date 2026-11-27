#!/usr/bin/env python3

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable

TTL_SECONDS = 300.0
WORKERS = 8

log = logging.getLogger(__name__)
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}


def clear() -> None:
    with _LOCK:
        _CACHE.clear()


def invalidate(matter_ids: Iterable[str]) -> None:
    with _LOCK:
        for matter_id in matter_ids:
            _CACHE.pop(str(matter_id), None)


def rows_for(
    matter_ids: Iterable[str],
    *,
    resolve: Callable[[str], dict[str, Any] | None] | None = None,
    batch: Callable[[list[str]], dict[str, dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    if resolve is None:
        import clientdb_sql

        resolve = clientdb_sql.get_client_by_matter_id
        if batch is None:
            batch = clientdb_sql.get_clients_by_matter_ids
    else:
        batch = None
    ids = [str(m) for m in dict.fromkeys(str(i) for i in matter_ids)]
    now = time.monotonic()
    found: dict[str, dict[str, Any] | None] = {}
    todo: list[str] = []
    with _LOCK:
        for matter_id in ids:
            hit = _CACHE.get(matter_id)
            if hit and now - hit[0] < TTL_SECONDS:
                found[matter_id] = hit[1]
            else:
                todo.append(matter_id)
    if todo and batch is not None:
        numeric = [m for m in todo if m.isdigit()]
        try:
            fetched = batch(numeric) if numeric else {}
        except Exception as exc:
            log.warning("client row batch lookup failed: %s", type(exc).__name__)
        else:
            stamp = time.monotonic()
            with _LOCK:
                for matter_id in numeric:
                    row = fetched.get(matter_id)
                    _CACHE[matter_id] = (stamp, row)
                    found[matter_id] = row
            todo = [m for m in todo if m not in numeric]
    if todo:
        def safe(matter_id: str) -> dict[str, Any] | None:
            try:
                return resolve(matter_id)
            except Exception as exc:
                log.warning("client row lookup failed: %s", type(exc).__name__)
                return None

        with ThreadPoolExecutor(max_workers=min(WORKERS, len(todo))) as pool:
            resolved = list(pool.map(safe, todo))
        stamp = time.monotonic()
        with _LOCK:
            for matter_id, row in zip(todo, resolved):
                _CACHE[matter_id] = (stamp, row)
                found[matter_id] = row
    from onboarding import client_removal

    hidden_rows = client_removal.visible_rows(ids, matter_id_of=str)
    return [row for matter_id in hidden_rows if (row := found.get(matter_id))]
