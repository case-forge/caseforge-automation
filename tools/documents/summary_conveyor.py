#!/usr/bin/env python3
"summary_conveyor: render matter fact summaries from existing SQL surfaces."
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import child_age
import matter_orders
from field_shapes import known_value
from documents.order_text_case import normalise_order_text

TBC = "TBC"


C8_WITHHELD = "[C8 protected — withheld from this summary]"

C8_BANNER = (
    "> **C8 PROTECTED MATTER**\n"
    "> This matter has a C8 application. The applicant's protected contact\n"
    "> details (address, email, phone) are withheld from this summary and\n"
    "> must never be disclosed to the respondent or placed in\n"
    "> respondent-facing material."
)

_APPLICANT_ROLE_RE = re.compile(r"\bapplicant\b", re.IGNORECASE)


def _is_applicant_role(role: Any) -> bool:
    return bool(_APPLICANT_ROLE_RE.search(str(role or "")))




def _tbc(value: Any) -> str:
    text = known_value(value) if value is not None else ""
    return text if text else TBC


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _row_dicts(cur: Any) -> list[dict[str, Any]]:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _safe_rows(cur: Any, sql: str, params: tuple) -> list[dict[str, Any]]:
    "Query results, or [] if the surface is absent/unreadable."
    try:
        cur.execute(sql, params)
        return _row_dicts(cur)
    except Exception:
        return []




def facts(matter_id: str) -> dict[str, Any]:
    "Matter facts read from the existing SQL surfaces only."
    mid = str(matter_id or "").strip()
    if not mid:
        raise ValueError("matter_id is required.")

    from clientdb_sql import get_connection

    result: dict[str, Any] = {"matter_id": mid}

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT m.client_role, m.company_reference, m.has_c8,
                   m.order_requested_text, m.children_summary,
                   m.live_matter_folder, m.legal_aid_tracker_status,
                   m.relationship_start, m.relationship_end,
                   m.referral_sent_at, m.source_email_sent_at,
                   p.canonical_name AS client_name, p.dob_iso AS client_dob,
                   p.phone_primary AS client_phone, p.email_primary AS client_email
            FROM matters m
            LEFT JOIN people p ON p.person_id = m.primary_person_id
            WHERE m.matter_id = ?
            """,
            (mid,),
        )
        row = cur.fetchone()
        matter_row = dict(zip([c[0] for c in cur.description], row)) if row else {}

        has_c8 = _bool(matter_row.get("has_c8"))

        result["client_name"] = _tbc(matter_row.get("client_name"))
        result["client_role"] = _tbc(matter_row.get("client_role"))
        result["company_reference"] = _tbc(matter_row.get("company_reference"))
        result["has_c8"] = has_c8
        result["order_requested_text"] = _tbc(normalise_order_text(matter_row.get("order_requested_text")))
        result["children_summary"] = _tbc(child_age.with_live_ages(str(matter_row.get("children_summary") or "")))
        result["live_matter_folder"] = _tbc(matter_row.get("live_matter_folder"))
        result["legal_aid_tracker_status"] = _tbc(matter_row.get("legal_aid_tracker_status"))
        result["relationship_start"] = _tbc(matter_row.get("relationship_start"))
        result["relationship_end"] = _tbc(matter_row.get("relationship_end"))
        result["referral_sent_at"] = _tbc(matter_row.get("referral_sent_at"))
        result["source_email_sent_at"] = _tbc(matter_row.get("source_email_sent_at"))
        result["client_dob"] = _tbc(matter_row.get("client_dob"))

        result["client_phone"] = _tbc(matter_row.get("client_phone"))
        result["client_email"] = _tbc(matter_row.get("client_email"))

        try:
            from documents import court_of_record as cor

            court_row = cor.get_court(mid)
        except Exception:
            court_row = None
        result["court"] = _tbc(court_row.get("court")) if court_row else TBC

        party_rows = _safe_rows(
            cur,
            "SELECT role, display_name, dob_iso, address_text, phone_primary, "
            "phone_digits, email_primary FROM matter_parties WHERE matter_id = ?",
            (mid,),
        )
        result["parties"] = [
            {
                "role": _tbc(p.get("role")),
                "display_name": _tbc(p.get("display_name")),
                "dob_iso": _tbc(p.get("dob_iso")),
                "address_text": _tbc(p.get("address_text")),
                "phone_primary": _tbc(p.get("phone_primary")),
                "phone_digits": _tbc(p.get("phone_digits")),
                "email_primary": _tbc(p.get("email_primary")),
            }
            for p in party_rows
        ]

        order_rows = _safe_rows(
            cur, "SELECT order_type_code FROM matter_order_types WHERE matter_id = ?", (mid,)
        )
        stored_tags, _unused = matter_orders.load_structured(mid)
        result["order_type_codes"] = sorted(matter_orders.resolve_orders(
            matter_row.get("order_requested_text"),
            stored_tags,
            [_tbc(r.get("order_type_code")) for r in order_rows if _tbc(r.get("order_type_code")) != TBC],
        ).codes)

        child_rows = _safe_rows(
            cur,
            "SELECT child_name, dob_iso, gender, parental_responsibility, notes "
            "FROM matter_children WHERE matter_id = ? AND LOWER(COALESCE(child_name, '')) NOT LIKE 'unnamed child%'",
            (mid,),
        )
        result["children"] = [
            {
                "child_name": _tbc(c.get("child_name")),
                "dob_iso": _tbc(c.get("dob_iso")),
                "gender": _tbc(c.get("gender")),
                "parental_responsibility": _tbc(c.get("parental_responsibility")),
                "notes": _tbc(c.get("notes")),
            }
            for c in child_rows
        ]

        bank_rows = _safe_rows(
            cur,
            "SELECT account_name, account_number, sort_code, amount, notes "
            "FROM matter_bank_details WHERE matter_id = ?",
            (mid,),
        )
        result["bank_details"] = [
            {
                "account_name": _tbc(b.get("account_name")),
                "account_number": _tbc(b.get("account_number")),
                "sort_code": _tbc(b.get("sort_code")),
                "amount": _tbc(b.get("amount")),
                "notes": _tbc(b.get("notes")),
            }
            for b in bank_rows
        ]

        live_rows = _safe_rows(
            cur,
            "SELECT latest_live_status, order_status, sealed_order_status, service_status, "
            "next_hearing_text, awaiting_next_step, last_client_chase, "
            "last_material_email_received, last_material_email_subject, draft_order_status "
            "FROM matter_live_status WHERE matter_id = ?",
            (mid,),
        )
        live = live_rows[0] if live_rows else {}
        result["live_status"] = {k: _tbc(v) for k, v in live.items()} if live else {
            "latest_live_status": TBC,
            "order_status": TBC,
            "sealed_order_status": TBC,
            "service_status": TBC,
            "next_hearing_text": TBC,
            "awaiting_next_step": TBC,
            "last_client_chase": TBC,
            "last_material_email_received": TBC,
            "last_material_email_subject": TBC,
            "draft_order_status": TBC,
        }

        ref_rows = _safe_rows(
            cur,
            "SELECT ref_type, ref_value, source, is_primary FROM matter_references "
            "WHERE matter_id = ? AND ref_type <> 'court'",
            (mid,),
        )
        result["references"] = [
            {
                "ref_type": _tbc(r.get("ref_type")),
                "ref_value": _tbc(r.get("ref_value")),
                "source": _tbc(r.get("source")),
                "is_primary": _bool(r.get("is_primary")),
            }
            for r in ref_rows
        ]

        incident_rows = _safe_rows(
            cur,
            "SELECT incident_date, incident_type, summary, police_called, crime_reference, "
            "arrest_status, bail_status, confidence FROM matter_incidents WHERE matter_id = ?",
            (mid,),
        )
        result["incidents"] = [
            {
                "incident_date": _tbc(r.get("incident_date")),
                "incident_type": _tbc(r.get("incident_type")),
                "summary": _tbc(r.get("summary")),
                "police_called": _bool(r.get("police_called")),
                "crime_reference": _tbc(r.get("crime_reference")),
                "arrest_status": _tbc(r.get("arrest_status")),
                "bail_status": _tbc(r.get("bail_status")),
                "confidence": _tbc(r.get("confidence")),
            }
            for r in incident_rows
        ]

    return result



_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
_ISO_DATE_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})")
_MONTH_YEAR_RE = re.compile(r"^\s*([A-Za-z]+)\s+(\d{4})\s*$")


def _parse_dated(value: Any) -> tuple[dt.date, str] | None:
    "(sort_date, display_text) for a value that is already a date, or None."
    text = str(value or "").strip()
    if not text or text == TBC:
        return None
    m = _ISO_DATE_RE.match(text)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))), text
        except ValueError:
            return None
    m2 = _MONTH_YEAR_RE.match(text)
    if m2:
        month = _MONTHS.get(m2.group(1).lower())
        if month:
            try:
                return dt.date(int(m2.group(2)), month, 1), text
            except ValueError:
                return None
    return None


def chronology_entries(f: dict[str, Any]) -> list[dict[str, Any]]:
    "Dated, status-relevant entries drawn from ``facts()``, ascending."
    entries: list[dict[str, Any]] = []

    def add(value: Any, event: str, source: str) -> None:
        parsed = _parse_dated(value)
        if parsed is None:
            return
        sort_date, display = parsed
        entries.append({"sort_date": sort_date, "date": display, "event": event, "outcome": TBC, "source": source})

    add(
        f.get("source_email_sent_at") if f.get("source_email_sent_at") != TBC else f.get("referral_sent_at"),
        "Referral received",
        "matters.source_email_sent_at" if f.get("source_email_sent_at") != TBC else "matters.referral_sent_at",
    )
    live = f.get("live_status", {})
    add(live.get("last_client_chase"), "Last client chase", "matter_live_status.last_client_chase")
    subject = live.get("last_material_email_subject")
    email_event = "Last material email received"
    if subject and subject != TBC:
        email_event = f"Last material email received ({subject})"
    add(live.get("last_material_email_received"), email_event, "matter_live_status.last_material_email_received")

    entries.sort(key=lambda e: (e["sort_date"], e["event"]))
    return entries




def _c8_banner(f: dict[str, Any]) -> str:
    return C8_BANNER + "\n\n" if f.get("has_c8") else ""


def _redact_for_disclosure(f: dict[str, Any]) -> dict[str, Any]:
    "Copy of *f* with the C8-protected applicant's contact fields (address,"
    if not f.get("has_c8"):
        return f
    redacted = dict(f)
    if _is_applicant_role(f.get("client_role")):
        if redacted.get("client_phone", TBC) != TBC:
            redacted["client_phone"] = C8_WITHHELD
        if redacted.get("client_email", TBC) != TBC:
            redacted["client_email"] = C8_WITHHELD
    redacted["parties"] = [_redact_party(p) for p in (f.get("parties") or [])]
    return redacted


def _redact_party(p: dict[str, Any]) -> dict[str, Any]:
    if not _is_applicant_role(p.get("role")):
        return p
    redacted = dict(p)
    for key in ("address_text", "phone_primary", "phone_digits", "email_primary"):
        if redacted.get(key, TBC) != TBC:
            redacted[key] = C8_WITHHELD
    return redacted


def _line(label: str, value: Any) -> str:
    return f"- **{label}:** {value}"


def _parties_block(f: dict[str, Any]) -> str:
    parties = f.get("parties") or []
    if not parties:
        return f"- {TBC} — no matter_parties rows recorded."
    lines = []
    for p in parties:
        lines.append(
            f"- **{p['role']}** — {p['display_name']} "
            f"(DOB {p['dob_iso']}; address {p['address_text']}; "
            f"phone {p['phone_primary']}; email {p['email_primary']})"
        )
    return "\n".join(lines)


def _children_block(f: dict[str, Any]) -> str:
    children = f.get("children") or []
    if not children:
        return f"- {TBC} — no matter_children rows recorded (matters.children_summary: {f.get('children_summary')})."
    lines = []
    for c in children:
        lines.append(
            f"- {c['child_name']} (DOB {c['dob_iso']}; gender {c['gender']}; "
            f"parental responsibility {c['parental_responsibility']}; notes {c['notes']})"
        )
    return "\n".join(lines)


def _order_types_line(f: dict[str, Any]) -> str:
    codes = f.get("order_type_codes") or []
    return ", ".join(codes) if codes else TBC


def _latest_incident_line(f: dict[str, Any]) -> str:
    "Most recent dated ``matter_incidents`` row, plain description only --"
    dated = [i for i in (f.get("incidents") or []) if i["incident_date"] != TBC]
    if not dated:
        return f"{TBC} — no dated matter_incidents rows recorded"
    latest = max(dated, key=lambda i: i["incident_date"])
    text = f"{latest['incident_date']}: {latest['incident_type']}" if latest["incident_type"] != TBC else latest["incident_date"]
    if latest["crime_reference"] != TBC:
        text += f" (ref {latest['crime_reference']})"
    return text


def _police_bail_crime_line(f: dict[str, Any]) -> str:
    bits = []
    for i in f.get("incidents") or []:
        entry = [part for part in (
            f"ref {i['crime_reference']}" if i["crime_reference"] != TBC else "",
            i["arrest_status"] if i["arrest_status"] != TBC else "",
            f"bail: {i['bail_status']}" if i["bail_status"] != TBC else "",
        ) if part]
        if entry:
            bits.append("; ".join(entry))
    return "; ".join(bits) if bits else TBC




def render_snapshot(f: dict[str, Any]) -> str:
    live = f.get("live_status", {})
    parts = [
        f"# Case Snapshot — {f['client_name']} (matter {f['matter_id']})",
        "",
        _c8_banner(f).rstrip(),
        "",
        _line("Role", f["client_role"]),
        _line("CaseForge reference", f["company_reference"]),
        _line("Court", f["court"]),
        _line("Order sought", f"{f['order_requested_text']} ({_order_types_line(f)})"),
        _line("Current position", live.get("latest_live_status", TBC)),
        _line("Next hearing / deadline", live.get("next_hearing_text", TBC)),
        _line("Outstanding", live.get("awaiting_next_step", TBC)),
        _line("Children", f["children_summary"]),
        _line("Legal aid", f["legal_aid_tracker_status"]),
        "",
        "## Parties",
        _parties_block(f),
        "",
        "## Source map",
        "- matters, matter_parties, matter_references, matter_order_types, "
        "matter_children, matter_live_status, matter_bank_details (SQL only — "
        "this snapshot does not read live documents).",
    ]
    return "\n".join(p for p in parts if p is not None).strip() + "\n"


def render_chronology(f: dict[str, Any]) -> str:
    f = _redact_for_disclosure(f)
    entries = chronology_entries(f)
    lines = [
        f"# Chronology — {f['client_name']} (matter {f['matter_id']})",
        "",
        _c8_banner(f).rstrip(),
        "",
        "| Date | Event | Outcome | Source |",
        "| --- | --- | --- | --- |",
    ]
    if entries:
        for e in entries:
            lines.append(f"| {e['date']} | {e['event']} | {e['outcome']} | {e['source']} |")
    else:
        lines.append(f"| {TBC} | No dated SQL facts recorded yet | {TBC} | — |")
    lines += [
        "",
        "Thin is correct: this chronology lists only dated facts already "
        "recorded in the SQL surfaces above. A short or empty table means no "
        "further dated SQL facts are recorded yet, not that nothing happened "
        "— check the live matter documents for the full picture.",
    ]
    return "\n".join(p for p in lines if p is not None).strip() + "\n"


def render_brief(f: dict[str, Any]) -> str:
    live = f.get("live_status", {})
    parts = [
        f"# Brief To Counsel — {f['client_name']} (matter {f['matter_id']})",
        "",
        _c8_banner(f).rstrip(),
        "",
        "## Posture",
        _line("Current position", live.get("latest_live_status", TBC)),
        _line("Order status", live.get("order_status", TBC)),
        _line("Sealed order status", live.get("sealed_order_status", TBC)),
        _line("Service status", live.get("service_status", TBC)),
        "",
        "## Hearing",
        _line("Next hearing / deadline", live.get("next_hearing_text", TBC)),
        _line("Court", f["court"]),
        "",
        "## Client and representation",
        _line("Client", f["client_name"]),
        _line("Role", f["client_role"]),
        _line("Public funding (legal aid tracker)", f["legal_aid_tracker_status"]),
        _line("Respondent representation", TBC),
        "",
        "## Order sought",
        _line("Order requested", f["order_requested_text"]),
        _line("Order type codes", _order_types_line(f)),
        "",
        "## Compressed facts",
        _line("Latest incident", _latest_incident_line(f)),
        _line(
            "Pattern of alleged harm",
            f"{TBC} — matter_abuse_themes is declined (owner decision 2026-07-31); "
            "no abuse-type coding is produced by this tool",
        ),
        "",
        "### Children and safeguarding",
        _children_block(f),
        "",
        _line("Police / bail / crime references", _police_bail_crime_line(f)),
        "",
        "## What counsel is asked to cover",
        f"- {TBC}",
    ]
    return "\n".join(p for p in parts if p is not None).strip() + "\n"


def render_bundle_summary(f: dict[str, Any]) -> str:
    f = _redact_for_disclosure(f)
    parts = [
        f"# Case Summary — {f['client_name']}",
        "",
        _c8_banner(f).rstrip(),
        "",
        "## Case Header",
        _line("CaseForge reference", f["company_reference"]),
        _line("Court", f["court"]),
        "",
        "## Applications and Orders",
        _line("Order requested", f["order_requested_text"]),
        _line("Order type codes", _order_types_line(f)),
        "",
        "## Parties",
        _parties_block(f),
        "",
        "## Children",
        _children_block(f),
        "",
        "## Current Procedural Position",
        _line("Position", f.get("live_status", {}).get("latest_live_status", TBC)),
        _line("Service status", f.get("live_status", {}).get("service_status", TBC)),
        "",
        "## Hearing Purpose",
        _line("Next hearing / deadline", f.get("live_status", {}).get("next_hearing_text", TBC)),
        "",
        "## Factual Summary",
        "See the accompanying chronology for the dated record; this summary "
        "does not repeat every dated event.",
    ]
    return "\n".join(p for p in parts if p is not None).strip() + "\n"


def closing(f: dict[str, Any]) -> str:
    "Draft-only closing-letter-shaped output. NOT wired to anything."
    parts = [
        f"# DRAFT — Closing Summary — {f['client_name']} (matter {f['matter_id']})",
        "",
        "> **DRAFT ONLY — closure policy not settled.**",
        "> This output is not finalised (see context/sql-summary-conveyor.md,",
        "> Output Variants -> Closing Letter). It is not wired to any task,",
        "> CLI default, or closing-letter workflow, and must not be used to",
        "> decide or communicate matter closure.",
        "",
        _c8_banner(f).rstrip(),
        "",
        _line("Order status", f.get("live_status", {}).get("order_status", TBC)),
        _line("Service status", f.get("live_status", {}).get("service_status", TBC)),
        _line("Legal aid tracker status", f["legal_aid_tracker_status"]),
        "",
        f"- {TBC} — final closure fields are not defined by this tool.",
    ]
    return "\n".join(p for p in parts if p is not None).strip() + "\n"


RENDERERS = {
    "snapshot": render_snapshot,
    "chronology": render_chronology,
    "brief": render_brief,
    "bundle-summary": render_bundle_summary,
}




def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("variant", choices=sorted(RENDERERS.keys()))
    ap.add_argument("--matter-id", required=True)
    ap.add_argument("--output", default="", help="write markdown here instead of stdout")
    args = ap.parse_args(argv)

    f = facts(args.matter_id)
    text = RENDERERS[args.variant](f)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
