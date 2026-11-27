from __future__ import annotations

import datetime as dt
import re
from typing import Any, Iterable

from scanned_docs import intake_facts, scan_rows

_ORDER_RE = re.compile(r"\border\b|\bnoh\b|notice of (?:the )?hearing|hearing notice", re.I)
_NOTICE_RE = re.compile(r"\bnoh\b|notice of (?:the )?hearing|hearing notice", re.I)
_FOR_HEARING_RE = re.compile(r"\bfor\b", re.I)
_NOT_ORDER_RE = re.compile(r"\bdraft\b|^sos\b|statement of service|letter|email", re.I)
SHOWN_EXPECTED = 5
SHOWN_ORDERS = 10
SHOWN_SCAN_HINTS = 10


def long_date(iso: str) -> str:
    try:
        day = dt.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso or "")
    return f"{day.day} {day:%b %Y}"


def classify(name: str, uploaded: Any = "", modified: Any = "") -> dict[str, Any] | None:
    if not _ORDER_RE.search(name) or _NOT_ORDER_RE.search(name):
        return None
    notice = bool(_NOTICE_RE.search(name))
    hearing_date = ""
    if notice and _FOR_HEARING_RE.search(name):
        hearing_date = intake_facts.filename_date(name)
    if hearing_date:
        date, source = scan_rows.scan_date("", uploaded, modified)
    else:
        date, source = scan_rows.scan_date(name, uploaded, modified)
    return {
        "name": name,
        "kind": "notice_of_hearing" if notice else "order",
        "date": date,
        "date_source": source,
        "hearing_date": hearing_date,
    }


def filed_orders(items: Iterable[tuple[str, dict[str, Any]]], scanned: set[str]) -> list[dict[str, Any]]:
    out = []
    for folder, item in items:
        if "file" not in item:
            continue
        name = str(item.get("name") or "")
        if name in scanned:
            continue
        found = classify(name, item.get("createdDateTime"), item.get("lastModifiedDateTime"))
        if found:
            out.append({**found, "folder": folder.rsplit("/", 1)[-1], "web_url": str(item.get("webUrl") or "")})
    out.sort(key=lambda o: (o["date"], o["name"].lower()), reverse=True)
    return out


def orders_expected(orders: list[dict[str, Any]], past_hearing_dates: Iterable[str], all_hearing_dates: Iterable[str] = ()) -> list[dict[str, str]]:
    order_dates = [o["date"] for o in orders if o["kind"] == "order" and o["date"]]
    past = sorted({str(d)[:10] for d in past_hearing_dates if d})
    every = sorted({*past, *(str(d)[:10] for d in all_hearing_dates if d)})
    out = []
    for day in reversed(past):
        later = [d for d in every if d > day]
        until = later[0] if later else "9999-12-31"
        if not any(day <= d < until for d in order_dates):
            out.append({"hearing_date": day, "line": f"Hearing {long_date(day)}: no order filed yet"})
    return out[:SHOWN_EXPECTED]


def scan_hints(rows: list[dict[str, Any]], hearing_dates: Iterable[str], surname: str) -> list[dict[str, Any]]:
    days = {str(d)[:10] for d in hearing_dates if d}
    mine = str(surname or "").upper()
    out = []
    for row in rows:
        if row.get("date_source") != "filename" or row.get("scan_date") not in days:
            continue
        guess = str(row.get("possible_client") or "").upper()
        if guess and mine and guess != mine:
            continue
        day = long_date(row["scan_date"])
        out.append({
            "name": row.get("name") or "",
            "web_url": row.get("web_url") or "",
            "hearing_date": row["scan_date"],
            "surname_matches": bool(guess and guess == mine),
            "line": f"Probably this client, likely the order from the hearing on {day}",
            "label": "A guess from the file name's date" + (" and surname" if guess else "") + ", not checked. Nothing is filed from it.",
        })
    return out[:SHOWN_SCAN_HINTS]


def hints(ctx, scanned_names: set[str]) -> dict[str, Any]:
    from onboarding.pipeline import court_common as cc
    from onboarding.pipeline import hearings as hh

    out: dict[str, Any] = empty()
    orders: list[dict[str, Any]] = []
    try:
        pairs = [(f, item) for f in cc.court_orders_folders(ctx) for item in (cc.listing(ctx, f) or [])]
        orders = filed_orders(pairs, scanned_names)
        out["last_order"] = orders[0] if orders else None
        out["orders"] = orders[:SHOWN_ORDERS]
    except Exception:
        out["hint_errors"].append("Could not read the Court-Orders folder for the last order.")
    hearing_dates: list[str] = []
    try:
        from hearing_calendar import hearing_dates as hd

        hearing_dates = [d.isoformat() for h in hh.all_hearings(ctx) for d in (hd.span_days(h) or [])]
        out["orders_expected"] = orders_expected(orders, [str(h.get("hearing_date") or "")[:10] for h in hh.past(ctx)], hearing_dates)
    except Exception:
        out["hint_errors"].append("Could not read this client's hearings.")
    if hearing_dates:
        try:
            out["scan_hints"] = scan_hints(scan_rows.list_scans()["rows"], hearing_dates, ctx.surname)
        except Exception:
            out["hint_errors"].append("Could not read the Scanned Docs folder.")
    try:
        from onboarding.pipeline import step_court_reply

        recorded = step_court_reply.scanned_orders(ctx)
        for order in out["orders"]:
            order["recorded"] = order["name"].lower() in recorded
        out["email_reply_filed"] = bool(step_court_reply.email_replies_filed(ctx))
    except Exception:
        out["hint_errors"].append("Could not read Case flow's record of the court's reply.")
    return out


def empty() -> dict[str, Any]:
    return {"last_order": None, "orders": [], "email_reply_filed": False, "orders_expected": [], "scan_hints": [], "hint_errors": []}
