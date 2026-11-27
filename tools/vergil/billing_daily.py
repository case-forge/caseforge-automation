
from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from billing import billing_items

LONDON = ZoneInfo("Europe/London")
MAX_DAYS = 366
DEFAULT_DAYS = 30


def london_today() -> dt.date:
    return dt.datetime.now(LONDON).date()


def _pence(text: str) -> int | None:
    try:
        return int((Decimal(text) * 100).quantize(Decimal(1)))
    except (InvalidOperation, ValueError):
        return None


def daily_totals(start: dt.date, end: dt.date, *, db_path: str | Path | None = None) -> dict[str, Any]:
    if end < start:
        raise ValueError("the start date must not be after the end date")
    count = (end - start).days + 1
    if count > MAX_DAYS:
        raise ValueError(f"a range is at most {MAX_DAYS} days")
    sums: dict[dt.date, list[int]] = {}
    undated = 0
    for item_date, net, vat in billing_items.money_rows(db_path=db_path):
        day = billing_items.parse_item_date(item_date)
        net_p, vat_p = _pence(net), _pence(vat)
        if day is None or net_p is None or vat_p is None:
            undated += 1
            continue
        if start <= day <= end:
            row = sums.setdefault(day, [0, 0, 0])
            row[0] += 1
            row[1] += net_p
            row[2] += vat_p
    days = []
    for offset in range(count):
        day = start + dt.timedelta(days=offset)
        n, net_p, vat_p = sums.get(day, (0, 0, 0))
        days.append({"date": day.isoformat(), "items": n, "net_pence": net_p, "vat_pence": vat_p,
                     "gross_pence": net_p + vat_p})
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "days": days,
        "total_items": sum(d["items"] for d in days),
        "total_net_pence": sum(d["net_pence"] for d in days),
        "total_vat_pence": sum(d["vat_pence"] for d in days),
        "total_gross_pence": sum(d["gross_pence"] for d in days),
        "undated_items": undated,
    }
