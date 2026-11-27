
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil import attention_store

log = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60

_obligations_cache: dict[str, Any] = {"at": 0.0, "rows": [], "error": ""}

_OBLIGATIONS_UNAVAILABLE = "obligations backend unavailable"


def _store_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": attention_store.item_task_id(row["item_id"]),
        "matter_id": row["matter_id"],
        "who": row["who"],
        "label": row["label"],
        "kind": row["kind"],
        "complaint_domain": row["complaint_domain"],
        "severity": row.get("severity") or "",
        "settlement_stage": row["settlement_stage"],
        "subject": row["subject"],
        "summary": row["summary"],
        "deadline": row["deadline"],
        "importance": row["importance"],
        "status": "completed" if row["status"] == "done" else "notStarted",
        "created": row["created_utc"],
        "web_link": row["web_link"],
        "message_key": row["message_key"],
        "sender_domain": row["sender_domain"],
        "can_complete": True,
    }


def _order_key(item: dict[str, Any]) -> tuple[int, int]:
    return (1 if item["status"] == "completed" else 0, 0 if item["kind"] == "complaint" and item.get("severity") != "soft" else 1)


def matter_tasks(matter_id: str, *, limit: int = 50) -> dict[str, Any]:
    matter_id = str(matter_id or "").strip()
    try:
        items = [
            _store_item(row) for row in attention_store.list_for_matter(matter_id)
            if row["kind"] in {"update", "complaint", "switchboard", "scope_creep", "settlement"}
        ]
    except Exception as exc:
        log.error("attention store read failed: %s", type(exc).__name__)
        return {
            "matter_id": matter_id,
            "configured": False,
            "open_complaints": 0,
            "open_updates": 0,
            "open_settlements": 0,
            "items": [],
        }
    items.sort(key=lambda row: row["created"], reverse=True)
    items.sort(key=_order_key)
    open_items = [row for row in items if row["status"] != "completed"]
    return {
        "matter_id": matter_id,
        "configured": True,
        "open_complaints": sum(1 for row in open_items if row["kind"] == "complaint" and row.get("severity") != "soft"),
        "open_updates": sum(1 for row in open_items if row["kind"] not in ("complaint", "settlement") or (row["kind"] == "complaint" and row.get("severity") == "soft")),
        "open_settlements": sum(1 for row in open_items if row["kind"] == "settlement"),
        "items": items[:limit],
    }


def _newest_first(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: row["created"], reverse=True)


def _obligation_rows() -> tuple[list[dict[str, Any]], str]:
    now = time.monotonic()
    if not _obligations_cache["at"] or now - _obligations_cache["at"] >= CACHE_TTL_SECONDS:
        error = ""
        rows: list[dict[str, Any]] = []
        try:
            from vergil import monitor_store

            found, failure = monitor_store.load_monitor_obligations()
            if failure:
                error = _OBLIGATIONS_UNAVAILABLE
            for ob in found:
                if ob.get("urgency") not in {"amber", "red"}:
                    continue
                rows.append(
                    {
                        "matter_id": "" if ob.get("matter_id") is None else str(ob["matter_id"]),
                        "matter_ref": str(ob.get("matter_ref") or ""),
                        "client": str(ob.get("client") or ""),
                        "label": str(ob.get("label") or ""),
                        "urgency": str(ob["urgency"]),
                        "reason": str(ob.get("reason") or ""),
                        "hearing_date": str(ob.get("hearing_date") or ""),
                        "age_working_days": ob.get("age_working_days"),
                        "court": str(ob.get("court") or ""),
                        "has_c8": bool(ob.get("has_c8")),
                    }
                )
        except Exception as exc:
            log.error("obligation read failed: %s", type(exc).__name__)
            error = _OBLIGATIONS_UNAVAILABLE
            rows = []
        rows.sort(
            key=lambda r: (
                0 if r["urgency"] == "red" else 1,
                r["hearing_date"] == "",
                r["hearing_date"],
                -(r["age_working_days"] if isinstance(r["age_working_days"], int) else -1),
            )
        )
        _obligations_cache.update(at=now, rows=rows, error=error)
    return list(_obligations_cache["rows"]), str(_obligations_cache["error"])


def attention(*, limit: int = 25) -> dict[str, Any]:
    store_ok = True
    try:
        stored_rows = attention_store.list_open()
    except Exception as exc:
        store_ok = False
        stored_rows = []
        log.error("attention store read failed: %s", type(exc).__name__)

    stored = [_store_item(row) for row in stored_rows]
    obligations, obligations_error = _obligation_rows()

    def newest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _newest_first(rows)

    red = newest([r for r in stored if r["kind"] == "complaint" and r.get("severity") != "soft"])
    soft_complaints = newest([
        r for r in stored
        if r["kind"] == "switchboard" or (r["kind"] == "complaint" and r.get("severity") == "soft")
    ])
    green = newest([r for r in stored if r["kind"] in ("settlement", "new_client")])
    yellow = newest([r for r in stored if r["kind"] == "update" and r["label"] != "FYI"])
    yellow.sort(key=lambda row: 0 if row["importance"] == "high" else 1)
    yellow += soft_complaints
    scope_creep = newest([r for r in stored if r["kind"] == "scope_creep"])
    accepted = newest([r for r in stored if r["kind"] == "counsel_accepted"])
    rejected = newest([r for r in stored if r["kind"] == "counsel_rejected"])
    court_order = newest([r for r in stored if r["kind"] == "court_order"])
    court_rejected = newest([r for r in stored if r["kind"] == "court_rejected"])
    result = {
        "configured": store_ok,
        "red_count": len(red),
        "yellow_count": len(yellow),
        "green_count": len(green),
        "red": red[:limit],
        "yellow": yellow[:limit],
        "green": green[:limit],
        "scope_creep_count": len(scope_creep),
        "scope_creep": scope_creep[:limit],
        "counsel_accepted_count": len(accepted),
        "counsel_accepted": accepted[:limit],
        "counsel_rejected_count": len(rejected),
        "counsel_rejected": rejected[:limit],
        "court_order_count": len(court_order),
        "court_order": court_order[:limit],
        "court_rejected_count": len(court_rejected),
        "court_rejected": court_rejected[:limit],
        "obligations_count": len(obligations),
        "obligations": obligations[:limit],
        "obligations_error": obligations_error,
    }
    return result


def complete_item(task_id: str, by: str) -> dict[str, Any]:
    item_id = attention_store.parse_task_id(task_id)
    item = _store_item(attention_store.complete(item_id, by))
    from vergil import auto_flags

    auto_flags.on_attention_completed(item)
    return item
