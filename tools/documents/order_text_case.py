#!/usr/bin/env python3

from __future__ import annotations

import argparse
import functools
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import order_codes

COURTS_DATA = REPO_ROOT / "context" / "courts-data.json"
BACKFILL_EDITOR = "system:order-text-case"

ACRONYMS: tuple[str, ...] = (
    "FL401", "FL403", "C100", "C1A", "C8",
    "NMO", "OO", "CAO", "PSO", "SIO", "DVPO",
    "LAA", "DV", "UK",
)

_COURT_SUFFIXES = (" Family Court", " Magistrates' Court", " County Court")


@functools.lru_cache(maxsize=1)
def court_names() -> tuple[str, ...]:
    try:
        data = json.loads(COURTS_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    names = {str(c.get("name") or "").strip() for c in data.get("courts", []) if isinstance(c, dict)}
    return tuple(sorted((n for n in names if n), key=lambda n: (-len(n), n)))


@functools.lru_cache(maxsize=1)
def court_venues() -> tuple[str, ...]:
    venues = set()
    for name in court_names():
        for suffix in _COURT_SUFFIXES:
            if name.endswith(suffix):
                venues.add(name[: -len(suffix)].strip())
                break
    return tuple(sorted((v for v in venues if v), key=lambda v: (-len(v), v)))


def _whole(word: str) -> str:
    return r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])"


def is_all_caps(text: str) -> bool:
    return any(ch.isalpha() for ch in text) and not any(ch.islower() for ch in text)


def _sentence_case(text: str) -> str:
    lowered = text.lower()
    return re.sub(r"(^|[.!?]\s+)([^\W\d_])", lambda m: m.group(1) + m.group(2).upper(), lowered, flags=re.UNICODE)


def restore_acronyms(text: str) -> str:
    for acronym in ACRONYMS:
        text = re.sub(_whole(acronym), acronym, text, flags=re.IGNORECASE)
    return text


hyphenate_non_molestation = order_codes.hyphenate_non_molestation


def normalise_order_text(value: Any) -> str:
    if value is None:
        return ""
    text = hyphenate_non_molestation(str(value))
    if not text.strip():
        return ""
    if not is_all_caps(text):
        return text
    out = restore_acronyms(_sentence_case(text.strip()))
    for name in court_names():
        out = re.sub(_whole(name), lambda _m, n=name: n, out, flags=re.IGNORECASE)
    out = re.sub(_whole("family court"), "Family Court", out, flags=re.IGNORECASE)
    for venue in court_venues():
        out = re.sub(
            r"(?i)(\b(?:court|sitting) at\s+)" + _whole(venue),
            lambda m, v=venue: m.group(1) + v,
            out,
        )
    return out



def plan_backfill(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    changes = []
    for row in rows:
        old = str(row.get("order_requested_text") or "")
        new = normalise_order_text(old)
        if new and new != old:
            changes.append({"matter_id": str(row.get("matter_id")), "old": old, "new": new})
    return changes


def _load_rows() -> list[dict[str, Any]]:
    import clientdb_sql

    sql = "SELECT matter_id, order_requested_text FROM matters WHERE order_requested_text IS NOT NULL"
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def apply_backfill(changes: list[dict[str, str]]) -> dict[str, Any]:
    from vergil import client_edits

    applied, errored = [], []
    for change in changes:
        try:
            client_edits.record_edit(
                matter_id=change["matter_id"],
                field_name="order_requested_text",
                new_value=change["new"],
                note="Sentence-cased ALL CAPS order text (gh#468)",
                edited_by=BACKFILL_EDITOR,
            )
            applied.append(change["matter_id"])
        except Exception as exc:
            errored.append({"matter_id": change["matter_id"], "reason": str(exc)})
    return {"applied": applied, "errored": errored}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sentence-case ALL CAPS order text.")
    parser.add_argument("text", nargs="?", help="Normalise one string and print it")
    parser.add_argument("--backfill", action="store_true", help="List matters whose order text would change (dry run)")
    parser.add_argument("--apply", action="store_true", help="With --backfill, write the changes through client_edits")
    args = parser.parse_args(argv)

    if args.backfill:
        changes = plan_backfill(_load_rows())
        if not args.apply:
            print(json.dumps({"dry_run": True, "would_change": len(changes), "changes": changes}, indent=2))
            return 0
        result = apply_backfill(changes)
        print(json.dumps({"dry_run": False, **result}, indent=2))
        return 1 if result["errored"] else 0
    if args.apply:
        parser.error("--apply only goes with --backfill")
    if args.text is None:
        parser.error("give a text to normalise, or --backfill")
    print(normalise_order_text(args.text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
