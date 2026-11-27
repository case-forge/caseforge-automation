#!/usr/bin/env python3

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import order_codes

CANONICAL_ORDER_TYPES: tuple[str, ...] = ("NMO", "OO", "CAO", "PSO", "SIO")
CONCEPT = "order-text"

ROWS, TAGS, TEXT, NONE = "rows", "tags", "text", "none"


def canonical(codes: Iterable[Any] | str | None) -> tuple[str, ...]:
    if codes is None:
        return ()
    items = codes.split(",") if isinstance(codes, str) else codes
    found = {str(c or "").strip().upper() for c in items}
    return tuple(code for code in CANONICAL_ORDER_TYPES if code in found)


REASON_MARKER = "Order check"
LEGACY_REASON_MARKER = "order-text"
PLAIN: dict[str, str] = {
    "missing": "order wording missing",
    "not_understood": "order wording not understood",
    "only_form": "order wording names only the C100 form, not an order",
    "differ": "model and rules differ (model used)",
    "model_down": "model unavailable (rules used)",
    "rules_blind": "rules did not understand the wording (model used)",
    "existing_differs": "recorded orders differ from what the readers give (nothing changed)",
    "mirror": "order tags and order rows differ",
    "defaulted_nmo_blank": "the referral's order field was blank when read and older software recorded NMO; confirm against the referral",
    "defaulted_nmo_unconfirmed": "recorded as NMO but the referral's order field could not be checked here (older software assumed NMO when blank); confirm against the referral",
    "mirror_repaired": "order tags and rows differed; both now follow the model-preferred reading",
}


def has_order_reason(text: object) -> bool:
    s = str(text or "")
    return REASON_MARKER in s or LEGACY_REASON_MARKER in s


def plain_reason(kind: str, *, model: Iterable[str] = (), rules: Iterable[str] = (), wording: str = "", note: str = "") -> str:
    parts = []
    if tuple(model):
        parts.append(f"model: {', '.join(model)}")
    if tuple(rules):
        parts.append(f"rules: {', '.join(rules)}")
    text = f"{REASON_MARKER} - {PLAIN[kind]}"
    if parts:
        text += f" [{'; '.join(parts)}]"
    if note:
        text += f" ({note})"
    wording = " ".join(str(wording or "").split())[:80]
    if wording:
        text += f" - wording '{wording}'"
    return text


@dataclass(frozen=True)
class MatterOrders:
    codes: tuple[str, ...] = ()
    source: str = NONE
    text: str = ""
    needs_review: bool = False
    review_reason: str = ""
    reading: order_codes.OrderResult = order_codes.OrderResult(empty=True)

    @property
    def empty(self) -> bool:
        return self.source in (TEXT, NONE) and self.reading.empty

    @property
    def unrecognised(self) -> tuple[str, ...]:
        return self.reading.unrecognised

    @property
    def fl401_form(self) -> bool:
        return self.reading.fl401_form

    @property
    def children_form(self) -> bool:
        return self.reading.children_form and not self.codes

    @property
    def structured(self) -> bool:
        return self.source in (ROWS, TAGS)


def resolve_orders(text: object = None, tags: Iterable[Any] | str | None = None, rows: Iterable[Any] | None = None) -> MatterOrders:
    wording = "" if text is None else str(text)
    reading = order_codes.resolve_order_text(wording)
    row_codes, tag_codes = canonical(rows), canonical(tags)
    structured, source = (row_codes, ROWS) if row_codes else (tag_codes, TAGS) if tag_codes else ((), NONE)
    if not structured:
        reason = ""
        if reading.needs_human:
            kind = "missing" if reading.empty else "only_form" if (reading.children_form and not reading.unrecognised) else "not_understood"
            reason = plain_reason(kind)
        return MatterOrders(reading.codes, TEXT if (reading.codes or not reading.empty) else NONE, wording, bool(reason), reason, reading)
    reason = ""
    if row_codes and tag_codes and set(row_codes) != set(tag_codes):
        reason = plain_reason("mirror", note=f"tags: {', '.join(tag_codes)}; rows: {', '.join(row_codes)}")
    elif reading.codes and not reading.unrecognised and tuple(sorted(reading.codes)) != tuple(sorted(structured)):
        reason = plain_reason("differ", model=structured, rules=canonical(reading.codes))
    return MatterOrders(structured, source, wording, bool(reason), reason, reading)


def _in_clause(ids: list[int]) -> str:
    return ",".join("?" for _ in ids)


def load_structured(matter_id: Any) -> tuple[str, tuple[str, ...]]:
    import clientdb_sql

    if not str(matter_id or "").strip().isdigit():
        return "", ()
    mid = int(str(matter_id))
    try:
        with clientdb_sql.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT order_type_tags FROM matters WHERE matter_id = ?", (mid,))
            row = cur.fetchone()
            cur.execute("SELECT order_type_code FROM matter_order_types WHERE matter_id = ?", (mid,))
            codes = tuple(str(r[0] or "") for r in cur.fetchall())
    except Exception:
        return "", ()
    return str((row[0] if row else "") or ""), codes


def resolve_many(matter_ids: Iterable[Any]) -> dict[str, MatterOrders]:
    import clientdb_sql

    ids = sorted({int(str(m)) for m in matter_ids if str(m or "").strip().isdigit()})
    if not ids:
        return {}
    marks = _in_clause(ids)
    wording: dict[str, tuple[str, str]] = {}
    rows: dict[str, list[str]] = {}
    with clientdb_sql.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT matter_id, order_requested_text, order_type_tags FROM matters WHERE matter_id IN ({marks})", tuple(ids))
        for mid, text, tags in cur.fetchall():
            wording[str(mid)] = (str(text or ""), str(tags or ""))
        cur.execute(f"SELECT matter_id, order_type_code FROM matter_order_types WHERE matter_id IN ({marks})", tuple(ids))
        for mid, code in cur.fetchall():
            rows.setdefault(str(mid), []).append(str(code or ""))
    return {mid: resolve_orders(text, tags, rows.get(mid)) for mid, (text, tags) in wording.items()}


def resolve_matter_orders(matter_id: Any) -> MatterOrders:
    return resolve_many([matter_id]).get(str(matter_id).strip(), MatterOrders())


def resolve_row(row: Mapping[str, Any], *, load_rows: bool = False) -> MatterOrders:
    text = row.get("order_requested_text") or row.get("order_type") or row.get("matter") or row.get("orders")
    tags = row.get("order_type_tags")
    rows = row.get("order_codes") or row.get("order_type_codes")
    if load_rows and not rows and str(row.get("matter_id") or "").strip().isdigit():
        stored_tags, rows = load_structured(row.get("matter_id"))
        tags = tags or stored_tags
    return resolve_orders(text, tags, rows)
