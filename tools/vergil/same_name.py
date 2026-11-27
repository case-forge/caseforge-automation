#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from typing import Any, Callable, Iterable

TTL_SECONDS = 60.0
FIELDS = ("same_name_index", "same_name_count", "same_name_birth_year", "same_name_ref")

log = logging.getLogger(__name__)
_LOCK = threading.Lock()
_CACHE: tuple[float, dict[str, dict[str, Any]]] | None = None


def clear() -> None:
    global _CACHE
    with _LOCK:
        _CACHE = None


def _sortable(value: Any) -> str:
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value or "").strip()


def _birth_year(value: Any) -> int | None:
    if isinstance(value, dt.date):
        return value.year
    text = str(value or "").strip()
    return int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else None


def build_labels(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("canonical_name_key") or "").strip()
        person = str(row.get("person_id") or "").strip()
        matter = str(row.get("matter_id") or "").strip()
        if not key or not person or not matter:
            continue
        entry = groups.setdefault(key, {}).setdefault(
            person, {"first": None, "dob": row.get("dob_iso"), "matters": []}
        )
        created = _sortable(row.get("created_utc"))
        if created and (entry["first"] is None or created < entry["first"]):
            entry["first"] = created
        entry["matters"].append((matter, str(row.get("company_reference") or "").strip()))

    def person_order(item: tuple[str, dict[str, Any]]) -> tuple:
        person, entry = item
        numeric = int(person) if person.isdigit() else None
        return (entry["first"] is None, entry["first"] or "", numeric is None, numeric or 0, person)

    labels: dict[str, dict[str, Any]] = {}
    for people in groups.values():
        if len(people) < 2:
            continue
        for index, (_person, entry) in enumerate(sorted(people.items(), key=person_order), start=1):
            for matter, ref in entry["matters"]:
                labels[matter] = {
                    "same_name_index": index,
                    "same_name_count": len(people),
                    "same_name_birth_year": _birth_year(entry["dob"]),
                    "same_name_ref": ref or None,
                }
    return labels


def labels(*, loader: Callable[[], list[dict[str, Any]]] | None = None) -> dict[str, dict[str, Any]]:
    global _CACHE
    now = time.monotonic()
    with _LOCK:
        if _CACHE and now - _CACHE[0] < TTL_SECONDS:
            return _CACHE[1]
    if loader is None:
        import clientdb_sql

        from onboarding import client_removal

        hidden = client_removal.hidden_ids(None)
        rows = [r for r in clientdb_sql.list_same_name_people() if str(r.get("matter_id") or "").strip() not in hidden]
    else:
        rows = loader()
    built = build_labels(rows)
    with _LOCK:
        _CACHE = (time.monotonic(), built)
    return built


def annotate(
    rows: Iterable[dict[str, Any]],
    *,
    matter_id_key: str = "matter_id",
    loader: Callable[[], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    rows = list(rows)
    if not rows:
        return rows
    try:
        found = labels(loader=loader)
    except Exception as exc:
        log.warning("same-name labels unavailable: %s", type(exc).__name__)
        return rows
    for row in rows:
        if not isinstance(row, dict):
            continue
        matter = str(row.get(matter_id_key) or "").strip()
        if not matter:
            continue
        label = found.get(matter)
        if label:
            row.update(label)
        else:
            row.update({"same_name_index": 1, "same_name_count": 1, "same_name_birth_year": None, "same_name_ref": None})
    return rows
