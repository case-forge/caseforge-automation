#!/usr/bin/env python3
"Tidy the hearings already held for review, to the rules the finder now writes by (owner, 2026-11-19)."
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from hearing_calendar import hearing_store

ACTOR = "system:hearing-tidy"
KEEP, CLEAR, SHORTEN, TO_LEAD = "keep", "clear", "shorten", "to_lead"

NOT_DOUBT = (
    re.compile(r"^no time estimate was given\b", re.IGNORECASE),
    re.compile(r"^no hearing time stated$", re.IGNORECASE),
)
GUESS = re.compile(r"^read by the model without a matching hearing sentence", re.IGNORECASE)
SENTENCE_BACKED = re.compile(
    r"the message mentions|the text contains hearing-worded|also states this hearing|lists more hearing dates|deterministic said",
    re.IGNORECASE,
)


def reasons_of(text: str) -> list[str]:
    return [part.strip() for part in str(text or "").split(";") if part.strip()]


def is_guess(row: dict[str, Any]) -> bool:
    parts = reasons_of(str(row.get("review_reason") or ""))
    return any(GUESS.search(part) for part in parts) and not any(SENTENCE_BACKED.search(part) for part in parts)


def plan_row(row: dict[str, Any], today: str) -> dict[str, str]:
    "What to do with one hearing in review, and the reason text it would keep. Pure."
    text = str(row.get("review_reason") or "")
    if row.get("human_edited") or row.get("review_state") != "needs_review":
        return {"action": KEEP, "reason": text}
    upcoming = str(row.get("hearing_date") or "")[:10] >= today
    if (
        upcoming
        and is_guess(row)
        and str(row.get("source_kind") or "") == "email"
        and str(row.get("source_message_id") or "").strip()
        and str(row.get("status") or "") == "scheduled"
        and not str(row.get("counsel") or "").strip()
        and not row.get("counsel_booked")
    ):
        return {"action": TO_LEAD, "reason": ""}
    kept = [part for part in reasons_of(text) if not any(pattern.search(part) for pattern in NOT_DOUBT)]
    remaining = "; ".join(kept)
    if not kept:
        return {"action": CLEAR, "reason": ""}
    if remaining != "; ".join(reasons_of(text)):
        return {"action": SHORTEN, "reason": remaining}
    return {"action": KEEP, "reason": text}


def _to_lead(row: dict[str, Any]) -> str:
    "Put the hearing's email on the emails-to-check list, then dismiss the hearing. Returns what happened."
    lead = hearing_store.record_lead(
        source_message_id=str(row["source_message_id"]),
        source_subject=str(row.get("source_subject") or ""),
        source_received_utc=str(row.get("source_received_utc") or ""),
        source_web_link=str(row.get("source_web_link") or ""),
        reason=hearing_store.unbacked_read_reason(str(row["hearing_date"])[:10], str(row.get("hearing_time") or ""), str(row.get("case_ref") or "")),
        actor=ACTOR,
    )
    if lead["action"] == "exists" and str((lead.get("lead") or {}).get("state") or "") != "open":
        return "kept: a person already closed that email's check"
    hearing_store.resolve_review(int(row["hearing_id"]), "dismiss", actor=ACTOR)
    return "lead_created" if lead["action"] == "created" else "lead_existed"


def run(*, apply: bool = False, today: str | None = None) -> dict[str, Any]:
    day = today or hearing_store.london_today().isoformat()
    queue = hearing_store.review_queue(include_past=True)
    counts: dict[str, int] = {}
    outcomes: dict[str, int] = {}

    def bump(table: dict[str, int], key: str) -> None:
        table[key] = table.get(key, 0) + 1

    for row in queue:
        plan = plan_row(row, day)
        when = "upcoming" if str(row.get("hearing_date") or "")[:10] >= day else "past"
        bump(counts, f"{plan['action']} ({when})")
        if not apply or plan["action"] == KEEP:
            continue
        if plan["action"] == TO_LEAD:
            bump(outcomes, _to_lead(row))
        else:
            hearing_store.tidy_review(int(row["hearing_id"]), plan["reason"], actor=ACTOR)
            bump(outcomes, plan["action"])
    return {
        "in_review_before": len(queue),
        "upcoming_in_review_before": sum(1 for row in queue if str(row.get("hearing_date") or "")[:10] >= day),
        "plan": dict(sorted(counts.items())),
        "applied": bool(apply),
        "outcomes": dict(sorted(outcomes.items())),
        **({"upcoming_in_review_after": len(hearing_store.review_queue(today=day))} if apply else {}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the changes (default: count only)")
    args = parser.parse_args(argv)
    print(json.dumps(run(apply=args.apply), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
