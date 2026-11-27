
from __future__ import annotations

import datetime as dt
import re
import sys
import uuid
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import app_settings
import csv_safe
import ops_db
from billing import billing_store, rates


class BillingItemError(ValueError):
    pass


CATEGORY_RATES: dict[str, tuple[Decimal, bool]] = {
    "routine_letter_out": (rates.ROUTINE_LETTER_OUT_RATE, False),
    "routine_letter_in": (rates.ROUTINE_LETTER_IN_RATE, False),
    "telephone": (rates.TELEPHONE_RATE, False),
    "attendance_preparation": (rates.ATTENDANCE_PREP_RATE, True),
    "attendance_counsel_court": (rates.ATTENDANCE_COUNSEL_COURT_RATE, True),
    "advocacy_court": (rates.ADVOCACY_COURT_RATE, True),
    "travelling_waiting": (rates.TRAVELLING_WAITING_RATE, True),
    "bundle_pages": (rates.BUNDLE_PAGE_RATE, False),
    "court_document_pages": (rates.COURT_DOCUMENT_PAGE_RATE, False),
    "received_document_pages": (rates.COURT_DOCUMENT_PAGE_RATE, False),
}

TBC_CATEGORY = "received_document_tbc"
TBC = "TBC"

CATEGORY_LABELS: dict[str, str] = {
    "routine_letter_out": "Letter Out",
    "routine_letter_in": "Routine Letter In",
    "telephone": "Telephone",
    "attendance_preparation": "Attendance/Preparation",
    "attendance_counsel_court": "Attendance on Counsel/Court",
    "advocacy_court": "Advocacy at Court",
    "travelling_waiting": "Travelling/Waiting",
    "bundle_pages": "Bundle (per page)",
    "court_document_pages": "Court forms and draft orders (per page)",
    "received_document_pages": "Received documents (per page)",
    TBC_CATEGORY: "Received document (rate TBC)",
}


BASIS_LEGAL_AID = "legal_aid"
BASIS_PRIVATE = "private"
PRIVATE_FLAG = "private_billing"


def matter_basis(matter_id: str, *, db_path: str | Path | None = None) -> str:
    matter = _clean(matter_id, limit=128)
    if not matter:
        return BASIS_LEGAL_AID
    with ops_db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT is_set FROM matter_flags WHERE matter_id = ? AND flag_name = ?", (matter, PRIVATE_FLAG)
        ).fetchone()
    return BASIS_PRIVATE if row and row[0] else BASIS_LEGAL_AID


def rate_for(category: str, basis: str = BASIS_LEGAL_AID, *, db_path: str | Path | None = None) -> Decimal | None:
    if category not in CATEGORY_RATES:
        raise BillingItemError(f"unknown billing category {category!r}; expected one of {sorted(CATEGORY_RATES)}")
    if basis == BASIS_PRIVATE:
        if CATEGORY_RATES[category][1]:
            return Decimal(str(app_settings.get_setting("private_hourly_rate", db_path=db_path)))
        return rates.RATE_TIERS.get(category, {}).get("private")
    if category in PAGE_CATEGORIES:
        return page_rate(db_path=db_path)
    return Decimal(str(app_settings.get_setting(f"{app_settings.LEGAL_AID_RATE_PREFIX}{category}", db_path=db_path)))


PAGE_CATEGORIES = ("bundle_pages", "court_document_pages", "received_document_pages")


def page_rate(*, db_path: str | Path | None = None) -> Decimal:
    hourly = Decimal(str(app_settings.get_setting(f"{app_settings.LEGAL_AID_RATE_PREFIX}attendance_preparation", db_path=db_path)))
    minutes = Decimal(str(app_settings.get_setting("minutes_per_page", db_path=db_path)))
    return (hourly * minutes / Decimal(60)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def charging_rates(basis: str = BASIS_LEGAL_AID, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for category, (_family, is_hourly) in CATEGORY_RATES.items():
        rate = rate_for(category, basis, db_path=db_path)
        out.append(
            {
                "category": category,
                "label": CATEGORY_LABELS[category],
                "rate": TBC if rate is None else _money(rate),
                "unit": "per hour" if is_hourly else "per item",
            }
        )
    return out


def _clean(value: Any, *, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def compute_net_amount(category: str, *, quantity: Decimal, minutes: int, rate: Decimal | None = None) -> Decimal:
    if category not in CATEGORY_RATES:
        raise BillingItemError(f"unknown billing category {category!r}; expected one of {sorted(CATEGORY_RATES)}")
    is_hourly = CATEGORY_RATES[category][1]
    rate = CATEGORY_RATES[category][0] if rate is None else rate
    if is_hourly:
        return rate * Decimal(minutes) / Decimal(60)
    return rate * quantity


def _insert_once(row: dict[str, Any], db_path: str | Path | None) -> dict[str, Any]:
    with billing_store.connect(db_path) as conn:
        cursor = conn.execute(
            f"INSERT INTO matter_billing_items ({', '.join(ITEM_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in ITEM_COLUMNS)}) ON CONFLICT DO NOTHING",
            tuple(row[col] for col in ITEM_COLUMNS),
        )
        if cursor.rowcount or not row.get("work_id"):
            return row
        found = conn.execute(
            f"SELECT {', '.join(ITEM_COLUMNS)} FROM matter_billing_items "
            "WHERE matter_id = ? AND work_id = ? AND COALESCE(tbc_category, category) = ?",
            (row["matter_id"], row["work_id"], row.get("tbc_category") or row["category"]),
        ).fetchone()
    if found is None:
        return row
    return {**dict(zip(ITEM_COLUMNS, found)), "already_recorded": True}


ITEM_COLUMNS = (
    "item_id", "matter_id", "item_date", "category", "description", "quantity",
    "minutes", "rate", "net_amount", "vat_amount", "work_id", "case_ref",
    "source_file", "client_name", "created_at", "party", "document_url", "schedule", "tbc_category",
)

SCHEDULES = (1, 2)

PARTIES = tuple(rates.GROUP_LABELS)


def party_labels() -> dict[str, str]:
    return dict(rates.GROUP_LABELS)


def record_item(
    *,
    matter_id: str,
    item_date: str,
    category: str,
    description: str,
    quantity: Decimal | int | str = 1,
    minutes: int = 0,
    work_id: str = "",
    case_ref: str = "",
    source_file: str = "",
    client_name: str = "",
    party: str = "",
    document_url: str = "",
    schedule: int | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        raise BillingItemError("matter_id is required")
    date_clean = _clean(item_date, limit=32)
    if not date_clean:
        raise BillingItemError("item_date is required")
    party_clean = _clean(party, limit=32)
    if party_clean and party_clean not in PARTIES:
        raise BillingItemError(f"unknown party {party_clean!r}; expected one of {list(PARTIES)}")
    if schedule is not None and schedule not in SCHEDULES:
        raise BillingItemError(f"schedule must be one of {list(SCHEDULES)} or None, got {schedule!r}")
    quantity_dec = Decimal(str(quantity))
    rate = rate_for(category, matter_basis(matter, db_path=db_path), db_path=db_path)
    if rate is None:
        return record_tbc_item(
            matter_id=matter, item_date=date_clean,
            description=f"{_clean(description, limit=420)} (private rate TBC: {CATEGORY_LABELS[category]})",
            quantity=quantity_dec, minutes=minutes, work_id=work_id, source_file=source_file,
            client_name=client_name, document_url=document_url, party=party_clean, schedule=schedule,
            tbc_category=category, db_path=db_path,
        )
    net = compute_net_amount(category, quantity=quantity_dec, minutes=minutes, rate=rate)
    vat = net * rates.VAT_RATE

    row = {
        "item_id": uuid.uuid4().hex,
        "matter_id": matter,
        "item_date": date_clean,
        "category": category,
        "description": _clean(description, limit=500),
        "quantity": str(quantity_dec),
        "minutes": int(minutes or 0),
        "rate": str(rate),
        "net_amount": _money(net),
        "vat_amount": _money(vat),
        "work_id": _clean(work_id, limit=64),
        "case_ref": _clean(case_ref, limit=64),
        "source_file": _clean(source_file, limit=300),
        "client_name": _clean(client_name, limit=200),
        "created_at": ops_db.utc_now_z(),
        "party": party_clean,
        "document_url": _clean(document_url, limit=2000),
        "schedule": schedule,
        "tbc_category": None,
    }

    return _insert_once(row, db_path)


_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")
_UK_DATE_RE = re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2}|\d{4})$")


def parse_item_date(value: Any) -> dt.date | None:
    text = str(value or "").strip()
    try:
        iso = _ISO_DATE_RE.match(text)
        if iso:
            return dt.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        uk = _UK_DATE_RE.match(text)
        if uk:
            year = int(uk.group(3))
            return dt.date(year + 2000 if year < 100 else year, int(uk.group(2)), int(uk.group(1)))
    except ValueError:
        return None
    return None


def _bill_order(item: dict[str, Any]) -> tuple:
    when = parse_item_date(item.get("item_date"))
    return (when is None, when or dt.date.max, str(item.get("created_at") or ""))


def list_items(matter_id: str, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        return []
    with billing_store.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            f"SELECT {', '.join(ITEM_COLUMNS)} FROM matter_billing_items "
            "WHERE matter_id = ? AND removed_utc IS NULL AND category != ?",
            (matter, TBC_CATEGORY),
        ).fetchall()
    return sorted((dict(zip(ITEM_COLUMNS, row)) for row in rows), key=_bill_order)


def money_rows(*, db_path: str | Path | None = None) -> list[tuple[str, str, str]]:
    with billing_store.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            "SELECT item_date, net_amount, vat_amount FROM matter_billing_items "
            "WHERE removed_utc IS NULL AND category != ?",
            (TBC_CATEGORY,),
        ).fetchall()
    return [(str(r[0] or ""), str(r[1] or ""), str(r[2] or "")) for r in rows]


def list_rate_tbc_items(matter_id: str, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        return []
    columns = (*ITEM_COLUMNS, *REMOVAL_COLUMNS)
    with billing_store.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            f"SELECT {', '.join(columns)} FROM matter_billing_items WHERE matter_id = ? AND category = ?",
            (matter, TBC_CATEGORY),
        ).fetchall()
    return sorted((dict(zip(columns, row)) for row in rows), key=_bill_order)


def record_tbc_item(
    *,
    matter_id: str,
    item_date: str,
    description: str,
    quantity: int | str | Decimal = 1,
    minutes: int = 0,
    work_id: str = "",
    source_file: str = "",
    client_name: str = "",
    document_url: str = "",
    party: str = "",
    schedule: int | None = None,
    tbc_category: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        raise BillingItemError("matter_id is required")
    date_clean = _clean(item_date, limit=32)
    if not date_clean:
        raise BillingItemError("item_date is required")
    row = {
        "item_id": uuid.uuid4().hex,
        "matter_id": matter,
        "item_date": date_clean,
        "category": TBC_CATEGORY,
        "description": _clean(description, limit=500),
        "quantity": str(Decimal(str(quantity))),
        "minutes": int(minutes or 0),
        "rate": TBC,
        "net_amount": TBC,
        "vat_amount": TBC,
        "work_id": _clean(work_id, limit=64),
        "case_ref": "",
        "source_file": _clean(source_file, limit=300),
        "client_name": _clean(client_name, limit=200),
        "created_at": ops_db.utc_now_z(),
        "party": _clean(party, limit=32),
        "document_url": _clean(document_url, limit=2000),
        "schedule": schedule,
        "tbc_category": _clean(tbc_category, limit=64) or None,
    }
    return _insert_once(row, db_path)


def settle_tbc_item(
    item_id: str, category: str, *, quantity: Decimal | int | str = 1, db_path: str | Path | None = None
) -> bool:
    quantity_dec = Decimal(str(quantity))
    if category not in CATEGORY_RATES:
        raise BillingItemError(f"unknown billing category {category!r}; expected one of {sorted(CATEGORY_RATES)}")
    if CATEGORY_RATES[category][1]:
        raise BillingItemError("a TBC row is settled with a per-item or per-page category, not an hourly one")
    item = _clean(item_id, limit=64)
    with billing_store.connect(db_path) as conn:
        found = conn.execute(
            "SELECT matter_id FROM matter_billing_items WHERE item_id = ? AND category = ?", (item, TBC_CATEGORY)
        ).fetchone()
        if not found:
            return False
        rate = rate_for(category, matter_basis(str(found[0]), db_path=db_path), db_path=db_path)
        if rate is None:
            raise BillingItemError(f"the private rate for {CATEGORY_LABELS[category]} is still TBC")
        net = compute_net_amount(category, quantity=quantity_dec, minutes=0, rate=rate)
        cursor = conn.execute(
            "UPDATE matter_billing_items SET category = ?, quantity = ?, rate = ?, net_amount = ?, vat_amount = ?, "
            "tbc_category = NULL WHERE item_id = ? AND category = ?",
            (category, str(quantity_dec), str(rate), _money(net), _money(net * rates.VAT_RATE), item, TBC_CATEGORY),
        )
        return bool(cursor.rowcount)


REMOVAL_COLUMNS = ("removed_utc", "removed_by", "restored_utc", "restored_by")


def list_removed_items(matter_id: str, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    matter = _clean(matter_id, limit=128)
    if not matter:
        return []
    columns = (*ITEM_COLUMNS, *REMOVAL_COLUMNS)
    with billing_store.connect(db_path) as conn:
        conn.row_factory = None
        rows = conn.execute(
            f"SELECT {', '.join(columns)} FROM matter_billing_items "
            "WHERE matter_id = ? AND removed_utc IS NOT NULL ORDER BY removed_utc DESC",
            (matter,),
        ).fetchall()
    return [dict(zip(columns, row)) for row in rows]


def list_frequent_callers(*, days: int = 7, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
    with billing_store.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT matter_id, MAX(client_name) AS client_name, COUNT(*) AS an_count "
            "FROM matter_billing_items "
            "WHERE category LIKE 'attendance%' AND created_at >= ? "
            "GROUP BY matter_id ORDER BY an_count DESC",
            (cutoff,),
        ).fetchall()
    return [billing_store.as_dict(row, ("matter_id", "client_name", "an_count")) for row in rows]


def item_id_for_work(matter_id: str, work_id: str, category: str, *, db_path: str | Path | None = None) -> str | None:
    matter = _clean(matter_id, limit=128)
    key = _clean(work_id, limit=64)
    if not matter or not key:
        return None
    with billing_store.connect(db_path) as conn:
        row = conn.execute(
            "SELECT item_id FROM matter_billing_items WHERE matter_id = ? AND work_id = ? "
            "AND (category = ? OR tbc_category = ?)",
            (matter, key, category, category),
        ).fetchone()
    return str(row[0]) if row else None


def record_correspondence_item(
    *,
    matter_id: str,
    item_date: str,
    direction: str,
    party: str,
    dedupe_key: str,
    client_name: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    if direction not in ("out", "in"):
        raise BillingItemError(f"direction must be 'out' or 'in', got {direction!r}")
    key = _clean(dedupe_key, limit=64)
    if not key:
        raise BillingItemError("dedupe_key is required")
    category = "routine_letter_out" if direction == "out" else "routine_letter_in"
    matter = _clean(matter_id, limit=128)
    if item_id_for_work(matter, key, category, db_path=db_path):
        return None
    label = party_labels().get(party, "Others")
    row = record_item(
        matter_id=matter,
        item_date=item_date,
        category=category,
        description=f"{CATEGORY_LABELS[category]} {'to' if direction == 'out' else 'from'} {label}",
        work_id=key,
        client_name=client_name,
        party=party,
        db_path=db_path,
    )
    return None if row.get("already_recorded") else row


def link_items(first_id: str, second_id: str, *, db_path: str | Path | None = None) -> bool:
    a, b = _clean(first_id, limit=64), _clean(second_id, limit=64)
    if not a or not b or a == b:
        return False
    with billing_store.connect(db_path) as conn:
        found = conn.execute("SELECT COUNT(*) FROM matter_billing_items WHERE item_id IN (?, ?)", (a, b)).fetchone()[0]
        if found != 2:
            return False
        conn.execute("UPDATE matter_billing_items SET linked_item_id = ? WHERE item_id = ?", (b, a))
        conn.execute("UPDATE matter_billing_items SET linked_item_id = ? WHERE item_id = ?", (a, b))
    return True


def linked_item_id(item_id: str, *, db_path: str | Path | None = None) -> str:
    with billing_store.connect(db_path) as conn:
        row = conn.execute("SELECT linked_item_id FROM matter_billing_items WHERE item_id = ?", (_clean(item_id, limit=64),)).fetchone()
    return str(row[0] or "") if row else ""


def set_document_url(item_id: str, url: str, *, db_path: str | Path | None = None) -> bool:
    with billing_store.connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE matter_billing_items SET document_url = ? WHERE item_id = ?",
            (_clean(url, limit=2000), item_id),
        )
        conn.commit()
        return cur.rowcount > 0


def get_item(item_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    identifier = _clean(item_id, limit=64)
    if not identifier:
        return None
    columns = (*ITEM_COLUMNS, *REMOVAL_COLUMNS)
    with billing_store.connect(db_path) as conn:
        conn.row_factory = None
        row = conn.execute(
            f"SELECT {', '.join(columns)} FROM matter_billing_items WHERE item_id = ?", (identifier,)
        ).fetchone()
    return dict(zip(columns, row)) if row else None


def remove_item(item_id: str, *, by: str = "", db_path: str | Path | None = None) -> bool:
    identifier = _clean(item_id, limit=64)
    if not identifier:
        return False
    with billing_store.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE matter_billing_items SET removed_by = CASE WHEN removed_utc IS NULL THEN ? ELSE removed_by END, "
            "removed_utc = COALESCE(removed_utc, ?) WHERE item_id = ?",
            (_clean(by, limit=200), ops_db.utc_now_z(), identifier),
        )
        return bool(cursor.rowcount)


def restore_item(item_id: str, *, by: str = "", db_path: str | Path | None = None) -> bool:
    identifier = _clean(item_id, limit=64)
    if not identifier:
        return False
    with billing_store.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE matter_billing_items SET removed_utc = NULL, removed_by = NULL, restored_utc = ?, restored_by = ? "
            "WHERE item_id = ? AND removed_utc IS NOT NULL",
            (ops_db.utc_now_z(), _clean(by, limit=200), identifier),
        )
        return bool(cursor.rowcount)


def grouped_by_category(matter_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    items = list_items(matter_id, db_path=db_path)
    by_category: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_category.setdefault(item["category"], []).append(item)

    categories: list[dict[str, Any]] = []
    grand_net = Decimal("0")
    grand_vat = Decimal("0")
    for category in CATEGORY_RATES:
        rows = by_category.get(category, [])
        if not rows:
            continue
        cat_net = sum((Decimal(row["net_amount"]) for row in rows), Decimal("0"))
        cat_vat = sum((Decimal(row["vat_amount"]) for row in rows), Decimal("0"))
        categories.append(
            {
                "category": category,
                "label": CATEGORY_LABELS[category],
                "items": rows,
                "subtotal_net": _money(cat_net),
                "subtotal_vat": _money(cat_vat),
            }
        )
        grand_net += cat_net
        grand_vat += cat_vat

    return {
        "categories": categories,
        "total_net": _money(grand_net),
        "total_vat": _money(grand_vat),
        "total_gross": _money(grand_net + grand_vat),
    }


def generate_itemized_bill_csv(matter_id: str, client_name: str, *, db_path: str | Path | None = None) -> str:
    import io

    grouped = grouped_by_category(matter_id, db_path=db_path)
    out_rows: list[list[str]] = [
        [_clean(client_name).upper(), "Date", "Description", "Net (£)", "VAT (£)"],
        ["", "", "", "", ""],
    ]
    for cat in grouped["categories"]:
        out_rows.append([cat["label"], "", "", "", ""])
        for item in cat["items"]:
            out_rows.append(["", item["item_date"], item["description"], item["net_amount"], item["vat_amount"]])
        out_rows.append(["", "", "Subtotal", cat["subtotal_net"], cat["subtotal_vat"]])
        out_rows.append(["", "", "", "", ""])
    out_rows.append(["TOTAL", "", "", grouped["total_net"], grouped["total_vat"]])

    buf = io.StringIO()
    csv_safe.writer(buf, lineterminator="\r\n").writerows(out_rows)
    return "﻿" + buf.getvalue()


BILLABLE_ACTIONS_COLUMNS = (
    "record_id", "client_name", "case_ref", "matter_type", "action_date",
    "source_group", "source_file", "source_datetime", "direction", "party",
    "action_type", "description", "minutes", "units", "unit_basis",
    "rate_regime", "rate_code", "unit_rate_gbp", "net_amount_gbp", "vat_rate",
    "vat_amount_gbp", "gross_amount_gbp", "fee_earner", "hearing_date",
    "status", "checked_by", "checked_on", "validation_notes",
)


def _billable_actions_row(item: dict[str, Any]) -> dict[str, str]:
    net = Decimal(item["net_amount"])
    vat = Decimal(item["vat_amount"])
    is_hourly = CATEGORY_RATES[item["category"]][1]
    hourly_rate = Decimal(item["rate"])
    if is_hourly:
        units = str(item["minutes"])
        unit_rate = _money(hourly_rate / Decimal(60))
    else:
        units = item["quantity"]
        unit_rate = item["rate"]
    return {
        "record_id": item["item_id"],
        "client_name": item.get("client_name") or "",
        "case_ref": item.get("case_ref") or "",
        "matter_type": "",
        "action_date": item["item_date"],
        "source_group": "",
        "source_file": item.get("source_file") or "",
        "source_datetime": item["created_at"],
        "direction": "",
        "party": item.get("party") or "",
        "action_type": CATEGORY_LABELS[item["category"]],
        "description": item["description"],
        "minutes": str(item["minutes"]) if is_hourly else "",
        "units": units,
        "unit_basis": "minutes" if is_hourly else "units",
        "rate_regime": "",
        "rate_code": "",
        "unit_rate_gbp": unit_rate,
        "net_amount_gbp": item["net_amount"],
        "vat_rate": str(rates.VAT_RATE),
        "vat_amount_gbp": item["vat_amount"],
        "gross_amount_gbp": _money(net + vat),
        "fee_earner": "",
        "hearing_date": "",
        "status": "unreviewed",
        "checked_by": "",
        "checked_on": "",
        "validation_notes": "",
    }


def generate_billable_actions_csv(matter_id: str, *, db_path: str | Path | None = None) -> str:
    import io

    items = list_items(matter_id, db_path=db_path)
    buf = io.StringIO()
    writer = csv_safe.dict_writer(buf, BILLABLE_ACTIONS_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for item in items:
        writer.writerow(_billable_actions_row(item))
    return buf.getvalue()
