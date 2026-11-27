#!/usr/bin/env python3
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import clientdb_sql

log = logging.getLogger(__name__)

NOT_ON_BENEFITS = "not_on_benefits"
ON_BENEFITS = "on_benefits"
UNRECOGNISED = "unrecognised"
NOT_READ = "not_read"

_NO_BENEFIT_VALUES = frozenset(
    {"", "n/a", "na", "n.a", "no", "none", "nil", "-", "not applicable", "no benefits", "not on benefits"}
)
_BENEFIT_NAMES = (
    "uc", "universal credit", "esa", "employment and support allowance", "pip",
    "personal independence payment", "income support", "jsa", "jobseeker's allowance",
    "jobseekers allowance", "dla", "disability living allowance", "housing benefit",
    "child benefit", "carer's allowance", "carers allowance", "pension credit",
    "tax credit", "tax credits", "attendance allowance",
)
_BENEFIT_RE = re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(n) for n in _BENEFIT_NAMES) + r")(?![a-z])")
_NEGATIVE_OPENING = re.compile(r"^(?:no|not|none|nil|n/a|na|never)(?![a-z])")


def benefits_decision(value: Any) -> str:
    text = " ".join(str(value if value is not None else "").split()).lower().strip(" .,;:!?()[]\"'")
    if text in _NO_BENEFIT_VALUES:
        return NOT_ON_BENEFITS
    if text == "yes" or (_BENEFIT_RE.search(text) and not _NEGATIVE_OPENING.match(text)):
        return ON_BENEFITS
    return UNRECOGNISED




def remember_decision(matter_id: Any, decision: str) -> None:
    import ops_db

    with ops_db.connect() as conn:
        conn.execute(
            "INSERT INTO matter_legal_aid (matter_id, benefits_decision, updated_utc) VALUES (?, ?, ?) "
            "ON CONFLICT(matter_id) DO UPDATE SET benefits_decision = excluded.benefits_decision, updated_utc = excluded.updated_utc",
            (str(int(matter_id)), decision, ops_db.utc_now_z()),
        )
        conn.commit()


def remembered_decision(matter_id: Any) -> str:
    import ops_db

    with ops_db.connect() as conn:
        row = conn.execute("SELECT benefits_decision FROM matter_legal_aid WHERE matter_id = ?", (str(int(matter_id)),)).fetchone()
    return str(row[0] or "") if row else ""


def _flag_for_review(matter_id: int, decision: str) -> bool:
    reason = "was not read" if decision == NOT_READ else "is not one the legal aid rule recognises"
    note = f"legal-aid-review: the benefits entry on the referrer intro {reason}; check whether the LAA means link is needed"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_notes FROM matters WHERE matter_id = ?", (matter_id,))
        row = cursor.fetchone()
        if row is None:
            return False
        current = str(row[0] or "")
        if "legal-aid-review:" not in current:
            cursor.execute(
                "UPDATE matters SET tracker_notes = ? WHERE matter_id = ?",
                (f"{current}\n{note}" if current else note, matter_id),
            )
    return True


def on_intro_extracted(matter_id: Any, fields: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    record: dict[str, Any] = {"decision": NOT_READ, "flagged": False, "error": ""}
    try:
        mid = int(matter_id)
        if "_benefits_raw" in fields:
            record["decision"] = benefits_decision(fields.get("_benefits_raw"))
        if dry_run:
            return record
        remember_decision(mid, record["decision"])
        if record["decision"] in (UNRECOGNISED, NOT_READ):
            record["flagged"] = _flag_for_review(mid, record["decision"])
    except Exception as exc:
        record["error"] = type(exc).__name__
        log.error("legal aid decision not recorded: %s", type(exc).__name__)
    return record
