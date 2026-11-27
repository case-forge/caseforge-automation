#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import agwu
import clientdb_sql
from . import obligation_aging

VALID_OBLIGATIONS = set(obligation_aging.OBLIGATION_TYPES)


def _resolve_matter_id(entry: dict) -> tuple[object, str]:
    if entry.get("matter_id") not in (None, ""):
        return entry["matter_id"], "explicit matter_id"

    ref = str(entry.get("ref") or "").strip()
    name = str(entry.get("name") or "").strip()
    if not ref and not name:
        return None, "no handle (need matter_id, ref, or name)"

    for query in [q for q in (ref, name) if q]:
        resolution = agwu.resolve_client(query, limit=8, caller="backfill_open_orders._resolve_matter_id")
        rows = [m.row for m in resolution.matches]
        if not rows:
            continue
        if ref:
            for row in rows:
                refs = f"{row.get('case_reference') or ''} {row.get('reference_summary') or ''}".lower()
                if ref.lower() in refs:
                    return row.get("matter_id"), f"ref match on {query!r}"
        if len(rows) == 1:
            return rows[0].get("matter_id"), f"name match {rows[0].get('client_name')!r}"
        if name:
            exact = [r for r in rows if str(r.get("client_name") or "").strip().lower() == name.lower()]
            if len(exact) == 1:
                return exact[0].get("matter_id"), f"exact name match {exact[0].get('client_name')!r}"
    return None, f"unresolved/ambiguous for ref={ref!r} name={name!r} — pass matter_id"


def _normalise_awaiting(value) -> str:
    if isinstance(value, str):
        tokens = [t.strip() for t in value.replace(";", ",").split(",")]
    else:
        tokens = [str(t).strip() for t in (value or [])]
    kept = [t for t in tokens if t in VALID_OBLIGATIONS]
    return ", ".join(dict.fromkeys(kept))


def apply_entry(entry: dict, *, dry_run: bool) -> dict:
    matter_id, note = _resolve_matter_id(entry)
    if matter_id in (None, ""):
        return {"ok": False, "note": note, "entry": entry}

    fields = {}
    if entry.get("order_status"):
        fields["order_status"] = str(entry["order_status"])
    awaiting = _normalise_awaiting(entry.get("awaiting"))
    if awaiting:
        fields["awaiting_next_step"] = awaiting
    if entry.get("next_hearing"):
        fields["next_hearing_text"] = str(entry["next_hearing"])
    if entry.get("service_status"):
        fields["service_status"] = str(entry["service_status"])
    if entry.get("latest"):
        fields["latest_live_status"] = str(entry["latest"])

    if not fields:
        return {"ok": False, "note": "no writable fields", "matter_id": matter_id}
    if dry_run:
        return {"ok": True, "note": f"DRY-RUN {note}", "matter_id": matter_id, "fields": fields}
    result = clientdb_sql.upsert_matter_live_status(matter_id, **fields)
    result["note"] = note
    return {"ok": True, **result}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill open orders into matter_live_status")
    ap.add_argument("--seed", help="JSON file: a list of seed entries (or a single object)")
    ap.add_argument("--matter-id", help="Single entry: matter id")
    ap.add_argument("--ref", help="Single entry: matter/court reference to resolve")
    ap.add_argument("--name", help="Single entry: client name to resolve")
    ap.add_argument("--order-status", dest="order_status")
    ap.add_argument("--awaiting", help="Comma list of obligation tokens")
    ap.add_argument("--next-hearing", dest="next_hearing")
    ap.add_argument("--service-status", dest="service_status")
    ap.add_argument("--latest")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    entries: list[dict] = []
    if args.seed:
        data = json.loads(Path(args.seed).read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else [data]
    if any([args.matter_id, args.ref, args.name]):
        entries.append(
            {
                "matter_id": args.matter_id,
                "ref": args.ref,
                "name": args.name,
                "order_status": args.order_status,
                "awaiting": args.awaiting,
                "next_hearing": args.next_hearing,
                "service_status": args.service_status,
                "latest": args.latest,
            }
        )
    if not entries:
        ap.error("provide --seed FILE and/or a single entry via --matter-id/--ref/--name")

    results = [apply_entry(e, dry_run=args.dry_run) for e in entries]
    ok = sum(1 for r in results if r.get("ok"))
    print(json.dumps({"applied": ok, "total": len(results), "results": results}, indent=2, default=str))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
