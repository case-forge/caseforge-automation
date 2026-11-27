#!/usr/bin/env python3
"Normalise name and address columns across people, matter_parties,"
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import psycopg2
import psycopg2.extras

from sql.client_details_lint import (
    PLACEHOLDER_RE,
    POSTCODE_RE,
    ROLE_ARTEFACT_RE,
    THIRD_PARTY_RE,
)
from documents.address_utils import (
    LOW_VALUE_ADDRESS_PARTS,
    _UK_ANYWHERE_RE,
    clean_address_lines,
    split_address_parts,
    strip_uk_label,
    strip_uk_suffix,
)

LONG_NAME_WORDS = 5
FULLY_BRACKETED_RE = re.compile(r"^\[.*\]$")

ORG_RE = re.compile(
    r"\b(council|borough|royal|nhs|trust|authority|ltd|limited|llp|plc|"
    r"services|department|county|city of|police|constabulary|social care|"
    r"children.s services)\b",
    re.IGNORECASE,
)


def classify_name(name: str) -> tuple[str, str, str] | None:
    "Return (first, middle, last) or None if the name is ambiguous."
    if not name or not name.strip():
        return None
    name = name.strip()
    if PLACEHOLDER_RE.search(name) or FULLY_BRACKETED_RE.match(name):
        return None
    if ORG_RE.search(name):
        return None
    if ROLE_ARTEFACT_RE.search(name) or "(" in name:
        return None
    if "," in name:
        return None
    words = [w for w in re.split(r"\s+", name) if w]
    if len(words) == 1 or len(words) >= LONG_NAME_WORDS:
        return None
    if name.isupper() and re.search(r"[A-Z]{2}", name):
        return None
    if words[0].lower() in SURNAME_PARTICLES:
        return None
    last_at = len(words) - 1
    while last_at - 1 >= 1 and words[last_at - 1].lower() in SURNAME_PARTICLES:
        last_at -= 1
    first = words[0]
    last = " ".join(words[last_at:])
    middle = " ".join(words[1:last_at])
    return first, middle, last


SURNAME_PARTICLES = frozenset({
    "van", "von", "der", "den", "de", "del", "della", "di", "da", "dos", "du",
    "la", "le", "al", "el", "bin", "ibn", "bint", "ben", "ter", "ten", "st", "st.",
})

def classify_address(address: str) -> dict | None:
    "Return dict of line1-4/postcode, or None if ambiguous (flag instead)."
    if not address or not address.strip():
        return None
    text = address.strip()
    if PLACEHOLDER_RE.search(text) or FULLY_BRACKETED_RE.match(text):
        return None
    if THIRD_PARTY_RE.search(text):
        return None
    matches = list(POSTCODE_RE.finditer(text))
    if len(matches) > 1:
        return None

    postcode = ""
    body = text
    if matches:
        m = matches[0]
        postcode = re.sub(r"\s+", " ", m.group(0).strip()).upper()
        body = (text[: m.start()] + " " + text[m.end():]).strip()

    parts = split_address_parts([body]) if body else []
    parts = [p for p in parts if p.strip().lower().strip(".") not in LOW_VALUE_ADDRESS_PARTS]
    for index in (0, 1):
        if index + 1 < len(parts) and re.fullmatch(r"\d+[A-Za-z]?(?:[-/]\d+[A-Za-z]?)?", parts[index].strip()):
            parts[index : index + 2] = [f"{parts[index].strip()} {parts[index + 1].strip()}"]
    if len(parts) > 4:
        parts = parts[:3] + [", ".join(parts[3:])]
    result = {"address_line1": "", "address_line2": "", "address_line3": "", "address_line4": ""}
    for i, p in enumerate(parts):
        result[f"address_line{i + 1}"] = p
    result["address_postcode"] = postcode
    if not any(result.values()):
        return None
    return result


ADDRESS_LINE_COLS = ["address_line1", "address_line2", "address_line3", "address_line4"]
ADDRESS_COLS = ["address_text", *ADDRESS_LINE_COLS, "address_postcode"]
NAME_PART_COLS = ["name_first", "name_middle", "name_last"]

TABLES = {
    "people": {
        "id_col": "person_id",
        "name_col": "canonical_name",
        "has_address": True,
    },
    "matter_parties": {
        "id_col": "matter_party_id",
        "name_col": "display_name",
        "has_address": True,
    },
    "matter_children": {
        "id_col": "child_id",
        "name_col": "child_name",
        "has_address": False,
    },
}

LOG_TABLE = "clientdb_normalise_log"
LOG_MIGRATION = Path(__file__).resolve().parent / "migrations" / "0027_clientdb_normalise_log.sql"
SAMPLE_IDS = 5


def _columns(cfg: dict) -> list[str]:
    cols = [cfg["id_col"], cfg["name_col"], *NAME_PART_COLS]
    if cfg["has_address"]:
        cols += ADDRESS_COLS
    return cols


def plan_row(cfg: dict, row: dict) -> tuple[dict, list[tuple[str, str]], list[str]]:
    "Decide what to change on one row, without touching the database."
    updates: dict[str, str] = {}
    findings: list[tuple[str, str]] = []
    rules: list[str] = []

    name = row.get(cfg["name_col"])
    if not (row.get("name_first") or row.get("name_last")) and name and name.strip():
        parsed = classify_name(name)
        if parsed:
            updates["name_first"], updates["name_middle"], updates["name_last"] = parsed
            rules.append("name_split")
        else:
            findings.append(("name", "ambiguous"))

    if cfg["has_address"]:
        text = row.get("address_text") or ""
        stripped = strip_uk_label(text) if text.strip() else text
        if stripped != text:
            if stripped.strip():
                updates["address_text"] = stripped
                rules.append("uk_text")
            else:
                findings.append(("address", "uk_only"))
                stripped = text

        lines = [row.get(c) or "" for c in ADDRESS_LINE_COLS]
        if any(_UK_ANYWHERE_RE.search(line) for line in lines):
            cleaned = clean_address_lines(lines)
            if cleaned is None:
                findings.append(("address_lines", "uk_mid_line"))
            else:
                padded = (cleaned + [""] * 4)[:4]
                if padded != [line.strip() for line in lines]:
                    updates.update(dict(zip(ADDRESS_LINE_COLS, padded)))
                    rules.append("uk_lines")

        already_split = bool(row.get("address_line1")) or bool(row.get("address_postcode"))
        if not already_split and stripped.strip():
            parsed_addr = classify_address(stripped)
            if parsed_addr:
                updates.update(parsed_addr)
                rules.append("addr_split")
            else:
                findings.append(("address", "ambiguous"))

    return updates, findings, rules


def _ensure_log_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(LOG_MIGRATION.read_text(encoding="utf-8"))


def _log_and_update(conn, table: str, cfg: dict, row: dict, updates: dict, run_tag: str) -> None:
    id_col, rid = cfg["id_col"], row[cfg["id_col"]]
    with conn.cursor() as cur:
        for col, new in updates.items():
            old = row.get(col)
            cur.execute(
                f"INSERT INTO {LOG_TABLE} (run_tag, table_name, pk_column, pk_value, column_name, old_value, new_value) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (run_tag, table, id_col, str(rid), col, old, new),
            )
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        cur.execute(f"UPDATE {table} SET {set_clause} WHERE {id_col} = %s", [*updates.values(), rid])


def process_table(conn, table: str, apply: bool, report: list[dict], run_tag: str = "") -> dict:
    cfg = TABLES[table]
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"SELECT {', '.join(_columns(cfg))} FROM {table}")
    rows = cur.fetchall()

    stats = {"total": len(rows), "name_split": 0, "name_skipped": 0,
             "addr_split": 0, "addr_skipped": 0, "uk_text": 0, "uk_lines": 0,
             "uk_skipped": 0, "rows_changed": 0}
    samples: dict[str, list] = {}

    for row in rows:
        rid = row[cfg["id_col"]]
        updates, findings, rules = plan_row(cfg, row)

        for rule in rules:
            stats[rule] += 1
            samples.setdefault(rule, [])
            if len(samples[rule]) < SAMPLE_IDS:
                samples[rule].append(rid)
        for field, reason in findings:
            key = {"name": "name_skipped", "address": "addr_skipped"}.get(field, "uk_skipped")
            if reason in ("uk_only", "uk_mid_line"):
                key = "uk_skipped"
            stats[key] += 1
            report.append({"table": table, "id": rid, "field": field, "reason": reason})

        if updates:
            stats["rows_changed"] += 1
            if apply:
                _log_and_update(conn, table, cfg, row, updates, run_tag)

    stats["sample_ids"] = samples
    return stats


def revert_run(conn, run_tag: str, apply: bool) -> dict:
    "Restore the old values a run wrote. A column is only restored while it"
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        f"SELECT log_id, table_name, pk_column, pk_value, column_name, old_value, new_value "
        f"FROM {LOG_TABLE} WHERE run_tag = %s AND reverted_utc IS NULL ORDER BY log_id DESC",
        (run_tag,),
    )
    entries = cur.fetchall()
    out = {"run_tag": run_tag, "mode": "apply" if apply else "dry-run",
           "entries": len(entries), "restored": 0, "changed_since": 0}
    for e in entries:
        cfg = TABLES.get(e["table_name"])
        allowed = set(NAME_PART_COLS) | set(ADDRESS_COLS)
        if cfg is None or e["pk_column"] != cfg["id_col"] or e["column_name"] not in allowed:
            raise ValueError(f"refusing to revert unexpected log row {e['log_id']}")
        table, pk, col = e["table_name"], e["pk_column"], e["column_name"]
        cur.execute(f"SELECT {col} AS v FROM {table} WHERE {pk}::text = %s", (e["pk_value"],))
        current = cur.fetchone()
        if current is None or (current["v"] or None) != (e["new_value"] or None):
            out["changed_since"] += 1
            continue
        out["restored"] += 1
        if apply:
            cur.execute(f"UPDATE {table} SET {col} = %s WHERE {pk}::text = %s", (e["old_value"], e["pk_value"]))
            cur.execute(f"UPDATE {LOG_TABLE} SET reverted_utc = now() at time zone 'utc' WHERE log_id = %s", (e["log_id"],))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Commit writes (default: dry-run)")
    ap.add_argument("--report", default="", help="Path to write JSON list of skipped rows")
    ap.add_argument("--run-tag", default="", help="Label for this run in the change log (default: timestamp)")
    ap.add_argument("--revert", default="", metavar="RUN_TAG", help="Restore the old values a previous run wrote")
    args = ap.parse_args()

    dsn = os.environ.get("CASEFORGE_CLIENTDB_PG_URL")
    if not dsn:
        print("CASEFORGE_CLIENTDB_PG_URL not set", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(dsn, connect_timeout=15, application_name="caseforge:sql/split_name_address_fields.py")
    try:
        if args.revert:
            result = revert_run(conn, args.revert, args.apply)
            if args.apply:
                conn.commit()
            else:
                conn.rollback()
            print(json.dumps(result, indent=2))
            return

        run_tag = args.run_tag or "normalise-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report: list[dict] = []
        if args.apply:
            _ensure_log_table(conn)
        all_stats = {}
        for table in TABLES:
            all_stats[table] = process_table(conn, table, args.apply, report, run_tag)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()

    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "run_tag": run_tag, "stats": all_stats}, indent=2, default=str))
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2))
        print(f"skipped-row report written to {args.report} ({len(report)} rows)")


if __name__ == "__main__":
    main()
