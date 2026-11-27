#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _default_client_db() -> Path | None:
    exact = REPO_ROOT / "clients" / "caseforge-clientdb.sqlite"
    if exact.is_file():
        return exact
    snapshots = sorted(
        (
            s for s in (REPO_ROOT / "clients").glob("caseforge-clientdb.sqlite.stale-*")
            if not s.name.endswith(("-wal", "-shm", "-journal"))
        ),
        key=lambda p: p.name,
        reverse=True,
    )
    if snapshots:
        return snapshots[0]
    partial = REPO_ROOT / "clients" / "caseforge-clientdb.partial.sqlite"
    return partial if partial.is_file() else None


def default_ops_db() -> Path | None:
    import sys

    tools_dir = str(REPO_ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from ops_db import configured_ops_db_path

    return configured_ops_db_path()


UNCONFIGURED_OPS_DB = Path("<CASEFORGE_OPS_DB not configured>")
DEFAULT_ARTIFACTS = REPO_ROOT / "artifacts"

RECENT_MATTER_WINDOW_DAYS = 30

MATTER_COLUMNS = [
    "client_role",
    "intake_source",
    "referral_source",
    "referral_sent_at",
    "source_email_sent_at",
    "review_reasons",
    "company_reference",
    "withheld_fields",
    "order_requested_text",
    "benefits_canonical",
    "children_summary",
    "property_summary",
    "live_matter_folder",
    "repo_client_folder",
    "legal_aid_tracker_status",
    "tracker_notes",
    "relationship_start",
    "relationship_end",
    "marriage_date",
    "divorce_date",
    "lived_together",
    "married",
    "bail_conditions",
    "bail_end_date",
    "crime_refs",
    "closed_at",
]
PEOPLE_COLUMNS = ["dob_iso", "phone_primary", "email_primary", "nino_canonical"]
PARTY_COLUMNS = ["dob_iso", "address_text", "phone_primary", "email_primary"]
CHILD_COLUMNS = ["child_name", "dob_iso", "gender", "parental_responsibility", "notes", "source"]
LIVE_STATUS_COLUMNS = [
    "latest_live_status",
    "order_status",
    "sealed_order_status",
    "service_status",
    "next_hearing_text",
    "awaiting_next_step",
    "last_client_chase",
    "last_material_email_received",
    "last_material_email_subject",
    "draft_order_status",
]
CLIENT_TELEMETRY_TABLES = [
    "runtime_activation_events",
    "startup_scorecards_summary",
    "graph_api_calls_daily",
    "client_search_events",
    "agent_output_feedback_events",
]
MATTER_TIMESTAMP_COLUMNS = ["created_utc", "updated_utc", "closed_at"]
PERMISSION_FLAG_COLUMNS = [
    "allow_email_print",
    "allow_sos_to_court_draft",
]
PLACEHOLDER_RE = re.compile(
    r"^\s*(?:"
    r"n/?a|unknown|\[unknown[^\]]*\]|\[check source file\]|"
    r"\[unknown - check correspondence\]|\[unknown - check laa/intake docs\]|"
    r"\[unknown - check service docs\]|tbc|-{3,}|withheld"
    r")\s*$",
    re.IGNORECASE,
)


def _firm_email_re() -> re.Pattern[str]:
    domains: set[str] = set()
    try:
        import firm_profile

        domains.update(d.strip().lower() for d in firm_profile.load_profile().firm_domains if d.strip())
        domains.update(firm_profile.misspelt_firm_domains())
    except Exception:
        pass
    if not domains:
        return re.compile(r"(?!)")
    return re.compile("@(?:" + "|".join(re.escape(d) for d in sorted(domains)) + ")$", re.IGNORECASE)


FIRM_EMAIL_RE = _firm_email_re()

LIVE_STATUS_CONTRACT = {
    "latest_live_status": "short text summary for the current operational position",
    "order_status": "short text such as application filed, granted, made final, or not granted",
    "sealed_order_status": "short text such as awaiting sealed order or sealed order received",
    "service_status": "short text describing service position",
    "next_hearing_text": "date or short hearing text extracted from recent material",
    "awaiting_next_step": "short text describing the next admin action needed",
    "last_client_chase": "UTC timestamp/string for the last client chase signal",
    "last_material_email_received": "UTC timestamp/string for the last material mailbox event",
    "last_material_email_subject": "subject text for the last material mailbox event",
    "draft_order_status": "short text describing draft order position",
    "waiting_for_sealed_order": "integer 0/1 derived flag",
}

CHILDREN_CONTRACT = {
    "child_name": "child full name as given in source material",
    "dob_iso": "ISO date where parseable, otherwise source date text",
    "gender": "child gender/sex where stated by source material",
    "parental_responsibility": "short text for PR position",
    "notes": "source notes or child detail that does not fit the split fields",
    "source": "source label for the parsed row",
}

SCHEMA_DECISIONS = [
    {
        "id": "clientdb.matter_folder_locations",
        "status": "retired",
        "surface": "client DB matter_folder_locations",
        "decision": "Retired from active folder lookup.",
        "audit_treatment": "Report row counts and comparisons only; do not raise a duplicate-folder finding.",
        "follow_up": "Keep for migration/debug review unless a separately approved export/drop workflow is run.",
    },
    {
        "id": "clientdb.matters.repo_client_folder",
        "status": "retired",
        "surface": "matters.repo_client_folder",
        "decision": "Retired local-folder cache.",
        "audit_treatment": "Report fill-rate only; do not raise a legacy-cache finding.",
        "follow_up": "Do not write new values; prefer matters.live_matter_folder plus ops OneDrive roots/index.",
    },
    {
        "id": "clientdb.billing_actions",
        "status": "retired",
        "surface": "billing_actions and billing_rate_sources",
        "decision": "Retired billing surfaces with known remaining rows.",
        "audit_treatment": "Report row counts only; do not raise a repeated active finding.",
        "follow_up": "Export/review first; dropping still requires destructive-action confirmation.",
    },
    {
        "id": "clientdb.matter_live_status",
        "status": "active",
        "surface": "matter_live_status",
        "decision": "Keep as the short live operational status cache.",
        "audit_treatment": "Continue raising findings when coverage or useful fields are underfilled.",
        "follow_up": "Wire writers/backfill rather than adding a replacement status table.",
    },
    {
        "id": "clientdb.matter_live_status.waiting_for_sealed_order",
        "status": "active",
        "surface": "matter_live_status.waiting_for_sealed_order",
        "decision": "Keep as a derived 0/1 sealed-order flag.",
        "audit_treatment": "Treat absence/underfill as a sync or backfill issue, not a retirement decision.",
        "follow_up": "Populate through the startup/live-status sync path.",
    },
    {
        "id": "clientdb.matter_children",
        "status": "active",
        "surface": "matter_children",
        "decision": "Keep as structured child details for bundle summaries and chronology facts.",
        "audit_treatment": "Continue raising findings when the schema or backfill is incomplete.",
        "follow_up": "Use model-assisted extraction for name, DOB, gender, PR, notes, and source.",
    },
    {
        "id": "clientdb.matter_bank_details",
        "status": "active",
        "surface": "matter_bank_details",
        "decision": "Keep as structured financial detail from routine intake.",
        "audit_treatment": "Report coverage and leave empty/underfilled state visible.",
        "follow_up": "Use model-assisted extraction for fields that deterministic routing cannot safely parse.",
    },
    {
        "id": "ops.matter_activity_status",
        "status": "deprecated",
        "surface": "ops matter_activity_status",
        "decision": "Deprecated compatibility table; do not use it as the matter-closure policy.",
        "audit_treatment": "Report row count only; do not raise an unused-table finding.",
        "follow_up": "Leave schema/helpers for compatibility until local ops cleanup and Azure sync work can remove it safely.",
    },
    {
        "id": "clientdb.matter_permissions",
        "status": "review",
        "surface": "client DB matter_permissions",
        "decision": "Ops DB is canonical, but the client DB copy is not retired yet.",
        "audit_treatment": "Continue raising a legacy-row finding while rows remain.",
        "follow_up": "Compare against ops matter_permissions before any retirement decision.",
    },
    {
        "id": "clientdb.telemetry_tables",
        "status": "retired",
        "surface": "client DB telemetry/reporting tables",
        "decision": "Retired as client identity DB surfaces; active reporting flows from ops telemetry SQLite to Azure reporting tables.",
        "audit_treatment": "Report row counts only; do not raise repeated schema findings while rows remain.",
        "follow_up": "Keep existing rows for export/review unless a separately approved cleanup workflow retires or moves them.",
    },
]


def _connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _scalar(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> int:
    row = conn.execute(sql, tuple(params)).fetchone()
    if row is None:
        return 0
    return int(row[0] or 0)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
            (table,),
        ).fetchone()
    )


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    if not table_exists(conn, table):
        return []
    return [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def row_count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    return _scalar(conn, f"SELECT COUNT(*) FROM {table}")


def nonempty_count(conn: sqlite3.Connection, table: str, column: str) -> int:
    if column not in table_columns(conn, table):
        return 0
    return _scalar(
        conn,
        f"SELECT COUNT(*) FROM {table} WHERE NULLIF(TRIM(COALESCE(CAST({column} AS TEXT), '')), '') IS NOT NULL",
    )


def non_unknown_count(conn: sqlite3.Connection, table: str, column: str) -> int:
    if column not in table_columns(conn, table):
        return 0
    return _scalar(
        conn,
        (
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE NULLIF(TRIM(COALESCE(CAST({column} AS TEXT), '')), '') IS NOT NULL "
            f"AND LOWER(TRIM(CAST({column} AS TEXT))) <> 'unknown'"
        ),
    )


def distinct_matter_count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table) or "matter_id" not in table_columns(conn, table):
        return 0
    return _scalar(conn, f"SELECT COUNT(DISTINCT matter_id) FROM {table}")


def recent_matter_ids(conn: sqlite3.Connection, days: int) -> list[int]:
    if not table_exists(conn, "matters") or "created_utc" not in table_columns(conn, "matters"):
        return []
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat().replace("+00:00", "Z")
    rows = conn.execute("SELECT matter_id FROM matters WHERE created_utc > ?", (cutoff,)).fetchall()
    return [int(row["matter_id"]) for row in rows]


def recent_coverage(conn: sqlite3.Connection, table: str, recent_ids: list[int]) -> dict[str, int]:
    if not recent_ids or not table_exists(conn, table) or "matter_id" not in table_columns(conn, table):
        return {"recent_matters": len(recent_ids), "recent_covered": 0}
    placeholders = ",".join("?" for _ in recent_ids)
    covered = _scalar(
        conn,
        f"SELECT COUNT(DISTINCT matter_id) FROM {table} WHERE matter_id IN ({placeholders})",
        tuple(recent_ids),
    )
    return {"recent_matters": len(recent_ids), "recent_covered": covered}


def recent_nonempty_count(conn: sqlite3.Connection, table: str, column: str, recent_ids: list[int]) -> int:
    if not recent_ids or column not in table_columns(conn, table):
        return 0
    placeholders = ",".join("?" for _ in recent_ids)
    return _scalar(
        conn,
        (
            f"SELECT COUNT(*) FROM {table} WHERE matter_id IN ({placeholders}) "
            f"AND NULLIF(TRIM(COALESCE(CAST({column} AS TEXT), '')), '') IS NOT NULL"
        ),
        tuple(recent_ids),
    )


def fill_stats(conn: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, dict[str, Any]]:
    total = row_count(conn, table)
    existing = set(table_columns(conn, table))
    stats: dict[str, dict[str, Any]] = {}
    for column in columns:
        if column not in existing:
            stats[column] = {"present": False, "filled": 0, "total": total, "pct": 0.0}
            continue
        if column in {"legal_aid_tracker_status"}:
            filled = non_unknown_count(conn, table, column)
        else:
            filled = nonempty_count(conn, table, column)
        pct = round((filled / total * 100.0), 1) if total else 0.0
        stats[column] = {"present": True, "filled": filled, "total": total, "pct": pct}
    return stats


_TIMESTAMP_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def _parse_iso_utc_timestamp(value: str) -> dt.datetime | None:
    text = value.strip()
    if not _TIMESTAMP_SHAPE.match(text):
        return None
    iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return dt.datetime.fromisoformat(iso_text)
    except ValueError:
        return None


def timestamp_quality(conn: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, dict[str, Any]]:
    existing = set(table_columns(conn, table))
    stats: dict[str, dict[str, Any]] = {}
    for column in columns:
        if column not in existing:
            stats[column] = {"present": False, "filled": 0, "malformed": 0}
            continue
        filled = 0
        malformed = 0
        for row in conn.execute(f"SELECT {column} AS value FROM {table}"):
            value = str(row["value"] or "").strip()
            if not value:
                continue
            filled += 1
            if _parse_iso_utc_timestamp(value) is None:
                malformed += 1
        stats[column] = {"present": True, "filled": filled, "malformed": malformed}
    return stats


def dob_quality(conn: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, dict[str, Any]]:
    existing = set(table_columns(conn, table))
    today = dt.date.today()
    earliest = dt.date(1900, 1, 1)
    stats: dict[str, dict[str, Any]] = {}
    for column in columns:
        if column not in existing:
            stats[column] = {"present": False, "filled": 0, "malformed": 0, "future": 0, "implausibly_old": 0}
            continue
        filled = 0
        malformed = 0
        future = 0
        implausibly_old = 0
        for row in conn.execute(f"SELECT {column} AS value FROM {table}"):
            value = str(row["value"] or "").strip()
            if not value:
                continue
            filled += 1
            try:
                parsed = dt.date.fromisoformat(value)
            except ValueError:
                malformed += 1
                continue
            if parsed > today:
                future += 1
            if parsed < earliest:
                implausibly_old += 1
        stats[column] = {
            "present": True,
            "filled": filled,
            "malformed": malformed,
            "future": future,
            "implausibly_old": implausibly_old,
        }
    return stats


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return {str(row["name"]): row_count(conn, str(row["name"])) for row in rows}


def normalise_path(value: Any) -> str:
    return "/".join(str(value or "").replace("\\", "/").strip().strip("/").lower().split())


def _library_root() -> str:
    import sys

    tools_dir = str(REPO_ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import firm_profile

    return firm_profile.load_profile().library_root


LIVE_MATTER_BASE = _library_root()

PathResolver = Callable[[str], "tuple[str, str] | None"]


def _clean_graph_path(value: Any) -> str:
    return re.sub(r"/+", "/", str(value or "").replace("\\", "/")).strip().strip("/")


def _candidate_paths(path: str) -> list[str]:
    cleaned = _clean_graph_path(path)
    if not cleaned:
        return []
    candidates = [cleaned]
    lower = cleaned.lower()
    marker = LIVE_MATTER_BASE.lower() + "/"
    if marker in lower:
        start = lower.index(marker)
        from_base = cleaned[start:]
        below_base = cleaned[start + len(marker):]
        for variant in (from_base, below_base):
            if variant and variant.lower() not in {c.lower() for c in candidates}:
                candidates.append(variant)
    else:
        candidates.append(f"{LIVE_MATTER_BASE}/{cleaned}")
    return candidates


def _resolve_via_index(ops_db: Path | None, path: str) -> "tuple[str, str] | None":
    if not ops_db or not Path(ops_db).exists():
        return None
    cleaned = _clean_graph_path(path)
    if not cleaned:
        return None
    with _connect(Path(ops_db)) as conn:
        required = {"drive_id", "item_id", "path", "item_type", "deleted_at_utc"}
        if not required.issubset(set(table_columns(conn, "onedrive_items"))):
            return None
        row = conn.execute(
            """
            SELECT drive_id, item_id
            FROM onedrive_items
            WHERE deleted_at_utc IS NULL
              AND item_type = 'folder'
              AND path = ? COLLATE NOCASE
            LIMIT 1
            """,
            (cleaned,),
        ).fetchone()
    if row is None:
        return None
    return (str(row["drive_id"] or ""), str(row["item_id"] or ""))


def _resolve_via_graph(path: str) -> "tuple[str, str] | None":
    import urllib.error

    try:
        import sys as _sys

        tools_dir = str(REPO_ROOT / "tools")
        if tools_dir not in _sys.path:
            _sys.path.insert(0, tools_dir)
        import graph_files
    except Exception:
        return None
    try:
        payload = graph_files.metadata(path)
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None
    item_id = str(payload.get("id") or "")
    drive_id = str(payload.get("_caseforge_drive_id") or "")
    return (drive_id, item_id) if item_id else None


def make_path_resolver(ops_db: Path | None) -> PathResolver:
    cache: dict[str, "tuple[str, str] | None"] = {}

    def resolve(path: str) -> "tuple[str, str] | None":
        key = _clean_graph_path(path).lower()
        if not key:
            return None
        if key in cache:
            return cache[key]
        target: "tuple[str, str] | None" = None
        candidates = _candidate_paths(path)
        for candidate in candidates:
            target = _resolve_via_index(ops_db, candidate)
            if target:
                break
        if target is None:
            for candidate in candidates:
                target = _resolve_via_graph(candidate)
                if target:
                    break
        cache[key] = target
        return target

    return resolve


def max_timestamp_value(conn: sqlite3.Connection, table: str, column: str, where: str = "1 = 1") -> str:
    if not table_exists(conn, table) or column not in table_columns(conn, table):
        return ""
    row = conn.execute(
        (
            f"SELECT MAX({column}) FROM {table} "
            f"WHERE {where} "
            f"AND NULLIF(TRIM(COALESCE(CAST({column} AS TEXT), '')), '') IS NOT NULL "
            f"AND TRIM(CAST({column} AS TEXT)) GLOB '20[0-9][0-9]-[01][0-9]-[0-3][0-9]T*Z'"
        )
    ).fetchone()
    return str(row[0] or "") if row else ""


def _folder_path_column(conn: sqlite3.Connection, table: str, candidates: tuple[str, ...]) -> str:
    existing = set(table_columns(conn, table))
    for column in candidates:
        if column in existing:
            return column
    return ""


def _path_rows(conn: sqlite3.Connection, table: str, id_column: str, path_column: str) -> dict[str, str]:
    if not table_exists(conn, table) or id_column not in table_columns(conn, table) or path_column not in table_columns(conn, table):
        return {}
    rows = conn.execute(
        f"""
        SELECT {id_column} AS matter_id, {path_column} AS folder_path
        FROM {table}
        WHERE NULLIF(TRIM(COALESCE(CAST({path_column} AS TEXT), '')), '') IS NOT NULL
        """
    ).fetchall()
    return {str(row["matter_id"]): str(row["folder_path"] or "").strip() for row in rows}


def compare_path_maps(
    left: dict[str, str],
    right: dict[str, str],
    resolve_path: PathResolver | None = None,
) -> dict[str, int]:
    overlap = set(left) & set(right)
    same = 0
    string_different_same_target = 0
    for matter_id in overlap:
        if normalise_path(left[matter_id]) == normalise_path(right[matter_id]):
            same += 1
            continue
        if resolve_path is None:
            continue
        left_target = resolve_path(left[matter_id])
        if left_target is None:
            continue
        if left_target == resolve_path(right[matter_id]):
            same += 1
            string_different_same_target += 1
    different = len(overlap) - same
    return {
        "left_rows": len(left),
        "right_rows": len(right),
        "overlap": len(overlap),
        "same": same,
        "different": different,
        "string_different_same_target": string_different_same_target,
        "left_only": len(set(left) - set(right)),
        "right_only": len(set(right) - set(left)),
    }


def _normalise_permission_value(value: Any) -> int | str:
    if value is None:
        return "NULL"
    text = str(value).strip()
    if text == "":
        return "NULL"
    try:
        return int(text)
    except ValueError:
        return text.lower()


def _permission_flag_rows(conn: sqlite3.Connection) -> tuple[dict[str, dict[str, Any]], set[str]]:
    if not table_exists(conn, "matter_permissions"):
        return {}, set()
    existing = set(table_columns(conn, "matter_permissions"))
    if "matter_id" not in existing:
        return {}, set()
    flags = [column for column in PERMISSION_FLAG_COLUMNS if column in existing]
    selected = ["matter_id", *flags]
    rows = conn.execute(f"SELECT {', '.join(selected)} FROM matter_permissions").fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        matter_id = str(row["matter_id"] or "").strip()
        if not matter_id:
            continue
        result[matter_id] = {flag: _normalise_permission_value(row[flag]) for flag in flags}
    return result, set(flags)


def _true_count(rows: Iterable[dict[str, Any]], flag: str) -> int:
    return sum(1 for row in rows if row.get(flag) == 1)


def analyse_permission_truth(client_db: Path, ops_db: Path | None) -> dict[str, Any]:
    with _connect(client_db) as client_conn:
        client_rows, client_flags = _permission_flag_rows(client_conn)
    ops_rows: dict[str, dict[str, Any]] = {}
    ops_flags: set[str] = set()
    if ops_db and ops_db.exists():
        with _connect(ops_db) as ops_conn:
            ops_rows, ops_flags = _permission_flag_rows(ops_conn)

    client_ids = set(client_rows)
    ops_ids = set(ops_rows)
    overlap = client_ids & ops_ids
    client_only = client_ids - ops_ids
    ops_only = ops_ids - client_ids
    shared_flags = client_flags & ops_flags
    flag_comparisons: dict[str, dict[str, Any]] = {}
    for flag in PERMISSION_FLAG_COLUMNS:
        overlap_same = 0
        overlap_different = 0
        if flag in shared_flags:
            overlap_same = sum(1 for matter_id in overlap if client_rows[matter_id].get(flag) == ops_rows[matter_id].get(flag))
            overlap_different = len(overlap) - overlap_same
        flag_comparisons[flag] = {
            "client_present": flag in client_flags,
            "ops_present": flag in ops_flags,
            "client_only_true": _true_count((client_rows[matter_id] for matter_id in client_only), flag),
            "ops_only_true": _true_count((ops_rows[matter_id] for matter_id in ops_only), flag),
            "overlap_same": overlap_same,
            "overlap_different": overlap_different,
        }

    overlap_any_shared_flag_different = 0
    if shared_flags:
        overlap_any_shared_flag_different = sum(
            1
            for matter_id in overlap
            if any(client_rows[matter_id].get(flag) != ops_rows[matter_id].get(flag) for flag in shared_flags)
        )
    return {
        "surface_rows": {
            "client_db.matter_permissions": len(client_rows),
            "ops.matter_permissions": len(ops_rows),
        },
        "comparison": {
            "overlap": len(overlap),
            "client_only": len(client_only),
            "ops_only": len(ops_only),
            "overlap_any_shared_flag_different": overlap_any_shared_flag_different,
        },
        "client_missing_ops_columns": [flag for flag in PERMISSION_FLAG_COLUMNS if flag in ops_flags and flag not in client_flags],
        "ops_missing_client_columns": [flag for flag in PERMISSION_FLAG_COLUMNS if flag in client_flags and flag not in ops_flags],
        "flag_comparisons": flag_comparisons,
        "recommended_canonical": (
            "ops.matter_permissions remains canonical. Keep client DB matter_permissions read-only until "
            "client-only rows and overlapping flag conflicts have been exported/reconciled into ops."
        ),
        "raw_ids_included": False,
    }


def analyse_folder_truth(
    client_db: Path,
    ops_db: Path | None,
    resolve_path: PathResolver | None = None,
) -> dict[str, Any]:
    if resolve_path is None:
        resolve_path = make_path_resolver(ops_db if ops_db and ops_db.exists() else None)
    with _connect(client_db) as client_conn:
        matter_paths = _path_rows(client_conn, "matters", "matter_id", "live_matter_folder")
        client_path_column = _folder_path_column(client_conn, "matter_folder_locations", ("matter_folder_path", "folder_path"))
        client_location_paths = _path_rows(client_conn, "matter_folder_locations", "matter_id", client_path_column) if client_path_column else {}
        freshness: dict[str, str] = {
            "matters.updated_utc": max_timestamp_value(
                client_conn,
                "matters",
                "updated_utc",
                "NULLIF(TRIM(COALESCE(CAST(live_matter_folder AS TEXT), '')), '') IS NOT NULL",
            ),
            "client.matter_folder_locations.last_verified_utc": max_timestamp_value(
                client_conn,
                "matter_folder_locations",
                "last_verified_utc",
                "NULLIF(TRIM(COALESCE(CAST(matter_folder_path AS TEXT), '')), '') IS NOT NULL"
                if client_path_column == "matter_folder_path"
                else "1 = 1",
            ),
        }
    ops_root_paths: dict[str, str] = {}
    ops_index_folders = 0
    if ops_db and ops_db.exists():
        with _connect(ops_db) as ops_conn:
            ops_root_paths = _path_rows(ops_conn, "matter_onedrive_roots", "matter_id", "folder_path")
            freshness["ops.matter_onedrive_roots.verified_at"] = max_timestamp_value(ops_conn, "matter_onedrive_roots", "verified_at")
            if table_exists(ops_conn, "onedrive_items") and "item_type" in table_columns(ops_conn, "onedrive_items"):
                ops_index_folders = _scalar(ops_conn, "SELECT COUNT(*) FROM onedrive_items WHERE item_type = 'folder'")
                freshness["ops.onedrive_items.last_seen_utc"] = max_timestamp_value(
                    ops_conn,
                    "onedrive_items",
                    "last_seen_utc",
                    "item_type = 'folder'",
                )
    return {
        "surface_rows": {
            "matters.live_matter_folder": len(matter_paths),
            "client.matter_folder_locations": len(client_location_paths),
            "ops.matter_onedrive_roots": len(ops_root_paths),
            "ops.onedrive_items_folders": ops_index_folders,
        },
        "comparisons": {
            "matters_vs_client_folder_locations": compare_path_maps(matter_paths, client_location_paths, resolve_path),
            "matters_vs_ops_roots": compare_path_maps(matter_paths, ops_root_paths, resolve_path),
            "client_folder_locations_vs_ops_roots": compare_path_maps(client_location_paths, ops_root_paths, resolve_path),
        },
        "freshness": freshness,
        "recommended_canonical": "ops.onedrive_items for live existence; ops.matter_onedrive_roots for verified matter root pointers; matters.live_matter_folder as SQL cache; client matter_folder_locations is retired and should require explicit migration/debug opt-in",
    }


def analyse_reference_integrity(conn: sqlite3.Connection) -> dict[str, Any]:
    if not table_exists(conn, "matter_references"):
        return {
            "duplicate_reference_values": 0,
            "duplicate_reference_rows": 0,
            "duplicate_reference_types": {},
            "company_refs_not_mirrored": 0,
        }
    duplicate_rows = conn.execute(
        """
        SELECT ref_type, ref_value_normalised, COUNT(DISTINCT matter_id) AS matter_count, COUNT(*) AS row_count
        FROM matter_references
        WHERE NULLIF(TRIM(COALESCE(ref_value_normalised, '')), '') IS NOT NULL
        GROUP BY ref_type, ref_value_normalised
        HAVING COUNT(DISTINCT matter_id) > 1 OR COUNT(*) > 1
        """
    ).fetchall()
    by_type: dict[str, int] = {}
    duplicate_reference_rows = 0
    for row in duplicate_rows:
        ref_type = str(row["ref_type"] or "unknown")
        by_type[ref_type] = by_type.get(ref_type, 0) + 1
        duplicate_reference_rows += int(row["row_count"] or 0)

    company_refs_not_mirrored = 0
    if table_exists(conn, "matters") and "company_reference" in table_columns(conn, "matters"):
        company_refs_not_mirrored = _scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM matters m
            WHERE NULLIF(TRIM(COALESCE(m.company_reference, '')), '') IS NOT NULL
              AND NOT EXISTS (
                SELECT 1
                FROM matter_references mr
                WHERE mr.matter_id = m.matter_id
                  AND mr.ref_type = 'company_ref'
                  AND UPPER(REPLACE(TRIM(mr.ref_value), ' ', '')) = UPPER(REPLACE(TRIM(m.company_reference), ' ', ''))
              )
            """,
        )

    return {
        "duplicate_reference_values": len(duplicate_rows),
        "duplicate_reference_rows": duplicate_reference_rows,
        "duplicate_reference_types": by_type,
        "company_refs_not_mirrored": company_refs_not_mirrored,
    }


def _normalise_contact_value(surface: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text or PLACEHOLDER_RE.match(text):
        return ""
    if surface.endswith(".email_primary"):
        return text.lower() if "@" in text else ""
    if surface.endswith(".phone_digits"):
        digits = re.sub(r"\D+", "", text)
        if len(digits) < 7 or set(digits) <= {"0"}:
            return ""
        return digits
    if surface.endswith(".nino_canonical"):
        nino = re.sub(r"\s+", "", text.upper())
        if not re.match(r"^[A-Z]{2}\d{6}[A-Z]$", nino):
            return ""
        return nino
    if surface.endswith(".address_text"):
        lowered = re.sub(r"\s+", " ", text.lower()).strip()
        return lowered if len(lowered) >= 8 else ""
    if surface.endswith(".display_name") or surface.endswith(".canonical_name"):
        lowered = re.sub(r"[^a-z0-9 ]+", "", re.sub(r"\s+", " ", text.lower())).strip()
        return lowered if lowered and not PLACEHOLDER_RE.match(lowered) else ""
    return text.lower()


def _placeholder_count(conn: sqlite3.Connection, table: str, column: str) -> int:
    if not table_exists(conn, table) or column not in table_columns(conn, table):
        return 0
    rows = conn.execute(
        f"SELECT {column} AS value FROM {table} WHERE NULLIF(TRIM(COALESCE(CAST({column} AS TEXT), '')), '') IS NOT NULL"
    ).fetchall()
    return sum(1 for row in rows if PLACEHOLDER_RE.match(str(row["value"] or "")))


def _duplicate_surface_stats(conn: sqlite3.Connection, table: str, column: str) -> dict[str, Any]:
    surface = f"{table}.{column}"
    if not table_exists(conn, table) or column not in table_columns(conn, table):
        return {"present": False, "duplicate_values": 0, "rows_in_duplicate_groups": 0, "largest_group_size": 0}
    groups: dict[str, int] = {}
    for row in conn.execute(f"SELECT {column} AS value FROM {table}"):
        normalised = _normalise_contact_value(surface, row["value"])
        if normalised:
            groups[normalised] = groups.get(normalised, 0) + 1
    duplicate_sizes = [count for count in groups.values() if count > 1]
    return {
        "present": True,
        "duplicate_values": len(duplicate_sizes),
        "rows_in_duplicate_groups": sum(duplicate_sizes),
        "largest_group_size": max(duplicate_sizes, default=0),
    }


def analyse_contact_integrity(conn: sqlite3.Connection) -> dict[str, Any]:
    surfaces = [
        ("people", "email_primary"),
        ("people", "phone_digits"),
        ("people", "nino_canonical"),
        ("matter_parties", "email_primary"),
        ("matter_parties", "phone_digits"),
        ("matter_parties", "address_text"),
        ("matter_parties", "display_name"),
    ]
    placeholders = {
        f"{table}.{column}": _placeholder_count(conn, table, column)
        for table, column in surfaces
    }
    duplicates = {
        f"{table}.{column}": _duplicate_surface_stats(conn, table, column)
        for table, column in surfaces
    }
    firm_email_people = 0
    if table_exists(conn, "people") and "email_primary" in table_columns(conn, "people"):
        firm_email_people = sum(
            1
            for row in conn.execute("SELECT email_primary FROM people WHERE NULLIF(TRIM(COALESCE(email_primary, '')), '') IS NOT NULL")
            if FIRM_EMAIL_RE.search(str(row["email_primary"] or ""))
        )
    return {
        "placeholder_values": placeholders,
        "duplicate_surfaces": duplicates,
        "firm_email_in_people": firm_email_people,
    }


def analyse_client_db(path: Path) -> dict[str, Any]:
    with _connect(path) as conn:
        matters = row_count(conn, "matters")
        children_summary_filled = nonempty_count(conn, "matters", "children_summary")
        recent_ids = recent_matter_ids(conn, RECENT_MATTER_WINDOW_DAYS)
        result: dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
            "table_counts": table_counts(conn),
            "matters_total": matters,
            "matter_columns": fill_stats(conn, "matters", MATTER_COLUMNS),
            "people_columns": fill_stats(conn, "people", PEOPLE_COLUMNS),
            "party_columns": fill_stats(conn, "matter_parties", PARTY_COLUMNS),
            "child_columns": fill_stats(conn, "matter_children", CHILD_COLUMNS),
            "live_status_columns": fill_stats(conn, "matter_live_status", LIVE_STATUS_COLUMNS),
            "date_quality": {
                "matters": timestamp_quality(conn, "matters", MATTER_TIMESTAMP_COLUMNS),
                "identity_dobs": {
                    "people": dob_quality(conn, "people", ["dob_iso"]),
                    "matter_parties": dob_quality(conn, "matter_parties", ["dob_iso"]),
                    "matter_children": dob_quality(conn, "matter_children", ["dob_iso"]),
                },
            },
            "contracts": {
                "matter_live_status": LIVE_STATUS_CONTRACT,
                "matter_children": CHILDREN_CONTRACT,
            },
            "schema": {
                "matters_columns": table_columns(conn, "matters"),
                "missing_expected_matter_columns": [
                    column for column in ("relationship_start", "relationship_end", "marriage_date", "divorce_date", "lived_together", "married", "bail_conditions", "bail_end_date", "crime_refs") if column not in table_columns(conn, "matters")
                ],
                "missing_expected_child_columns": [
                    column for column in ("child_name", "dob_iso", "gender", "parental_responsibility")
                    if column not in table_columns(conn, "matter_children")
                ],
            },
            "coverage": {
                "matter_children_rows": row_count(conn, "matter_children"),
                "matter_children_matters": distinct_matter_count(conn, "matter_children"),
                "children_summary_filled": children_summary_filled,
                "matter_children_recent": recent_coverage(conn, "matter_children", recent_ids),
                "children_summary_filled_recent": recent_nonempty_count(conn, "matters", "children_summary", recent_ids),
                "matter_bank_details_rows": row_count(conn, "matter_bank_details"),
                "matter_bank_details_matters": distinct_matter_count(conn, "matter_bank_details"),
                "matter_live_status_rows": row_count(conn, "matter_live_status"),
                "matter_live_status_matters": distinct_matter_count(conn, "matter_live_status"),
                "matter_live_status_recent": recent_coverage(conn, "matter_live_status", recent_ids),
                "matter_folder_locations_rows": row_count(conn, "matter_folder_locations"),
                "matter_folder_locations_matters": distinct_matter_count(conn, "matter_folder_locations"),
                "matter_permissions_rows": row_count(conn, "matter_permissions"),
                "matter_permissions_matters": distinct_matter_count(conn, "matter_permissions"),
            },
            "reference_integrity": analyse_reference_integrity(conn),
            "contact_integrity": analyse_contact_integrity(conn),
            "legacy": {
                "billing_actions_rows": row_count(conn, "billing_actions"),
                "billing_rate_sources_rows": row_count(conn, "billing_rate_sources"),
                "client_telemetry_rows": {
                    table: row_count(conn, table) for table in CLIENT_TELEMETRY_TABLES if table_exists(conn, table)
                },
                "migrations_rows": row_count(conn, "_migrations"),
            },
        }
        return result


def analyse_ops_db(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "table_counts": {}, "coverage": {}}
    with _connect(path) as conn:
        return {
            "path": str(path),
            "exists": True,
            "table_counts": table_counts(conn),
            "coverage": {
                "matter_permissions_rows": row_count(conn, "matter_permissions"),
                "matter_onedrive_roots_rows": row_count(conn, "matter_onedrive_roots"),
                "matter_activity_status_rows": row_count(conn, "matter_activity_status"),
                "onedrive_items_rows": row_count(conn, "onedrive_items"),
                "document_field_sources_rows": row_count(conn, "document_field_sources"),
            },
        }


def add_finding(findings: list[dict[str, str]], severity: str, code: str, title: str, recommendation: str) -> None:
    findings.append(
        {
            "severity": severity,
            "code": code,
            "title": title,
            "recommendation": recommendation,
        }
    )


def build_findings(client: dict[str, Any], ops: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    matters = int(client.get("matters_total") or 0)
    coverage = client.get("coverage", {})
    legacy = client.get("legacy", {})
    matter_cols = client.get("matter_columns", {})
    child_cols = client.get("child_columns", {})
    live_cols = client.get("live_status_columns", {})
    date_quality = client.get("date_quality", {})
    reference_integrity = client.get("reference_integrity", {})
    contact_integrity = client.get("contact_integrity", {})

    status_rows = int(coverage.get("matter_live_status_rows") or 0)
    live_nonempty = sum(int(stat.get("filled") or 0) for stat in live_cols.values() if stat.get("present"))
    recent = coverage.get("matter_live_status_recent") or {}
    recent_matters = int(recent.get("recent_matters") or 0)
    recent_covered = int(recent.get("recent_covered") or 0)
    if recent_matters and (recent_covered / recent_matters) < 0.60:
        add_finding(
            findings,
            "high",
            "clientdb_matter_live_status_underused",
            (
                f"matter_live_status covers only {recent_covered}/{recent_matters} matters opened in the last "
                f"{RECENT_MATTER_WINDOW_DAYS} days -- a lifetime ratio would read this as healthy."
            ),
            "Confirm the intake-time writer (referralpartner-intake-check.py) and order_intake.py's own upsert are actually running before adding any new hearing/status tables.",
        )
    if status_rows and live_nonempty == 0:
        add_finding(
            findings,
            "high",
            "clientdb_matter_live_status_empty_fields",
            "matter_live_status has rows but no useful status fields filled.",
            "Treat this as schema drift or a broken writer path; do not build summaries from it until fixed.",
        )

    recent_children_summary = int((coverage.get("children_summary_filled_recent")) or 0)
    recent_child_matters = int((coverage.get("matter_children_recent") or {}).get("recent_covered") or 0)
    if recent_children_summary and recent_child_matters < recent_children_summary * 0.25:
        add_finding(
            findings,
            "medium",
            "matter_children_backfill_needed",
            (
                f"Structured matter_children coverage ({recent_child_matters}/{recent_children_summary} recent "
                f"matters) is far behind children_summary in the last {RECENT_MATTER_WINDOW_DAYS} days."
            ),
            "Backfill safe child name/DOB/gender/PR rows from structured intake sources, then render children_summary from matter_children where possible.",
        )

    if not child_cols.get("gender", {}).get("present"):
        add_finding(
            findings,
            "medium",
            "matter_children_missing_gender_column",
            "matter_children cannot represent the full child summary contract because gender is missing.",
            "Add matter_children.gender and ask the model-assisted intake path to populate it when source material states it.",
        )

    if not matter_cols.get("relationship_start", {}).get("present") or not matter_cols.get("relationship_end", {}).get("present"):
        add_finding(
            findings,
            "medium",
            "relationship_columns_missing_locally",
            "Local client DB is missing relationship_start/relationship_end columns expected by current code.",
            "Run or reconcile the relationship-date migration before relying on those fields in summary renderers.",
        )

    malformed_timestamp_count = sum(
        int(stat.get("malformed") or 0)
        for stat in (date_quality.get("matters") or {}).values()
        if stat.get("present")
    )
    if malformed_timestamp_count:
        add_finding(
            findings,
            "medium",
            "matter_timestamp_values_malformed",
            "Some matters timestamp fields are not valid ISO-like UTC strings.",
            "Review and repair malformed created_utc/updated_utc/closed_at values before using recency as a source-priority signal.",
        )

    identity_dob_problem_count = 0
    for table_stats in (date_quality.get("identity_dobs") or {}).values():
        for stat in table_stats.values():
            if not stat.get("present"):
                continue
            identity_dob_problem_count += int(stat.get("malformed") or 0)
            identity_dob_problem_count += int(stat.get("future") or 0)
            identity_dob_problem_count += int(stat.get("implausibly_old") or 0)
    if identity_dob_problem_count:
        add_finding(
            findings,
            "medium",
            "clientdb_identity_dob_values_invalid",
            "Client DB has malformed, future, or implausibly old DOB values.",
            "Repair DOB import errors before using age, relationship, or identity signals for automatic matching.",
        )

    if int(coverage.get("matter_permissions_rows") or 0):
        add_finding(
            findings,
            "medium",
            "clientdb_permissions_legacy_rows",
            "Client DB matter_permissions still has rows even though ops DB is canonical.",
            "Compare with ops matter_permissions, migrate any missing decisions, then keep the client table as read-only fallback or retire it.",
        )

    if int(reference_integrity.get("duplicate_reference_values") or 0):
        add_finding(
            findings,
            "high",
            "matter_references_duplicate_values",
            "matter_references contains duplicate normalised reference values.",
            "Treat duplicate court/company refs as bad-import candidates; confirm the correct matter from folder/file evidence and remove or move the bad reference rows before relying on automatic matter matching.",
        )

    if int(reference_integrity.get("company_refs_not_mirrored") or 0):
        add_finding(
            findings,
            "medium",
            "company_references_not_mirrored",
            "Some matters.company_reference values are not mirrored into matter_references as company_ref rows.",
            "Mirror company references into matter_references so matchers can use one reference table consistently.",
        )

    duplicate_contact_surfaces = [
        surface
        for surface, stats in (contact_integrity.get("duplicate_surfaces") or {}).items()
        if int(stats.get("duplicate_values") or 0)
    ]
    if duplicate_contact_surfaces:
        add_finding(
            findings,
            "medium",
            "clientdb_duplicate_contact_values",
            "Client DB has duplicate real-looking contact values.",
            "Review duplicate emails, phones, NINOs, addresses, and party names with deterministic merge/alias rules; do not merge solely on address or common names.",
        )

    placeholder_values = sum(int(value or 0) for value in (contact_integrity.get("placeholder_values") or {}).values())
    if placeholder_values:
        add_finding(
            findings,
            "medium",
            "clientdb_placeholder_contact_values",
            "Client DB still contains placeholder strings in contact/identity fields.",
            "Replace placeholder contact values with NULL so matchers do not treat them as real duplicate evidence.",
        )

    if int(contact_integrity.get("firm_email_in_people") or 0):
        add_finding(
            findings,
            "high",
            "clientdb_firm_email_as_client_email",
            "Firm mailbox addresses appear in people.email_primary.",
            "Clear firm addresses from client email fields and verify true client contact details from source material.",
        )

    if int(legacy.get("migrations_rows") or 0) == 0:
        add_finding(
            findings,
            "low",
            "migration_tracking_empty",
            "Local _migrations table has no applied migration rows.",
            "Review migration status for local SQLite so schema drift is visible before further schema work.",
        )

    return findings


def pct_line(stats: dict[str, Any]) -> str:
    if not stats.get("present"):
        return "missing"
    return f"{stats.get('filled', 0)}/{stats.get('total', 0)} ({stats.get('pct', 0)}%)"


def render_markdown(report: dict[str, Any]) -> str:
    client = report["client_db"]
    ops = report["ops_db"]
    findings = report["findings"]
    lines = [
        "# Client DB Schema Audit",
        "",
        f"Generated UTC: {report['generated_utc']}",
        "",
        "## Scope",
        "",
        f"- Client DB: `{client['path']}`",
        f"- Ops DB: `{ops['path']}`" if ops.get("exists") else f"- Ops DB: `{ops['path']}` (not found)",
        "- Mode: non-destructive audit only; no SQL changes were made.",
        "",
        "## Table Contracts",
        "",
        "`matter_live_status` is a one-row-per-matter operational status cache. Values are mostly short text or UTC timestamp strings; `waiting_for_sealed_order` is an integer 0/1 flag.",
        "",
    ]
    for column, meaning in (client.get("contracts", {}).get("matter_live_status") or {}).items():
        lines.append(f"- `matter_live_status.{column}`: {meaning}")
    lines.extend(
        [
            "",
            "`matter_children` is the structured child detail table for model-assisted intake and later source backfills.",
            "",
        ]
    )
    for column, meaning in (client.get("contracts", {}).get("matter_children") or {}).items():
        lines.append(f"- `matter_children.{column}`: {meaning}")
    lines.extend(
        [
            "",
            "## Schema Decisions",
            "",
        ]
    )
    for item in report.get("schema_decisions", []):
        lines.extend(
            [
                f"### {str(item['status']).upper()} - {item['surface']}",
                "",
                f"Decision: {item['decision']}",
                "",
                f"Audit treatment: {item['audit_treatment']}",
                "",
                f"Follow-up: {item['follow_up']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Findings",
            "",
        ]
    )
    if findings:
        for item in findings:
            lines.extend(
                [
                    f"### {item['severity'].upper()} - {item['code']}",
                    "",
                    item["title"],
                    "",
                    f"Recommendation: {item['recommendation']}",
                    "",
                ]
            )
    else:
        lines.append("- No findings triggered by current thresholds.")
        lines.append("")

    coverage = client["coverage"]
    lines.extend(
        [
            "## Client DB Coverage",
            "",
            f"- Matters: {client['matters_total']}",
            f"- matter_children: {coverage.get('matter_children_rows', 0)} rows across {coverage.get('matter_children_matters', 0)} matters; children_summary filled on {coverage.get('children_summary_filled', 0)} matters.",
            f"- matter_bank_details: {coverage.get('matter_bank_details_rows', 0)} rows across {coverage.get('matter_bank_details_matters', 0)} matters.",
            f"- matter_live_status: {coverage.get('matter_live_status_rows', 0)} rows across {coverage.get('matter_live_status_matters', 0)} matters.",
            f"- matter_folder_locations: {coverage.get('matter_folder_locations_rows', 0)} rows.",
            f"- matter_permissions: {coverage.get('matter_permissions_rows', 0)} rows.",
            "",
            "## Key Matter Fields",
            "",
        ]
    )
    for column in MATTER_COLUMNS:
        lines.append(f"- `{column}`: {pct_line(client['matter_columns'].get(column, {}))}")
    lines.extend(["", "## Child Fields", ""])
    for column in CHILD_COLUMNS:
        lines.append(f"- `matter_children.{column}`: {pct_line(client['child_columns'].get(column, {}))}")
    lines.extend(["", "## People Fields", ""])
    for column in PEOPLE_COLUMNS:
        lines.append(f"- `people.{column}`: {pct_line(client['people_columns'].get(column, {}))}")
    lines.extend(["", "## Party Fields", ""])
    for column in PARTY_COLUMNS:
        lines.append(f"- `matter_parties.{column}`: {pct_line(client['party_columns'].get(column, {}))}")
    lines.extend(["", "## Ops DB Coverage", ""])
    for key, value in (ops.get("coverage") or {}).items():
        lines.append(f"- `{key}`: {value}")
    folder_truth = client.get("folder_truth") or {}
    lines.extend(["", "## Folder Truth", ""])
    lines.append(f"- Recommended canonical: {folder_truth.get('recommended_canonical', '')}")
    for surface, count in (folder_truth.get("surface_rows") or {}).items():
        lines.append(f"- `{surface}`: {count}")
    for name, comparison in (folder_truth.get("comparisons") or {}).items():
        lines.append(
            f"- `{name}`: overlap {comparison.get('overlap', 0)}, same {comparison.get('same', 0)}, different {comparison.get('different', 0)}, left-only {comparison.get('left_only', 0)}, right-only {comparison.get('right_only', 0)}, same-target-different-string {comparison.get('string_different_same_target', 0)}"
        )
    for surface, newest in (folder_truth.get("freshness") or {}).items():
        lines.append(f"- newest `{surface}`: {newest or '[none]'}")
    permission_truth = client.get("permission_truth") or {}
    lines.extend(["", "## Permission Truth", ""])
    lines.append(f"- Recommended canonical: {permission_truth.get('recommended_canonical', '')}")
    lines.append(f"- Raw matter IDs included: {permission_truth.get('raw_ids_included', False)}")
    for surface, count in (permission_truth.get("surface_rows") or {}).items():
        lines.append(f"- `{surface}`: {count}")
    comparison = permission_truth.get("comparison") or {}
    if comparison:
        lines.append(
            "- comparison: "
            f"overlap {comparison.get('overlap', 0)}, "
            f"client-only {comparison.get('client_only', 0)}, "
            f"ops-only {comparison.get('ops_only', 0)}, "
            f"overlap with any shared-flag difference {comparison.get('overlap_any_shared_flag_different', 0)}"
        )
    missing_client = permission_truth.get("client_missing_ops_columns") or []
    missing_ops = permission_truth.get("ops_missing_client_columns") or []
    if missing_client:
        lines.append(f"- client DB missing ops permission columns: {', '.join(f'`{item}`' for item in missing_client)}")
    if missing_ops:
        lines.append(f"- ops DB missing client permission columns: {', '.join(f'`{item}`' for item in missing_ops)}")
    for flag, stats in (permission_truth.get("flag_comparisons") or {}).items():
        lines.append(
            f"- `{flag}`: client present {stats.get('client_present')}, ops present {stats.get('ops_present')}; "
            f"client-only true {stats.get('client_only_true', 0)}, ops-only true {stats.get('ops_only_true', 0)}, "
            f"overlap same {stats.get('overlap_same', 0)}, overlap different {stats.get('overlap_different', 0)}"
        )
    reference_integrity = client.get("reference_integrity") or {}
    lines.extend(["", "## Reference Integrity", ""])
    lines.append(f"- duplicate normalised reference values: {reference_integrity.get('duplicate_reference_values', 0)}")
    lines.append(f"- rows involved in duplicate reference groups: {reference_integrity.get('duplicate_reference_rows', 0)}")
    lines.append(f"- company refs not mirrored into `matter_references`: {reference_integrity.get('company_refs_not_mirrored', 0)}")
    for ref_type, count in sorted((reference_integrity.get("duplicate_reference_types") or {}).items()):
        lines.append(f"- duplicate `{ref_type}` values: {count}")
    contact_integrity = client.get("contact_integrity") or {}
    lines.extend(["", "## Contact Integrity", ""])
    lines.append(f"- firm email values in `people.email_primary`: {contact_integrity.get('firm_email_in_people', 0)}")
    for surface, count in sorted((contact_integrity.get("placeholder_values") or {}).items()):
        lines.append(f"- placeholder `{surface}` values: {count}")
    for surface, stats in sorted((contact_integrity.get("duplicate_surfaces") or {}).items()):
        if not stats.get("present", True):
            lines.append(f"- duplicate `{surface}` values: missing surface")
            continue
        lines.append(
            f"- duplicate `{surface}` values: {stats.get('duplicate_values', 0)} groups; "
            f"{stats.get('rows_in_duplicate_groups', 0)} rows; largest group {stats.get('largest_group_size', 0)}"
        )
    lines.extend(["", "## Date Quality", ""])
    for table, columns in (client.get("date_quality") or {}).items():
        if table == "identity_dobs":
            continue
        for column, stats in columns.items():
            if not stats.get("present"):
                lines.append(f"- `{table}.{column}`: missing")
            else:
                lines.append(
                    f"- `{table}.{column}`: filled {stats.get('filled', 0)}, malformed {stats.get('malformed', 0)}"
                )
    lines.extend(["", "## Identity DOB Quality", ""])
    for table, columns in ((client.get("date_quality") or {}).get("identity_dobs") or {}).items():
        for column, stats in columns.items():
            if not stats.get("present"):
                lines.append(f"- `{table}.{column}`: missing")
            else:
                lines.append(
                    f"- `{table}.{column}`: filled {stats.get('filled', 0)}, "
                    f"malformed {stats.get('malformed', 0)}, future {stats.get('future', 0)}, "
                    f"implausibly old {stats.get('implausibly_old', 0)}"
                )
    lines.extend(["", "## Retired Or Non-Identity Tables In Client DB", ""])
    legacy = client["legacy"]
    lines.append(f"- `billing_actions`: {legacy.get('billing_actions_rows', 0)} rows")
    lines.append(f"- `billing_rate_sources`: {legacy.get('billing_rate_sources_rows', 0)} rows")
    for table, count in (legacy.get("client_telemetry_rows") or {}).items():
        lines.append(f"- `{table}`: {count} rows")
    lines.append(f"- `_migrations`: {legacy.get('migrations_rows', 0)} rows")
    lines.append("")
    return "\n".join(lines)


def build_report(
    client_db: Path,
    ops_db: Path | None = None,
    resolve_path: PathResolver | None = None,
) -> dict[str, Any]:
    client = analyse_client_db(client_db)
    ops_path = ops_db or default_ops_db() or UNCONFIGURED_OPS_DB
    ops = analyse_ops_db(ops_path)
    client["folder_truth"] = analyse_folder_truth(client_db, ops_path, resolve_path)
    client["permission_truth"] = analyse_permission_truth(client_db, ops_path)
    return {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "client_db": client,
        "ops_db": ops,
        "schema_decisions": SCHEMA_DECISIONS,
        "findings": build_findings(client, ops),
    }


def write_default_report(markdown: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"clientdb-schema-audit-{stamp}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Non-destructive CaseForge client DB schema utilisation audit.")
    parser.add_argument("--client-db", type=Path, default=None, help="SQLite client DB to audit; default the configured clientdb_sql backend (Postgres is mirrored to a throwaway SQLite file), else a local clients/ mirror.")
    parser.add_argument("--ops-db", type=Path, default=None, help="Ops DB to read; default the configured one (CASEFORGE_OPS_DB).")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown.")
    parser.add_argument("--output", type=Path, help="Write markdown or JSON to this path.")
    parser.add_argument("--write-default-report", action="store_true", help="Write markdown report under artifacts/.")
    return parser.parse_args(argv)


def _sqlite_value(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, str, bytes)):
        return value
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, memoryview):
        return bytes(value)
    try:
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
    except ImportError:
        pass
    return str(value)


def export_postgres_mirror(dest: Path, conn: Any = None) -> int:
    if conn is None:
        import sys

        tools_dir = str(REPO_ROOT / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import clientdb_sql

        with clientdb_sql.get_connection() as live:
            return export_postgres_mirror(dest, live)
    names = [
        str(row[0])
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        ).fetchall()
    ]
    mirror = sqlite3.connect(str(dest))
    try:
        for name in names:
            cur = conn.execute(f'SELECT * FROM "{name}"')
            columns = [str(d[0]) for d in cur.description]
            quoted = ", ".join(f'"{c}"' for c in columns)
            mirror.execute(f'CREATE TABLE "{name}" ({quoted})')
            marks = ", ".join("?" for _ in columns)
            while True:
                batch = cur.fetchmany(1000)
                if not batch:
                    break
                mirror.executemany(
                    f'INSERT INTO "{name}" VALUES ({marks})',
                    [tuple(_sqlite_value(v) for v in row) for row in batch],
                )
        mirror.commit()
    finally:
        mirror.close()
    return len(names)


def _configured_sqlite_client_db() -> Path | None:
    import sys

    tools_dir = str(REPO_ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import clientdb_sql

        if clientdb_sql.configured_backend() == "sqlite":
            path = Path(clientdb_sql._sqlite_path())
            return path if path.is_file() else None
    except Exception:
        return None
    return None


def _postgres_configured() -> bool:
    import sys

    tools_dir = str(REPO_ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import clientdb_sql

        return clientdb_sql.configured_backend() == "postgres"
    except Exception:
        return False


SCRATCH_ENV = "CLIENTDB_AUDIT_SCRATCH_DIR"
SCRATCH_PREFIX = "clientdb-audit-"


def _private_scratch_base() -> Path | None:
    explicit = os.getenv(SCRATCH_ENV, "").strip()
    if explicit:
        base = Path(explicit)
        return base if base.is_dir() and os.access(base, os.W_OK) else None
    shm = Path("/dev/shm")
    if shm.is_dir() and os.access(shm, os.W_OK):
        return shm
    try:
        import sys

        tools_dir = str(REPO_ROOT / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import ops_db

        luks = ops_db.read_luks_paths_env(ops_db.TELEMETRY_ROOT_ENV)
    except Exception:
        luks = ""
    if luks and Path(luks).is_dir() and os.access(luks, os.W_OK):
        return Path(luks)
    return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def clear_stale_scratch(base: Path) -> int:
    removed = 0
    for path in base.glob(f"{SCRATCH_PREFIX}*"):
        match = re.match(rf"^{re.escape(SCRATCH_PREFIX)}(\d+)-", path.name)
        if match and _pid_alive(int(match.group(1))):
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed


def main(argv: list[str] | None = None) -> int:
    base = _private_scratch_base()
    if base is None:
        return _main(None, argv)
    clear_stale_scratch(base)
    previous_umask = os.umask(0o077)
    scratch = Path(tempfile.mkdtemp(prefix=f"{SCRATCH_PREFIX}{os.getpid()}-", dir=base))
    try:
        return _main(scratch, argv)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        os.umask(previous_umask)


def _main(scratch: Path | None, argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.client_db is None:
        args.client_db = _configured_sqlite_client_db()
    if args.client_db is None and _postgres_configured():
        if scratch is None:
            raise SystemExit(
                "No private scratch location for the Postgres mirror: /dev/shm and the LUKS telemetry "
                f"volume are both unavailable. Set {SCRATCH_ENV} to a tmpfs or encrypted directory."
            )
        args.client_db = scratch / "caseforge-clientdb.sqlite"
        try:
            export_postgres_mirror(args.client_db)
            os.chmod(args.client_db, 0o600)
        except Exception as exc:
            raise SystemExit(f"Could not read caseforge-clientdb from Postgres to audit it: {type(exc).__name__}")
        from_postgres = True
    else:
        from_postgres = False
    if args.client_db is None:
        args.client_db = _default_client_db()
    if args.client_db is None:
        raise SystemExit(
            "No client DB to audit. Configure clientdb_sql for the live Postgres caseforge-clientdb "
            "(CASEFORGE_CLIENTDB_PG_URL) or a SQLite file, keep a clients/caseforge-clientdb.sqlite "
            "(or .stale-* snapshot) mirror, or pass --client-db explicitly."
        )
    if not args.client_db.exists():
        raise SystemExit(f"Client DB not found: {args.client_db}")
    if args.client_db.name.endswith(("-wal", "-shm", "-journal")):
        raise SystemExit(
            f"Refusing to audit {args.client_db.name}: that is a SQLite "
            f"sidecar, not a database. Pass the database file itself."
        )
    import sqlite3 as _sqlite3

    try:
        with _sqlite3.connect(f"file:{args.client_db}?mode=ro", uri=True) as _conn:
            _table_count = _conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
    except _sqlite3.DatabaseError as exc:
        raise SystemExit(f"Refusing to audit {args.client_db.name}: not a readable "
                         f"SQLite database ({exc})")
    if _table_count == 0:
        raise SystemExit(
            f"Refusing to audit {args.client_db.name}: zero tables. An empty "
            f"schema audited 'successfully' reads as a healthy absence of "
            f"findings; if this file is a fresh export it is incomplete."
        )
    report = build_report(args.client_db, args.ops_db)

    try:
        age_days = (
            dt.datetime.now(dt.timezone.utc)
            - dt.datetime.fromtimestamp(args.client_db.stat().st_mtime, dt.timezone.utc)
        ).days
    except OSError:
        age_days = None
    report["client_db_source"] = {
        "path": str(args.client_db),
        "is_live": from_postgres or args.client_db.name == "caseforge-clientdb.sqlite",
        "backend": "postgres" if from_postgres else "sqlite",
        "age_days": age_days,
        "note": (
            "Live client data is Postgres caseforge-clientdb, audited through a throwaway SQLite "
            "mirror taken at run time. With no Postgres configured the tool audits the "
            "newest local SQLite snapshot, which may be stale."
        ),
    }
    if args.json:
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        rendered = render_markdown(report)
    output_path: Path | None = args.output
    if args.write_default_report and output_path is None:
        output_path = write_default_report(render_markdown(report), DEFAULT_ARTIFACTS)
    elif output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    if output_path:
        print(output_path)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
