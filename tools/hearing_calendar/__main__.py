from __future__ import annotations

import argparse
import datetime as dt
import json
from zoneinfo import ZoneInfo

from hearing_calendar import hearing_store


def _line(row: dict) -> str:
    return (
        f"{row.get('hearing_id')}  {str(row.get('hearing_date'))[:10]} {row.get('hearing_time') or '--:--'}  matter {row.get('matter_id') or '-'}  "
        f"{row.get('status')}  {row.get('court') or ''}  {row.get('case_ref') or row.get('case_number') or ''}  counsel: {row.get('counsel') or '-'}"
        + ("  [needs review]" if row.get("review_state") == "needs_review" else "")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hearing_calendar")
    sub = parser.add_subparsers(dest="command", required=True)
    lst = sub.add_parser("list", help="hearings in a date range, optionally for one matter (default: today onwards, 14 days)")
    lst.add_argument("--from", dest="date_from", default="")
    lst.add_argument("--to", dest="date_to", default="")
    lst.add_argument("--matter", type=int, default=None)
    lst.add_argument("--json", action="store_true")
    show = sub.add_parser("show", help="one hearing with its history")
    show.add_argument("hearing_id", type=int)
    sub.add_parser("review", help="hearings waiting for a person to confirm")
    sub.add_parser("unlinked", help="live hearings with no client linked")
    args = parser.parse_args(argv)
    if args.command == "list":
        start = args.date_from or dt.datetime.now(ZoneInfo("Europe/London")).date().isoformat()
        end = args.date_to or (dt.date.fromisoformat(start) + dt.timedelta(days=14)).isoformat()
        rows = hearing_store.list_hearings(start, end, matter_id=args.matter)
        print(json.dumps(rows, indent=2, default=str) if args.json else "\n".join(_line(r) for r in rows) or "no hearings")
    elif args.command == "show":
        row = hearing_store.get_hearing(args.hearing_id)
        print(json.dumps({"hearing": row, "history": hearing_store.history(args.hearing_id)}, indent=2, default=str))
    else:
        rows = hearing_store.review_queue() if args.command == "review" else hearing_store.unlinked_hearings()
        print("\n".join(_line(r) for r in rows) or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
