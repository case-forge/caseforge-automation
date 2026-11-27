#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

_TOOLS_DIR = str(Path(__file__).resolve().parent.parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from field_shapes import known_value


def name_words(name: str | None) -> frozenset[str]:
    text = re.sub(r"\([^)]*\)", " ", known_value(name).lower())
    return frozenset(w for w in re.split(r"[^a-z]+", text) if len(w) > 1)


def _email(value: str | None) -> str:
    text = known_value(value).lower()
    return "" if not text or "@" not in text else text


def _phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-10:] if len(digits) >= 10 else ""


def why_duplicate(a: dict, b: dict) -> str | None:
    wa, wb = name_words(a.get("name")), name_words(b.get("name"))
    if wa and wa == wb:
        return "same name"
    small, big = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    if len(small) >= 2 and small <= big:
        return "one name contains the other"
    ea, eb = _email(a.get("email")), _email(b.get("email"))
    if ea and ea == eb:
        return "same email"
    pa, pb = _phone(a.get("phone")), _phone(b.get("phone"))
    if pa and pa == pb:
        return "same phone"
    return None


def possible_duplicates(record: dict, others: Iterable[dict]) -> list[dict]:
    found = []
    for other in others:
        if str(other.get("matter_id")) == str(record.get("matter_id") or ""):
            continue
        reason = why_duplicate(record, other)
        if reason:
            found.append({**other, "reason": reason})
    return found


def load_records() -> list[dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import clientdb_sql

    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT m.matter_id AS matter_id, m.canonical_name AS name, "
            "p.email_primary AS email, p.phone_primary AS phone "
            "FROM matters m LEFT JOIN people p ON p.person_id = m.primary_person_id "
            "WHERE m.closed_at IS NULL"
        )
        return [dict(r._asdict()) for r in cur.fetchall()]


FLAG_FIELD = "possible_duplicate"
FLAG_LABEL = "Possible duplicate"
FLAGGED_BY = "Duplicate check"


def flag_for_check(record: dict, other: dict, reason: str) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from vergil import client_edits

    client_edits.flag_field_for_review(
        matter_id=str(record["matter_id"]),
        client_name=str(record.get("name") or ""),
        field_name=FLAG_FIELD,
        field_label=FLAG_LABEL,
        value_snapshot=f"May be the same client as matter {other['matter_id']} ({reason})",
        flagged_by=FLAGGED_BY,
        note="Check whether these are one client filed twice; merge or resolve this flag.",
    )


def pairs(records: Iterable[dict] | None = None) -> list[dict]:
    rows = list(load_records() if records is None else records)
    found = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            reason = why_duplicate(a, b)
            if reason:
                found.append({"a": a, "b": b, "reason": reason})
    return found


def main(argv: list[str]) -> int:
    flag = "--flag" in argv
    argv = [a for a in argv if a != "--flag"]
    records = load_records()
    if argv:
        probe = {"matter_id": "", "name": " ".join(argv)}
        for hit in possible_duplicates(probe, records):
            print(f"{hit['matter_id']}\t{hit['name']}\t{hit['reason']}")
        return 0
    seen = set()
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            reason = why_duplicate(a, b)
            if reason and (a["matter_id"], b["matter_id"]) not in seen:
                seen.add((a["matter_id"], b["matter_id"]))
                if flag:
                    flag_for_check(a, b, reason)
                    flag_for_check(b, a, reason)
                print(f"{a['matter_id']} {a['name']!r} ~ {b['matter_id']} {b['name']!r}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
