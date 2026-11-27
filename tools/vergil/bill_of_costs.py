#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from billing import billing_items


def clean_text(value: Any) -> str:
    return str(value or "").strip()


_PARTY_LINES = (
    ("routine_letter_out", "Letters Out"),
    ("routine_letter_in", "Routine Letters In"),
    ("telephone", "Routine Calls"),
)


def party_summary(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from decimal import Decimal

    labels = billing_items.party_labels()
    summary: list[dict[str, Any]] = []
    for party, label in labels.items():
        lines: list[dict[str, Any]] = []
        for category, line_label in _PARTY_LINES:
            items = [
                item
                for cat in categories
                if cat["category"] == category
                for item in cat["items"]
                if clean_text(item.get("party")) == party
            ]
            if not items:
                continue
            net = sum((Decimal(i["net_amount"]) for i in items), Decimal("0"))
            vat = sum((Decimal(i["vat_amount"]) for i in items), Decimal("0"))
            lines.append(
                {
                    "label": line_label,
                    "count": int(sum(Decimal(str(i.get("quantity") or 1)) for i in items)),
                    "net": billing_items._money(net),
                    "vat": billing_items._money(vat),
                }
            )
        if lines:
            summary.append({"party": party, "label": label, "lines": lines})
    return summary


def _tag_attendance_drafts(categories: list[dict[str, Any]], db_path: str | None) -> None:
    ids = [item.get("item_id") for cat in categories for item in cat["items"] if item.get("item_id")]
    if not ids:
        return
    try:
        import ops_db

        marks = ",".join("?" for _ in ids)
        with ops_db.connect(db_path) as conn:
            rows = conn.execute(
                f"SELECT billing_item_id, draft_id FROM an_drafts WHERE billing_item_id IN ({marks})", ids
            ).fetchall()
    except Exception:
        return
    by_item = {str(r[0]): str(r[1]) for r in rows}
    for cat in categories:
        for item in cat["items"]:
            draft = by_item.get(str(item.get("item_id")))
            if draft:
                item["attendance_draft_id"] = draft


def _flag_possible_double_bills(categories: list[dict[str, Any]]) -> None:
    for cat in categories:
        seen: dict[str, int] = {}
        for item in cat["items"]:
            url = clean_text(item.get("document_url"))
            if url:
                seen[url] = seen.get(url, 0) + 1
        for item in cat["items"]:
            url = clean_text(item.get("document_url"))
            if url and seen.get(url, 0) > 1:
                item["possible_double_bill"] = True


def removed_items(matter: str, db_path: str | None) -> list[dict[str, Any]]:
    rows = billing_items.list_removed_items(matter, db_path=db_path)
    return [
        {
            "item_id": row["item_id"],
            "item_date": row["item_date"],
            "description": row["description"],
            "category_label": billing_items.CATEGORY_LABELS.get(row["category"], row["category"]),
            "net_amount": row["net_amount"],
            "vat_amount": row["vat_amount"],
            "removed_utc": row["removed_utc"],
            "removed_by": row.get("removed_by") or "",
        }
        for row in rows
    ]


def rate_tbc_lines(matter: str, db_path: str | None) -> list[dict[str, Any]]:
    return [
        {"item_id": row["item_id"], "item_date": row["item_date"], "description": row["description"]}
        for row in billing_items.list_rate_tbc_items(matter, db_path=db_path)
        if not row.get("removed_utc")
    ]


def bill_of_costs(matter_id: str, *, db_path: str | None = None) -> dict[str, Any]:
    matter = clean_text(matter_id)
    if not matter:
        return {
            "matter_id": matter,
            "client_name": "",
            "categories": [],
            "parties": [],
            "billing_basis": billing_items.BASIS_LEGAL_AID,
            "rates": billing_items.charging_rates(),
            "rate_tbc": [],
            "total_net": "0.00",
            "total_vat": "0.00",
            "total_gross": "0.00",
            "item_count": 0,
            "removed": [],
        }

    basis = billing_items.matter_basis(matter, db_path=db_path)
    grouped = billing_items.grouped_by_category(matter, db_path=db_path)
    _tag_attendance_drafts(grouped["categories"], db_path)
    _flag_possible_double_bills(grouped["categories"])
    client_name = ""
    item_count = 0
    for cat in grouped["categories"]:
        item_count += len(cat["items"])
        if not client_name:
            for item in cat["items"]:
                name = clean_text(item.get("client_name"))
                if name:
                    client_name = name
                    break

    return {
        "matter_id": matter,
        "client_name": client_name,
        "categories": grouped["categories"],
        "parties": party_summary(grouped["categories"]),
        "billing_basis": basis,
        "rates": billing_items.charging_rates(basis, db_path=db_path),
        "rate_tbc": rate_tbc_lines(matter, db_path),
        "total_net": grouped["total_net"],
        "total_vat": grouped["total_vat"],
        "total_gross": grouped["total_gross"],
        "item_count": item_count,
        "removed": removed_items(matter, db_path),
    }
