#!/usr/bin/env python3

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import robot_notices
from vergil import attention_store, client_edits

log = logging.getLogger(__name__)

UNSORTED_AN_REASON = "Attendance note filed to Unsorted"
COMPLAINT_REASON = "Client complaint to deal with"
CARE_CASE_NUMBER_REASON = "Email quotes a care proceedings case number (type C)"
UNSORTED_AN_KIND = "attendance_note_unsorted"
_SET_BY = "Automatic"


def raise_flag(matter_id: str, reason: str, *, db_path: Any = None) -> None:
    matter = str(matter_id or "").strip()
    if not matter:
        return
    try:
        client_edits.set_flag(matter_id=matter, flag_name="flagged", is_set=True, set_by=_SET_BY, reason=reason, db_path=db_path)
    except Exception as exc:
        log.error("automatic flag not raised: %s", type(exc).__name__)


def clear_flag(matter_id: str, reason: str, *, db_path: Any = None) -> None:
    matter = str(matter_id or "").strip()
    if not matter:
        return
    try:
        client_edits.set_flag(
            matter_id=matter, flag_name="flagged", is_set=False, set_by=_SET_BY, only_if_reason=reason, db_path=db_path
        )
    except Exception as exc:
        log.error("automatic flag not cleared: %s", type(exc).__name__)


def on_notice_dismissed(notice_id: str, *, db_path: Any = None) -> bool:
    try:
        notice = robot_notices.get(notice_id, db_path=db_path)
        if not notice or notice["kind"] != UNSORTED_AN_KIND:
            return False
        matter = str(notice.get("matter_id") or "").strip()
        if matter and not robot_notices.open_for(matter, UNSORTED_AN_KIND, db_path=db_path):
            clear_flag(matter, UNSORTED_AN_REASON, db_path=db_path)
        return True
    except Exception as exc:
        log.error("unsorted flag not cleared: %s", type(exc).__name__)
        return False


def on_attention_completed(item: dict[str, Any], *, db_path: Any = None) -> None:
    try:
        if item.get("kind") != "complaint":
            return
        matter = str(item.get("matter_id") or "").strip()
        open_hard = [r for r in attention_store.list_open(kinds=("complaint",), matter_id=matter) if r.get("severity") != "soft"]
        if matter and not open_hard:
            clear_flag(matter, COMPLAINT_REASON, db_path=db_path)
    except Exception as exc:
        log.error("complaint flag not cleared: %s", type(exc).__name__)
