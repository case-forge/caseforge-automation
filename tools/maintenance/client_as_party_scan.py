#!/usr/bin/env python3
"Read-only scan: clients saved as a party on their own matter."
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

DETAILS = {
    "address_text": "address_text",
    "phone_primary": "phone_primary",
    "email_primary": "email_primary",
    "dob_iso": "dob_iso",
}

QUERY = """
SELECT m.matter_id, COALESCE(m.has_c8, 0), mp.matter_party_id,
       mp.address_text, mp.phone_primary, mp.email_primary, mp.dob_iso,
       p.address_text, p.phone_primary, p.email_primary, p.dob_iso
FROM matters m
JOIN matter_parties mp ON mp.matter_id = m.matter_id
LEFT JOIN people p ON p.person_id = m.primary_person_id
WHERE LOWER(TRIM(mp.role)) = LOWER(TRIM(COALESCE(m.client_role, 'Applicant')))
ORDER BY m.matter_id
"""


def _blank(value) -> bool:
    return value is None or not str(value).strip()


def classify(row) -> dict:
    matter_id, has_c8, party_id, *rest = row
    party, person = rest[:4], rest[4:]
    only_on_party = [
        name for name, mine, theirs in zip(DETAILS, party, person) if not _blank(mine) and _blank(theirs)
    ]
    return {
        "matter_id": int(matter_id),
        "party_id": int(party_id),
        "c8": bool(has_c8),
        "only_on_party_row": only_on_party,
        "safe_to_remove": not only_on_party,
    }


def scan() -> list[dict]:
    import clientdb_sql

    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(QUERY)
        return [classify(r) for r in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--c8-only", action="store_true", help="only matters carrying C8 protection")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    rows = [r for r in scan() if r["c8"] or not args.c8_only]
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    safe = [r for r in rows if r["safe_to_remove"]]
    keep = [r for r in rows if not r["safe_to_remove"]]
    print(f"Matters with the client saved as a party on their own matter: {len(rows)}")
    print(f"  holds nothing the client record lacks (removable after approval): {len(safe)}")
    print(f"  holds a detail the client record lacks (copy it over first):      {len(keep)}")
    print(f"  of those, C8 matters: {sum(1 for r in rows if r['c8'])}")
    for r in keep:
        print(f"  matter {r['matter_id']}{' [C8]' if r['c8'] else ''}: only on the party row: {', '.join(r['only_on_party_row'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
