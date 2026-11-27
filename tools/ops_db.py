#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import json
import logging
import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

_LOG = logging.getLogger(__name__)

try:
    import actor_kind
    import firm_profile
except ImportError:
    from tools import actor_kind, firm_profile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPS_DB_PATH = REPO_ROOT / "ops" / "caseforge-ops.sqlite3"
OPS_DB_ENV = "CASEFORGE_OPS_DB"
TELEMETRY_ROOT_ENV = "CASEFORGE_TELEMETRY_ROOT"
LUKS_PATHS_ENV_FILE = Path(os.getenv("CASEFORGE_LUKS_PATHS_FILE", "/etc/caseforge-automation/luks-paths.env"))

LIVE_BASE = firm_profile.load_profile().library_root
LEGACY_TELEMETRY_DB = REPO_ROOT / "telemetry" / "caseforge-telemetry.sqlite3"
LEGACY_AGENT_JOBS_DB = REPO_ROOT / "telemetry" / "agent-jobs.sqlite3"
LEGACY_OUTPUT_FEEDBACK_DB = REPO_ROOT / "DATA" / "output-feedback.sqlite"


def utc_now_z() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def read_luks_paths_env(key: str) -> str:
    try:
        text = LUKS_PATHS_ENV_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


DEFAULT_TELEMETRY_ROOT = REPO_ROOT / "telemetry"
HUB_REQUEST_LOG_NAME = "caseforge-hub-api-requests.jsonl"


def hub_request_log_path() -> Path:
    root = os.getenv(TELEMETRY_ROOT_ENV, "").strip()
    return (Path(root) if root else DEFAULT_TELEMETRY_ROOT) / HUB_REQUEST_LOG_NAME


def hub_request_log_candidates(default_root: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    for raw in (os.getenv(TELEMETRY_ROOT_ENV, "").strip(), read_luks_paths_env(TELEMETRY_ROOT_ENV)):
        if raw:
            roots.append(Path(raw))
    roots.append(Path(default_root) if default_root is not None else DEFAULT_TELEMETRY_ROOT)
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        path = root / HUB_REQUEST_LOG_NAME
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def resolve_hub_request_log(default_root: Path | None = None) -> Path | None:
    best: tuple[float, Path] | None = None
    for path in hub_request_log_candidates(default_root):
        try:
            if not path.is_file():
                continue
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if best is None or mtime > best[0]:
            best = (mtime, path)
    return best[1] if best else None


class OpsDbNotConfiguredError(RuntimeError):
    pass


def configured_ops_db_path() -> Path | None:
    configured = os.getenv(OPS_DB_ENV, "").strip() or read_luks_paths_env(OPS_DB_ENV)
    return Path(configured) if configured else None


def resolve_ops_db_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    configured = configured_ops_db_path()
    if configured:
        return configured
    raise OpsDbNotConfiguredError(
        f"{OPS_DB_ENV} is not set, and {LUKS_PATHS_ENV_FILE} has no entry for it "
        f"either -- refusing to fall back to the unencrypted default at "
        f"{DEFAULT_OPS_DB_PATH} (gh#275/#290). For a cron/systemd job, source "
        f"tools/lib/job-harness.sh, or add EnvironmentFile=-{LUKS_PATHS_ENV_FILE} to "
        f"the unit. For an interactive/dev session, export {OPS_DB_ENV} yourself."
    )



WAL_SWITCH_ATTEMPTS = 5
WAL_RETRY_SLEEP_SECONDS = 0.05
BUSY_TIMEOUT_MS = 30_000


def _journal_mode(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA journal_mode;").fetchone()
    return str((row[0] if row else "") or "").strip().lower()


def enable_wal(conn: sqlite3.Connection, *, attempts: int = WAL_SWITCH_ATTEMPTS) -> str:
    for attempt in range(max(1, attempts)):
        try:
            if _journal_mode(conn) == "wal":
                return "wal"
            row = conn.execute("PRAGMA journal_mode=WAL;").fetchone()
            return str((row[0] if row else "wal") or "wal").strip().lower()
        except sqlite3.OperationalError:
            if attempt == max(1, attempts) - 1:
                break
            time.sleep(WAL_RETRY_SLEEP_SECONDS * (attempt + 1))
    try:
        return _journal_mode(conn) or "unknown"
    except sqlite3.OperationalError:
        return "unknown"


_WAL_CONFIRMED: set[tuple[str, int, int]] = set()


def apply_connection_pragmas(
    conn: sqlite3.Connection,
    *,
    attempts: int = WAL_SWITCH_ATTEMPTS,
    db_key: tuple[str, int, int] | None = None,
) -> str:
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS};")
    key = db_key
    if key is not None and key in _WAL_CONFIRMED:
        mode = "wal"
    else:
        mode = enable_wal(conn, attempts=attempts)
        if key is not None and mode == "wal":
            _WAL_CONFIRMED.add(key)
    conn.execute(f"PRAGMA synchronous={_synchronous_level()};")
    conn.execute("PRAGMA foreign_keys=ON;")
    return mode


def _synchronous_level() -> str:
    return "OFF" if os.environ.get("CASEFORGE_SQLITE_SYNCHRONOUS_OFF") == "1" else "NORMAL"


_SCHEMA_READY: set[tuple[str, int, int]] = set()


SCHEMA_STAMP = 4217


def _schema_stamp(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _schema_key(db_path: Path) -> tuple[str, int, int] | None:
    try:
        stat = db_path.stat()
    except OSError:
        return None
    return (str(db_path), stat.st_dev, stat.st_ino)


def _connect_raw(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = resolve_ops_db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    key = _schema_key(db_path)
    apply_connection_pragmas(conn, db_key=key)
    if key is None or key not in _SCHEMA_READY or _schema_stamp(conn) != SCHEMA_STAMP:
        ensure_schema(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_STAMP}")
        key = _schema_key(db_path)
        if key is not None:
            _SCHEMA_READY.add(key)
    _ensure_change_log_safely(conn)
    label_connection(conn)
    return conn


@contextlib.contextmanager
def connect(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = _connect_raw(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_database(path: str | Path | None = None) -> Path:
    db_path = resolve_ops_db_path(path)
    with connect(db_path):
        pass
    return db_path


SCHEMA_RETRY_ATTEMPTS = 6


def ensure_schema(conn: sqlite3.Connection, *, force: bool = False) -> None:
    if not force:
        key = _main_db_key(conn)
        if key is not None and key in _SCHEMA_READY and _schema_stamp(conn) == SCHEMA_STAMP:
            return
    for attempt in range(SCHEMA_RETRY_ATTEMPTS):
        try:
            _ensure_schema_once(conn)
            break
        except sqlite3.OperationalError as exc:
            if "schema has changed" not in str(exc) or attempt == SCHEMA_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(0.02 * (attempt + 1))
    _ensure_change_log_safely(conn)


def _ensure_change_log_safely(conn: sqlite3.Connection) -> None:
    for attempt in range(SCHEMA_RETRY_ATTEMPTS):
        try:
            ensure_change_log(conn)
            return
        except sqlite3.Error as exc:
            if "schema has changed" in str(exc) and attempt < SCHEMA_RETRY_ATTEMPTS - 1:
                time.sleep(0.02 * (attempt + 1))
                continue
            print(f"ops_db: change log not installed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return


def _ensure_schema_once(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ops_schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS onedrive_items (
            item_id TEXT NOT NULL,
            drive_id TEXT NOT NULL,
            parent_item_id TEXT,
            root_name TEXT NOT NULL,
            path TEXT NOT NULL,
            name TEXT NOT NULL,
            item_type TEXT NOT NULL CHECK (item_type IN ('folder', 'file')),
            modified_utc TEXT,
            size_bytes INTEGER,
            deleted_at_utc TEXT,
            last_seen_utc TEXT NOT NULL,
            name_normalised TEXT NOT NULL,
            path_normalised TEXT NOT NULL,
            PRIMARY KEY (drive_id, item_id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_onedrive_items_path
            ON onedrive_items(path COLLATE NOCASE);

        CREATE INDEX IF NOT EXISTS idx_onedrive_items_item_id
            ON onedrive_items(item_id);

        CREATE INDEX IF NOT EXISTS idx_onedrive_items_parent
            ON onedrive_items(drive_id, parent_item_id, item_type);

        CREATE INDEX IF NOT EXISTS idx_onedrive_items_path_lookup
            ON onedrive_items(path_normalised);

        CREATE INDEX IF NOT EXISTS idx_onedrive_items_name_lookup
            ON onedrive_items(name_normalised);

        CREATE INDEX IF NOT EXISTS idx_onedrive_items_root_seen
            ON onedrive_items(root_name, last_seen_utc);

        CREATE TABLE IF NOT EXISTS matter_onedrive_roots (
            matter_id TEXT PRIMARY KEY,
            drive_id TEXT,
            folder_item_id TEXT,
            folder_path TEXT,
            root_name TEXT,
            source TEXT NOT NULL,
            verified_at TEXT NOT NULL,
            created_utc TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_matter_onedrive_roots_item
            ON matter_onedrive_roots(drive_id, folder_item_id);

        CREATE INDEX IF NOT EXISTS idx_matter_onedrive_roots_path
            ON matter_onedrive_roots(folder_path COLLATE NOCASE);

        CREATE TABLE IF NOT EXISTS matter_permissions (
            matter_id TEXT PRIMARY KEY,
            allow_email_print INTEGER,
            email_print_set_at TEXT,
            email_print_set_by TEXT,
            allow_sos_to_court_draft INTEGER,
            sos_to_court_draft_set_at TEXT,
            sos_to_court_draft_set_by TEXT,
            notes TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_matter_permissions_email_print
            ON matter_permissions(allow_email_print);

        -- Completed casework, one row per artefact produced for a matter.
        --
        -- Nothing else records that a client care letter or attendance
        -- note has been done: `matters` has 34 columns and `matter_live_status` 15, and
        -- the only related field anywhere is matter_folder_locations.attendance_folder_id
        -- -- which says where to *put* an attendance note, not whether one exists. This
        -- table answers "has this been done already", which the per-machine caseforge-chat
        -- design needs to avoid two people producing the same letter, and which a
        -- billing register is a different grouping of.
        --
        -- Recorded, not derived: a file appearing in a folder is evidence a document
        -- exists, not evidence of who did it, when, or for which chargeable event. Both
        -- uses need the second thing.
        --
        -- No UNIQUE on (matter_id, work_type): a matter legitimately has several
        -- attendance notes. Duplicate *suppression* is a question the reader asks
        -- ("is there one since the last hearing?"), not a constraint the table imposes.
        CREATE TABLE IF NOT EXISTS matter_work_log (
            work_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            work_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed'
                CHECK (status IN ('completed', 'draft', 'superseded')),
            performed_by TEXT,
            performed_on_host TEXT,
            occurred_at TEXT NOT NULL,
            reference TEXT,
            artefact_url TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_matter_work_log_matter
            ON matter_work_log(matter_id, work_type, occurred_at DESC);

        CREATE INDEX IF NOT EXISTS idx_matter_work_log_occurred
            ON matter_work_log(occurred_at DESC);

        -- Legacy: caseforge-client-viewer's Edit button briefly used a
        -- propose/accept/reject review queue (2026-09-07). Retired the same
        -- day -- every solicitor reaches the tool through one shared login,
        -- so a second-person review was never real, and self-accepting your
        -- own proposal is not oversight. Table kept, not dropped, so the
        -- handful of real rows it collected are not lost; they are copied
        -- into client_edit_history below rather than read from here again.
        CREATE TABLE IF NOT EXISTS client_edit_proposals (
            proposal_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT NOT NULL,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'accepted', 'rejected')),
            proposed_by TEXT,
            created_at TEXT NOT NULL,
            resolved_by TEXT,
            resolved_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_client_edit_proposals_matter
            ON client_edit_proposals(matter_id, status, created_at DESC);

        -- What caseforge-client-viewer's Edit button writes to now (2026-09-08):
        -- applied immediately, one row per change, `edited_by` a typed name
        -- rather than a verified login -- see client_edits.py's module
        -- docstring for why. An append-only history, never a queue: nothing
        -- here is ever superseded or deleted, a wrong edit gets corrected by
        -- a further edit.
        CREATE TABLE IF NOT EXISTS client_edit_history (
            edit_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT NOT NULL,
            note TEXT,
            edited_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_client_edit_history_matter
            ON client_edit_history(matter_id, created_at DESC);

        -- A nightly copy of Microsoft's audit log (tools/usage/ms_audit_ingest.py): mailbox and file changes by
        -- people and by apps, and the tenant's admin events. Read by the CRM's audit page.
        CREATE TABLE IF NOT EXISTS ms_audit_events (
            id TEXT PRIMARY KEY,
            created_utc TEXT NOT NULL,
            workload TEXT NOT NULL,
            operation TEXT NOT NULL,
            user_upn TEXT,
            user_type TEXT,
            app_id TEXT,
            client_ip TEXT,
            source_path TEXT,
            dest_path TEXT,
            source_name TEXT,
            dest_name TEXT,
            site_url TEXT,
            detail_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ms_audit_events_time ON ms_audit_events(created_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_ms_audit_events_ip ON ms_audit_events(client_ip, created_utc);

        -- Every sign-in and failed sign-in Microsoft recorded, from the same nightly copy.
        CREATE TABLE IF NOT EXISTS ms_signins (
            id TEXT PRIMARY KEY,
            created_utc TEXT NOT NULL,
            user_upn TEXT,
            result TEXT NOT NULL,
            error_code TEXT,
            client_ip TEXT,
            app_id TEXT,
            user_agent TEXT,
            request_type TEXT,
            os TEXT,
            browser TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ms_signins_time ON ms_signins(created_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_ms_signins_ip ON ms_signins(client_ip, created_utc);

        -- One-time backfill of the legacy queue's real output (whatever was
        -- actually accepted before the redesign), keyed on the same id so
        -- re-running this on every startup is a no-op the second time.
        INSERT OR IGNORE INTO client_edit_history
            (edit_id, matter_id, field_name, old_value, new_value, note, edited_by, created_at)
        SELECT proposal_id, matter_id, field_name, old_value, new_value, note,
               COALESCE(NULLIF(resolved_by, ''), proposed_by, 'unknown'),
               COALESCE(resolved_at, created_at)
        FROM client_edit_proposals
        WHERE status = 'accepted';

        -- Quick-tick boolean flags on a matter (e.g. "persistent caller")
        -- that don't correspond to a real caseforge-clientdb column -- added
        -- 2026-09-08, owner request: "some things ... are things I can tick
        -- and be done with it" rather than typing a note every time. One
        -- row per (matter_id, flag_name); flipping a flag overwrites the
        -- row rather than appending, since only the current state matters
        -- here -- unlike client_edit_history, this is not itself a log
        -- (each flip is still separately recorded there, field_name
        -- "flag:<name>", for the "who/when" audit trail).
        -- A server copy of the client viewer's attendance-note typing box and saved drafts, one row
        -- per matter, so they follow the caseworker to another browser.
        -- Where a matter's signed letter of authority was filed and its 1st witness statement found, so
        -- the client viewer does not list the client's folders on every open. One row per matter and marker.
        CREATE TABLE IF NOT EXISTS matter_markers (
            matter_id TEXT NOT NULL,
            marker TEXT NOT NULL,
            item_id TEXT NOT NULL,
            drive_id TEXT NOT NULL,
            web_url TEXT NOT NULL,
            date TEXT NOT NULL,
            checked_utc TEXT NOT NULL,
            PRIMARY KEY (matter_id, marker)
        );

        -- The Details tab's Legal aid section, one row per matter: what the intro's benefits entry
        -- meant, the completed application found in the LAA correspondence folder, the envelope it
        -- was sent for signing in, and the signed declaration filed when it came back.
        CREATE TABLE IF NOT EXISTS matter_legal_aid (
            matter_id TEXT PRIMARY KEY,
            benefits_decision TEXT NOT NULL DEFAULT '',
            app_item_id TEXT NOT NULL DEFAULT '',
            app_drive_id TEXT NOT NULL DEFAULT '',
            app_name TEXT NOT NULL DEFAULT '',
            app_path TEXT NOT NULL DEFAULT '',
            app_url TEXT NOT NULL DEFAULT '',
            app_found_utc TEXT NOT NULL DEFAULT '',
            envelope_id TEXT NOT NULL DEFAULT '',
            sent_utc TEXT NOT NULL DEFAULT '',
            sent_by TEXT NOT NULL DEFAULT '',
            signed_item_id TEXT NOT NULL DEFAULT '',
            signed_drive_id TEXT NOT NULL DEFAULT '',
            signed_name TEXT NOT NULL DEFAULT '',
            signed_url TEXT NOT NULL DEFAULT '',
            signed_utc TEXT NOT NULL DEFAULT '',
            problem TEXT NOT NULL DEFAULT '',
            updated_utc TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS an_backups (
            matter_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS form_draft_backups (
            matter_id TEXT NOT NULL,
            form_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_utc TEXT NOT NULL,
            PRIMARY KEY (matter_id, form_id)
        );

        CREATE TABLE IF NOT EXISTS matter_flags (
            matter_id TEXT NOT NULL,
            flag_name TEXT NOT NULL,
            is_set INTEGER NOT NULL DEFAULT 0,
            set_by TEXT,
            set_at TEXT,
            PRIMARY KEY (matter_id, flag_name)
        );

        -- A person's own Flag and Star on a matter (vergil/client_edits.py). Only set flags are stored: clearing
        -- deletes the row. user_key is the signed-in identity the hub already knows (user_state.budget_identity,
        -- lower-cased). Flags that automation raises stay in matter_flags, shared by everyone.
        CREATE TABLE IF NOT EXISTS user_matter_flags (
            user_key TEXT NOT NULL,
            matter_id TEXT NOT NULL,
            flag_name TEXT NOT NULL,
            set_at TEXT NOT NULL,
            reason TEXT,
            PRIMARY KEY (user_key, matter_id, flag_name)
        );
        CREATE INDEX IF NOT EXISTS idx_user_matter_flags_matter ON user_matter_flags(matter_id);

        -- A flag on a file or folder in the audit page's Folders view (vergil/audit_folder_view.py): "this is wrong, or
        -- should not be here". Shared by every admin and kept until cleared; a cleared flag keeps its row. kind is who set it:
        -- a person, an agent (an AI session) or automation (a scan); an item can carry one open flag of each kind and each
        -- kind clears only its own (the unique index is made in the migration below, as the column may be new). item_key is the
        -- OneDrive item id while the index knows the item (it survives a move or a rename), otherwise "path:" and the path
        -- below the book, lower-cased. path is where the item was when flagged, shown if it has since gone.
        CREATE TABLE IF NOT EXISTS audit_folder_flags (
            flag_id INTEGER PRIMARY KEY AUTOINCREMENT,
            book TEXT NOT NULL,
            client TEXT NOT NULL,
            item_key TEXT NOT NULL,
            path TEXT NOT NULL,
            item_type TEXT NOT NULL,
            flagged_by TEXT NOT NULL,
            flagged_at TEXT NOT NULL,
            note TEXT,
            cleared_by TEXT,
            cleared_at TEXT,
            kind TEXT NOT NULL DEFAULT 'person'
        );
        CREATE INDEX IF NOT EXISTS idx_audit_folder_flags_client ON audit_folder_flags(book, client);

        -- Test clients: no longer read or written by any code; the table and its rows are left in place.
        CREATE TABLE IF NOT EXISTS test_clients (
            matter_id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL DEFAULT '',
            marked_by TEXT NOT NULL,
            marked_utc TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS test_clients_fixed BEFORE UPDATE ON test_clients
        BEGIN
            SELECT RAISE(ABORT, 'a test client is fixed at creation');
        END;

        -- New clients waiting for their signed New Client Form (onboarding/pending_new_clients.py):
        -- the button makes the folder, envelopes and draft and a row here; the person, matter and
        -- party are made when the form comes back. status: pending | creating | created | cancelled.
        -- stage is how far the press got (folder | pack | done), so a retry with the same
        -- request_id resumes it instead of refusing it; working_since is set while a press runs.
        -- The test tick columns (test_requested, test_marked_by, test_requested_utc) are no longer
        -- read or written; they stay in the schema, unused.
        CREATE TABLE IF NOT EXISTS pending_new_clients (
            pending_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_utc TEXT NOT NULL,
            created_by TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            category_key TEXT NOT NULL,
            category_label TEXT NOT NULL DEFAULT '',
            folder_path TEXT NOT NULL,
            extra_forms TEXT NOT NULL DEFAULT '[]',
            envelope_ids TEXT NOT NULL DEFAULT '{}',
            draft_id TEXT NOT NULL DEFAULT '',
            draft_web_link TEXT NOT NULL DEFAULT '',
            draft_subject TEXT NOT NULL DEFAULT '',
            test_requested INTEGER NOT NULL DEFAULT 0,
            test_marked_by TEXT NOT NULL DEFAULT '',
            test_requested_utc TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'creating', 'created', 'cancelled')),
            matter_id TEXT NOT NULL DEFAULT '',
            email_sent_utc TEXT NOT NULL DEFAULT '',
            returned TEXT NOT NULL DEFAULT '[]',
            created_matter_utc TEXT NOT NULL DEFAULT '',
            cancelled_by TEXT NOT NULL DEFAULT '',
            cancelled_utc TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            updated_utc TEXT NOT NULL DEFAULT '',
            request_id TEXT NOT NULL DEFAULT '',
            stage TEXT NOT NULL DEFAULT 'done',
            working_since TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            alert30_utc TEXT NOT NULL DEFAULT '',
            alert60_utc TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_pending_new_clients_status ON pending_new_clients(status);
        CREATE TRIGGER IF NOT EXISTS pending_new_clients_test_tick_fixed
        BEFORE UPDATE OF test_requested, test_marked_by, test_requested_utc ON pending_new_clients
        WHEN NEW.test_requested IS NOT OLD.test_requested
          OR NEW.test_marked_by IS NOT OLD.test_marked_by
          OR NEW.test_requested_utc IS NOT OLD.test_requested_utc
        BEGIN
            SELECT RAISE(ABORT, 'the test tick is fixed at the press');
        END;

        -- Removed clients (onboarding/client_removal.py): one row per removal, who, when, why
        -- and what was done. state: removed | restored | purged, or merged | unmerged for a
        -- client merged into another (onboarding/client_merge.py, merged_into names it).
        -- Hidden while removed, purged or merged.
        CREATE TABLE IF NOT EXISTS removed_clients (
            removal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            client_name TEXT NOT NULL DEFAULT '',
            is_test INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL,
            removed_by TEXT NOT NULL,
            removed_utc TEXT NOT NULL,
            folder_from TEXT NOT NULL DEFAULT '',
            folder_to TEXT NOT NULL DEFAULT '',
            actions TEXT NOT NULL DEFAULT '{}',
            state TEXT NOT NULL DEFAULT 'removed',
            restored_by TEXT NOT NULL DEFAULT '',
            restored_utc TEXT NOT NULL DEFAULT '',
            purged_utc TEXT NOT NULL DEFAULT '',
            purge_note TEXT NOT NULL DEFAULT '',
            merged_into TEXT NOT NULL DEFAULT ''
        );
        DROP INDEX IF EXISTS idx_removed_clients_open;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_removed_clients_hidden
            ON removed_clients(matter_id) WHERE state IN ('removed', 'purged', 'merged');

        -- Per-field "mark for review" flags (2026-09-23, owner instruction
        -- after a Vergil client-matching incident: "I don't trust it to
        -- find them in the first place" -- the caseworker flags a specific
        -- field's *current value* as worth a second look, no AI judgement
        -- involved in setting it). Deliberately not `matter_flags`: that
        -- table is a small, fixed vocabulary of whole-matter booleans;
        -- `field_name` here is free text (any field label the UI shows,
        -- including a per-party field like "Respondent address"), and a
        -- flag carries the actual value at flag time (`value_snapshot`),
        -- so the review queue is still useful even if the live field
        -- changes later. An open row (`resolved_at IS NULL`) is what the
        -- review-queue quick list reads; resolving marks it done rather
        -- than deleting it, same "nothing is ever deleted" reasoning as
        -- `client_edit_history`.
        CREATE TABLE IF NOT EXISTS field_review_flags (
            review_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            client_name TEXT,
            field_name TEXT NOT NULL,
            field_label TEXT NOT NULL,
            value_snapshot TEXT,
            note TEXT,
            flagged_by TEXT NOT NULL,
            flagged_at TEXT NOT NULL,
            resolved_by TEXT,
            resolved_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_field_review_flags_matter
            ON field_review_flags(matter_id, field_name);

        CREATE INDEX IF NOT EXISTS idx_field_review_flags_open
            ON field_review_flags(resolved_at, flagged_at DESC);

        CREATE TABLE IF NOT EXISTS matter_billing_items (
            item_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            item_date TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            quantity TEXT NOT NULL DEFAULT '1',
            minutes INTEGER NOT NULL DEFAULT 0,
            rate TEXT NOT NULL,
            net_amount TEXT NOT NULL,
            vat_amount TEXT NOT NULL,
            work_id TEXT,
            case_ref TEXT,
            source_file TEXT,
            client_name TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_matter_billing_items_matter
            ON matter_billing_items(matter_id, item_date);

        CREATE TABLE IF NOT EXISTS matter_activity_status (
            matter_id TEXT PRIMARY KEY,
            activity_status TEXT NOT NULL DEFAULT 'active'
                CHECK (activity_status IN ('active', 'inactive')),
            status_source TEXT NOT NULL,
            status_reason TEXT,
            effective_date TEXT,
            closing_letter_sent INTEGER NOT NULL DEFAULT 0,
            billing_pending INTEGER NOT NULL DEFAULT 0,
            billing_done INTEGER NOT NULL DEFAULT 0,
            legal_aid_pending INTEGER NOT NULL DEFAULT 0,
            legal_aid_done INTEGER NOT NULL DEFAULT 0,
            override INTEGER NOT NULL DEFAULT 0,
            created_utc TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_matter_activity_status_status
            ON matter_activity_status(activity_status);

        CREATE TABLE IF NOT EXISTS matter_routing_context (
            matter_id TEXT PRIMARY KEY,
            folder_path TEXT,
            root_name TEXT,
            folder_bucket TEXT NOT NULL DEFAULT 'unknown',
            owner_bucket TEXT NOT NULL DEFAULT 'standard_val',
            lifecycle TEXT NOT NULL DEFAULT 'unknown',
            attention_policy TEXT NOT NULL DEFAULT 'standard',
            priority TEXT NOT NULL DEFAULT 'normal',
            snoozed_until_utc TEXT,
            muted_at_utc TEXT,
            mute_reason TEXT,
            source TEXT NOT NULL,
            computed_utc TEXT NOT NULL,
            created_utc TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_matter_routing_context_bucket
            ON matter_routing_context(folder_bucket, lifecycle, owner_bucket);

        CREATE INDEX IF NOT EXISTS idx_matter_routing_context_attention
            ON matter_routing_context(attention_policy, priority);

        -- What a letter note (Perusal / Preparation) is about and how many pages it has, apart from an_drafts so its
        -- positional column list does not change. One row per draft that has either.
        CREATE TABLE IF NOT EXISTS an_letter_meta (
            draft_id TEXT PRIMARY KEY,
            doc_kind TEXT,
            pages INTEGER,
            letter_item_id TEXT,
            note_item_id TEXT,
            pair_key TEXT,
            linked_draft_id TEXT,
            auto_activity TEXT
        );

        CREATE TABLE IF NOT EXISTS an_drafts (
            draft_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            ticks_json TEXT NOT NULL,
            note_text TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'committed', 'draft')),
            created_utc TEXT NOT NULL,
            committed_utc TEXT,
            an_output_path TEXT,
            billing_item_id TEXT,
            billing_deleted_utc TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_an_drafts_matter
            ON an_drafts(matter_id, status);

        CREATE TABLE IF NOT EXISTS robot_notices (
            notice_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            matter_id TEXT NOT NULL DEFAULT '',
            client_name TEXT NOT NULL DEFAULT '',
            dedupe_key TEXT NOT NULL DEFAULT '',
            created_utc TEXT NOT NULL,
            resolved_utc TEXT,
            resolved_by TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_robot_notices_open
            ON robot_notices(resolved_utc, created_utc);

        CREATE TABLE IF NOT EXISTS pipeline_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_by TEXT NOT NULL DEFAULT '',
            updated_utc TEXT NOT NULL
        );

        -- Caseflow: one matter's own Manual/Auto setting. No row means the matter follows the
        -- firm-wide mode in pipeline_settings ("inherit"); a row says who chose what, and when.
        CREATE TABLE IF NOT EXISTS pipeline_matter_mode (
            matter_id TEXT PRIMARY KEY,
            setting TEXT NOT NULL,
            set_by TEXT NOT NULL,
            set_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pipeline_events (
            event_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            step TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            by_name TEXT NOT NULL DEFAULT '',
            mode TEXT NOT NULL DEFAULT 'manual',
            created_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_pipeline_events_matter
            ON pipeline_events(matter_id, created_utc);

        -- One run of one Case flow step at a time: a press racing auto mode, or a double click, finds
        -- the row and is refused instead of running the step twice. ``claimed_utc`` ages out a claim
        -- whose process died (``claim_pipeline_step``).
        CREATE TABLE IF NOT EXISTS pipeline_step_claims (
            matter_id TEXT NOT NULL,
            step TEXT NOT NULL,
            token TEXT NOT NULL,
            by_name TEXT NOT NULL DEFAULT '',
            claimed_utc TEXT NOT NULL,
            PRIMARY KEY (matter_id, step)
        );

        -- Caseflow: a step's view the last time its live check said "done". The tab shows it
        -- from here instead of re-reading OneDrive; a reset or a run of that step deletes it.
        CREATE TABLE IF NOT EXISTS pipeline_step_done (
            matter_id TEXT NOT NULL,
            step TEXT NOT NULL,
            view_json TEXT NOT NULL,
            checked_utc TEXT NOT NULL,
            PRIMARY KEY (matter_id, step)
        );

        -- Caseflow: a step's view the last time it was read live and was not done, so the tab can open
        -- from here without reading OneDrive or the mailbox. Overwritten by every live read.
        CREATE TABLE IF NOT EXISTS pipeline_step_seen (
            matter_id TEXT NOT NULL,
            step TEXT NOT NULL,
            view_json TEXT NOT NULL,
            checked_utc TEXT NOT NULL,
            PRIMARY KEY (matter_id, step)
        );

        -- Inbound mail a Caseflow step waits for (a court's reply, a statement of service),
        -- recorded by the mail-intake classifier for a confidently matched Caseflow matter.
        -- One row per message; consumed_utc is set by the step that acts on it.
        CREATE TABLE IF NOT EXISTS pipeline_triggers (
            trigger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('court_reply', 'sos')),
            message_id TEXT NOT NULL UNIQUE,
            conversation_id TEXT NOT NULL DEFAULT '',
            received_utc TEXT NOT NULL DEFAULT '',
            match_reasons TEXT NOT NULL DEFAULT '[]',
            consumed_utc TEXT,
            created_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_pipeline_triggers_matter
            ON pipeline_triggers(matter_id, kind, consumed_utc);

        -- Caseflow's ``serve_other`` step: someone other than the respondent a person has asked to serve
        -- (a law firm, a hospital, a school). One row per recipient; that step drafts one email each.
        CREATE TABLE IF NOT EXISTS pipeline_service_recipients (
            recipient_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            added_by TEXT NOT NULL,
            added_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_pipeline_service_recipients_matter
            ON pipeline_service_recipients(matter_id);

        -- Matters a person took off the Case flow board (old matters that are no longer part of
        -- Case flow). One row per matter. Nothing else is touched: the events, the done marks, the
        -- files and the drafts all stay. A person running or marking a step for the matter on its
        -- Case flow tab deletes the row, and the matter is on the board again.
        CREATE TABLE IF NOT EXISTS pipeline_board_removed (
            matter_id TEXT PRIMARY KEY,
            removed_by TEXT NOT NULL,
            removed_utc TEXT NOT NULL
        );

        -- A client sunk to the bottom of the status board (a no-show or drop-out), until a person acts for them.
        -- Internal only: the board shows no label. One row per matter; clearing deletes the row (the change log keeps it).
        CREATE TABLE IF NOT EXISTS pipeline_board_sunk (
            matter_id TEXT PRIMARY KEY,
            sunk_by TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            sunk_utc TEXT NOT NULL
        );

        -- A person's permission, per matter, for Case flow's folder step to download the client's documents
        -- from a WeTransfer link (WeTransfer's terms bar automated extraction, so it is never on by default).
        -- One row per matter; the grant covers that matter only.
        CREATE TABLE IF NOT EXISTS pipeline_wetransfer_grants (
            matter_id TEXT PRIMARY KEY,
            granted_by TEXT NOT NULL,
            granted_utc TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT ''
        );

        -- A person's dismissal of a cancelled item on the front page Auto Send panel (``vergil/auto_send_dismissals.py``).
        -- The item id is the send gate's draft id; the Outlook draft itself is never touched.
        CREATE TABLE IF NOT EXISTS pipeline_auto_send_dismissals (
            item_id TEXT PRIMARY KEY,
            dismissed_by TEXT NOT NULL,
            dismissed_utc TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT ''
        );

        -- One row per client nudge a person pressed on the Status board (``todos/client_nudge.py``): the rule
        -- that applied, who pressed it, and the Outlook draft it made. Never sent by us.
        CREATE TABLE IF NOT EXISTS pipeline_client_nudges (
            nudge_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            doc TEXT NOT NULL DEFAULT '',
            nudged_by TEXT NOT NULL,
            nudged_utc TEXT NOT NULL,
            draft_id TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_pipeline_client_nudges_matter
            ON pipeline_client_nudges(matter_id, doc, nudged_utc);

        -- The automatic reminders for a document left unsigned (``todos/client_nudge.py`` ``auto_remind``): one row per
        -- envelope and stage (``day2``, ``day4``, ``alert``), claimed before anything is made, so each stage happens at
        -- most once per envelope. The row with stage ``go_live`` holds the moment reminders began (nobody older is reminded).
        CREATE TABLE IF NOT EXISTS pipeline_unsigned_reminders (
            reminder_id INTEGER PRIMARY KEY AUTOINCREMENT,
            envelope_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            matter_id TEXT NOT NULL DEFAULT '',
            doc TEXT NOT NULL DEFAULT '',
            made_utc TEXT NOT NULL,
            draft_id TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            UNIQUE (envelope_id, stage)
        );

        -- The automatic court chaser (``todos/court_chase_auto.py``): one row per application (matter and the day it was sent), claimed
        -- before anything is made, so an application is chased once. ``status``: drafted, armed, superseded (the court replied first),
        -- left (the gate sent it) or refused. The row with ``anchor`` ``go_live`` holds the moment chasers began.
        CREATE TABLE IF NOT EXISTS pipeline_court_chasers (
            chaser_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            anchor TEXT NOT NULL,
            made_utc TEXT NOT NULL,
            draft_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'claimed',
            note TEXT NOT NULL DEFAULT '',
            UNIQUE (matter_id, anchor)
        );

        -- Caseflow sync scan: the newest scan result per matter (level 0 to 4, the step it could run from,
        -- whether a person needs to look), the snapshot it came from, the best state seen since a person last
        -- accepted it (``baseline_json``) and how the snapshot falls short of it (``regressions_json``).
        -- Counts and keys only, no file names. The snapshot is re-buildable by a scan; the baseline is not (it
        -- holds the best state seen and what a person accepted), and an accept is logged in the matter's
        -- activity log.
        CREATE TABLE IF NOT EXISTS matter_sync_scan (
            matter_id TEXT PRIMARY KEY,
            level INTEGER NOT NULL,
            start_at TEXT NOT NULL,
            attention INTEGER NOT NULL,
            scanned_utc TEXT NOT NULL,
            snapshot_json TEXT NOT NULL DEFAULT '{}',
            baseline_json TEXT NOT NULL DEFAULT '{}',
            regressions_json TEXT NOT NULL DEFAULT '[]'
        );

        -- Caseflow's ``amend`` step: one row per amendment round of the client's witness statement. The
        -- client's email, what it was read into and the prepared changes (``review_json``) wait for
        -- the owner; ``status`` is prepared, saved (statement saved, email not drafted yet), drafted
        -- or discarded. A discarded round does not count towards the round number.
        CREATE TABLE IF NOT EXISTS pipeline_amend_rounds (
            round_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            round_no INTEGER NOT NULL,
            status TEXT NOT NULL,
            email_text TEXT NOT NULL DEFAULT '',
            review_json TEXT NOT NULL DEFAULT '{}',
            prepared_by TEXT NOT NULL,
            prepared_utc TEXT NOT NULL,
            decided_by TEXT NOT NULL DEFAULT '',
            decided_utc TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_pipeline_amend_rounds_matter
            ON pipeline_amend_rounds(matter_id, round_no);

        -- Drafts the pipeline made that are to be watched until they leave (``onboarding/pipeline/sent_watch.py``):
        -- the draft's Graph id and internet message id, so a sent copy is matched by id and never by subject.
        -- ``status`` is draft, sent or stopped; ``auto_send`` is 1 when the draft carries LEAVING SOON.
        CREATE TABLE IF NOT EXISTS pipeline_sent_watch (
            watch_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            step TEXT NOT NULL,
            round INTEGER NOT NULL DEFAULT 0,
            class TEXT NOT NULL DEFAULT '',
            draft_id TEXT NOT NULL,
            internet_message_id TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            recipients TEXT NOT NULL DEFAULT '[]',
            web_link TEXT NOT NULL DEFAULT '',
            auto_send INTEGER NOT NULL DEFAULT 0,
            created_utc TEXT NOT NULL,
            sent_utc TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            stopped_reason TEXT NOT NULL DEFAULT '',
            armed_utc TEXT,
            sends_at TEXT,
            arm_note TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_pipeline_sent_watch_msgid
            ON pipeline_sent_watch(internet_message_id);
        CREATE INDEX IF NOT EXISTS idx_pipeline_sent_watch_draft
            ON pipeline_sent_watch(draft_id);

        -- Who opened a client's Activity log, and when (``vergil/activity_views.py``): one row per person per matter
        -- per ten minutes, for the log's "Seen by" line and the audit page. The viewer is a signed-in firm email.
        CREATE TABLE IF NOT EXISTS activity_log_views (
            view_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            viewer TEXT NOT NULL,
            viewed_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_activity_log_views_matter
            ON activity_log_views(matter_id, viewed_utc);

        -- The audit chain from a signed Documenso envelope (or an amended statement) to the file saved from it
        -- (``onboarding/pipeline/provenance.py``): one row per file written, with OneDrive's item id and the bytes' sha256.
        CREATE TABLE IF NOT EXISTS matter_file_provenance (
            provenance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            source TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT '',
            round INTEGER NOT NULL DEFAULT 0,
            envelope_id TEXT NOT NULL DEFAULT '',
            documenso_document_id TEXT NOT NULL DEFAULT '',
            drive_item_id TEXT NOT NULL DEFAULT '',
            sha256 TEXT NOT NULL DEFAULT '',
            path TEXT NOT NULL DEFAULT '',
            saved_utc TEXT NOT NULL,
            saved_by TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_matter_file_provenance_matter
            ON matter_file_provenance(matter_id, saved_utc);

        -- Which email actually left for a matter's step and round, and how: our draft as made, our draft edited
        -- before sending, or one written by hand (``onboarding/pipeline/provenance.py``). Filled from the sent watch
        -- and from Sent Items evidence; ids only, no subject or address.
        CREATE TABLE IF NOT EXISTS pipeline_sent_links (
            matter_id TEXT NOT NULL,
            step TEXT NOT NULL,
            round INTEGER NOT NULL DEFAULT 0,
            draft_message_id TEXT NOT NULL DEFAULT '',
            sent_message_id TEXT NOT NULL DEFAULT '',
            sent_internet_message_id TEXT NOT NULL DEFAULT '',
            sent_utc TEXT NOT NULL DEFAULT '',
            how TEXT NOT NULL,
            source TEXT NOT NULL,
            recorded_utc TEXT NOT NULL,
            PRIMARY KEY (matter_id, step, round)
        );

        -- The Case review tab: one row per matter and review date, holding both forms' answers (the File
        -- Review Form and the File Summary Sheet) as JSON, with who saved it. A later review date is a
        -- new row, so an earlier review stays as it was saved.
        CREATE TABLE IF NOT EXISTS matter_audits (
            matter_id TEXT NOT NULL,
            review_date TEXT NOT NULL,
            answers TEXT NOT NULL,
            saved_by TEXT NOT NULL,
            saved_utc TEXT NOT NULL,
            first_saved_by TEXT NOT NULL,
            first_saved_utc TEXT NOT NULL,
            saves INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (matter_id, review_date)
        );

        -- The Case review tab's conflict of interest check: each run for a matter, with who ran it and the
        -- ranked possible matches it found (names and match reasons, never contact values). The
        -- newest run is the one shown; an earlier run stays as it was.
        CREATE TABLE IF NOT EXISTS matter_conflict_checks (
            matter_id TEXT NOT NULL,
            run_utc TEXT NOT NULL,
            run_by TEXT NOT NULL,
            result TEXT NOT NULL,
            PRIMARY KEY (matter_id, run_utc)
        );

        -- An email address a person has confirmed is the matter's client's own, so the oddness check and
        -- the draft address checks stop flagging it. Keyed by matter and canonical address: a changed
        -- client email is a new address and starts unconfirmed.
        CREATE TABLE IF NOT EXISTS client_email_confirmations (
            matter_id TEXT NOT NULL,
            address TEXT NOT NULL,
            confirmed_by TEXT NOT NULL,
            confirmed_utc TEXT NOT NULL,
            PRIMARY KEY (matter_id, address)
        );

        -- A matter's category colour (teal, red, orange, purple, blue); '' is a deliberate "none".
        -- Retired: nothing reads or writes it. To be dropped after a backup.
        CREATE TABLE IF NOT EXISTS matter_category (
            matter_id TEXT PRIMARY KEY,
            colour TEXT NOT NULL,
            changed_by TEXT NOT NULL,
            changed_utc TEXT NOT NULL
        );

        -- The client's reply to the witness statement draft (client viewer green and red
        -- smiley lists): approved, or wants changes with a note. One row per matter; the
        -- latest reply wins and clearing it deletes the row.
        CREATE TABLE IF NOT EXISTS statement_replies (
            matter_id TEXT PRIMARY KEY,
            state TEXT NOT NULL CHECK (state IN ('approved', 'amend')),
            note TEXT NOT NULL DEFAULT '',
            recorded_by TEXT NOT NULL,
            recorded_utc TEXT NOT NULL
        );

        -- What the triage read in one email about the witness statement ('approved' or 'amend'), keyed by the
        -- email's message key, so the filing step can name the PDF from the same reading.
        CREATE TABLE IF NOT EXISTS statement_reply_messages (
            message_key TEXT PRIMARY KEY,
            state TEXT NOT NULL CHECK (state IN ('approved', 'amend')),
            recorded_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS matter_case_stage (
            matter_id TEXT PRIMARY KEY,
            stage TEXT NOT NULL,
            set_by TEXT NOT NULL,
            set_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS matter_case_stage_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id TEXT NOT NULL,
            at_utc TEXT NOT NULL,
            actor TEXT NOT NULL,
            old_stage TEXT,
            new_stage TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_matter_case_stage_events_matter
            ON matter_case_stage_events(matter_id, at_utc);

        -- The matter's fact sheet (matter_fact_extraction.fact_sheet_for, gh#1450): what its papers say, which paper
        -- said it, the clashes and the gaps, as JSON. One row per matter, replaced when the papers change; the
        -- fingerprint is the papers' paths and versions ('' when the model could not run, so the next run retries).
        CREATE TABLE IF NOT EXISTS matter_fact_sheets (
            matter_id TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            sheet TEXT NOT NULL,
            made_utc TEXT NOT NULL
        );
        """
    )
    for col, defn in (
        ("allow_sos_to_court_draft", "INTEGER"),
        ("sos_to_court_draft_set_at", "TEXT"),
        ("sos_to_court_draft_set_by", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE matter_permissions ADD COLUMN {col} {defn}")
        except sqlite3.OperationalError:
            pass
    for col, defn in (
        ("billing_item_id", "TEXT"),
        ("billing_deleted_utc", "TEXT"),
        ("caller", "TEXT"),
        ("caller_other", "TEXT"),
        ("time_minutes", "INTEGER"),
        ("ready_utc", "TEXT"),
        ("claimed_utc", "TEXT"),
        ("attempts", "INTEGER NOT NULL DEFAULT 0"),
        ("last_error", "TEXT"),
        ("note_kind", "TEXT"),
        ("filed_unsorted", "INTEGER"),
        ("filed_folder", "TEXT"),
        ("bundle_pages", "INTEGER"),
        ("billing_note", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE an_drafts ADD COLUMN {col} {defn}")
        except sqlite3.OperationalError:
            pass
    for col in ("letter_item_id", "note_item_id", "pair_key", "linked_draft_id", "auto_activity", "attendance_folder", "doc_other"):
        _add_column_if_missing(conn, "an_letter_meta", col, "TEXT")
    for col, defn in (("hidden_utc", "TEXT"), ("hidden_by", "TEXT NOT NULL DEFAULT ''")):
        try:
            conn.execute(f"ALTER TABLE statement_replies ADD COLUMN {col} {defn}")
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute("ALTER TABLE matter_flags ADD COLUMN reason TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE user_matter_flags ADD COLUMN reason TEXT")
    except sqlite3.OperationalError:
        pass
    _add_column_if_missing(conn, "audit_folder_flags", "kind", "TEXT NOT NULL DEFAULT 'person'")
    conn.execute("DROP INDEX IF EXISTS ux_audit_folder_flags_open")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_audit_folder_flags_open_kind ON audit_folder_flags(book, item_key, kind) WHERE cleared_at IS NULL")
    _add_column_if_missing(conn, "pipeline_events", "instance", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "pipeline_events", "links", "TEXT NOT NULL DEFAULT '[]'")
    _add_column_if_missing(conn, "pipeline_events", "actor_kind", "TEXT NOT NULL DEFAULT ''")
    for col, defn in (("armed_utc", "TEXT"), ("sends_at", "TEXT"), ("arm_note", "TEXT NOT NULL DEFAULT ''")):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pipeline_sent_watch'").fetchone():
            _add_column_if_missing(conn, "pipeline_sent_watch", col, defn)
    _add_column_if_missing(conn, "pipeline_triggers", "internet_message_id", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "removed_clients", "merged_into", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "pending_new_clients", "request_id", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "pending_new_clients", "stage", "TEXT NOT NULL DEFAULT 'done'")
    _add_column_if_missing(conn, "pending_new_clients", "working_since", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "pending_new_clients", "phone", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "pending_new_clients", "alert30_utc", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "pending_new_clients", "alert60_utc", "TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pipeline_triggers_internet_message "
        "ON pipeline_triggers(kind, internet_message_id) WHERE internet_message_id <> ''"
    )
    for col, defn in (
        ("party", "TEXT"),
        ("document_url", "TEXT"),
        ("linked_item_id", "TEXT"),
        ("schedule", "INTEGER"),
        ("tbc_category", "TEXT"),
        ("removed_utc", "TEXT"),
        ("removed_by", "TEXT"),
        ("restored_utc", "TEXT"),
        ("restored_by", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE matter_billing_items ADD COLUMN {col} {defn}")
        except sqlite3.OperationalError:
            pass
    _unique_index_unless_duplicates(
        conn, "ux_matter_billing_items_work", "matter_billing_items",
        "matter_id, work_id, COALESCE(tbc_category, category)", "work_id IS NOT NULL AND work_id <> ''",
    )
    _unique_index_unless_duplicates(conn, "ux_pending_new_clients_request", "pending_new_clients", "request_id", "request_id <> ''")
    _unique_index_unless_duplicates(conn, "ux_pipeline_service_recipients_email", "pipeline_service_recipients", "matter_id, email")
    _unique_index_unless_duplicates(conn, "ux_pipeline_amend_rounds_no", "pipeline_amend_rounds", "matter_id, round_no", "status <> 'discarded'")
    _unique_index_unless_duplicates(conn, "ux_pipeline_amend_rounds_open", "pipeline_amend_rounds", "matter_id", "status IN ('prepared', 'saved')")
    _unique_index_unless_duplicates(conn, "ux_robot_notices_open_key", "robot_notices", "dedupe_key", "resolved_utc IS NULL AND dedupe_key <> ''")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_matter_permissions_sos_to_court_draft
            ON matter_permissions(allow_sos_to_court_draft)
        """
    )
    conn.commit()


def _unique_index_unless_duplicates(conn: sqlite3.Connection, name: str, table: str, key: str, where: str = "1") -> bool:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?", (name,)).fetchone():
        return True
    duplicated = conn.execute(f"SELECT 1 FROM {table} WHERE {where} GROUP BY {key} HAVING COUNT(*) > 1 LIMIT 1").fetchone()
    if duplicated:
        _LOG.error("unique index %s not built: %s already holds duplicate rows for it", name, table)
        return False
    conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table}({key}) WHERE {where}")
    return True


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column in {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}:
        return
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise



CHANGE_LOG_TABLE = "ops_change_log"
CHANGE_LOG_ACTOR_TABLE = "ops_change_log_actor"
_CHANGE_LOG_PREFIX = "ops_change_log_"
CHANGE_LOG_COVERED = (
    "an_drafts", "client_edit_history", "client_edit_proposals", "field_review_flags",
    "matter_activity_status", "matter_audits", "matter_billing_items",
    "matter_case_stage", "matter_case_stage_events", "matter_fact_sheets", "pipeline_auto_send_dismissals", "matter_casework", "matter_category", "matter_conflict_checks", "client_email_confirmations",
    "locked_folders", "pipeline_client_nudges", "pipeline_unsigned_reminders", "pipeline_court_chasers", "matter_flags", "matter_moved_from", "matter_legal_aid", "matter_permissions", "matter_work_log", "pending_new_clients",
    "matter_file_provenance", "pipeline_sent_links",
    "pipeline_amend_rounds", "pipeline_board_removed", "pipeline_board_sunk", "pipeline_events", "pipeline_matter_mode", "pipeline_service_recipients",
    "pipeline_settings", "pipeline_step_done", "pipeline_triggers", "pipeline_wetransfer_grants", "removed_clients", "robot_notices",
    "statement_replies", "statement_reply_messages", "test_clients", "worker_casework",
    "worker_mail_alerts", "worker_mail_category", "matter_mail_category", "audit_folder_flags",
)

CHANGE_LOG_EXCLUDED = {
    "ops_change_log": "the log itself",
    "ops_change_log_actor": "the log itself",
    "activity_log_views": "an append-only record of who opened a client's Activity log, itself the record",
    "ops_schema_meta": "schema bookkeeping",
    "ms_audit_events": "a nightly copy of Microsoft's audit log, itself the record of those changes",
    "ms_signins": "a nightly copy of Microsoft's sign-in records, itself the record",
    "telegram_sent_log": "an append-only record of every Telegram message sent, itself the record",
    "user_matter_flags": "one person's own Flag and Star: personal to them, not part of the firm's audit trail",
    "pipeline_step_claims": "a lock held for the length of one step run, gone when it ends",
    "onedrive_items": "Graph index, a re-buildable mirror of OneDrive",
    "matter_onedrive_roots": "folder lookup mirrored from caseforge-clientdb matter_folder_locations (logged there) and Graph",
    "matter_markers": "cache of where a matter's letter of authority and statement were found",
    "matter_routing_context": "recomputed from the folder on every classified email",
    "matter_sos_seen": "cache of statements of service found on an earlier look",
    "held_attachment_hashes": "sha256 of each email attachment the filer saved, per matter: a rebuildable record the duplicate guard reads",
    "mail_category_meta": "when the email category feature first ran; set once, never edited",
    "pipeline_sent_watch": "the pipeline's own record of the drafts it made and when each left: ids, subject and recipients, no client data a person edits",
    "court_prep_marks": "when an email for one hearing was found in Sent Items (Court Prep): derived from the mailbox on a schedule, never edited, rebuildable",
    "pipeline_step_seen": "cache of a step's last live read, overwritten by every read",
    "matter_sync_scan": "the newest sync scan per matter, rewritten daily by the scan; an accept (which resets the baseline) is logged in the matter's activity log",
    "an_backups": "browser autosave of the attendance-note typing box; the filed note is in an_drafts",
    "form_draft_backups": "browser autosave of unsaved Client-tab and hearing edit drafts, deleted on save or discard; the saved edit is logged in its own table",
    "an_letter_meta": "what a letter note was about and its page count, keyed by draft_id with no matter_id; written once with the note, whose filing and billing line are logged (an_drafts, matter_billing_items)",
    "folder_delta_seen": "folder watcher's seen-set (a lock/dedupe table)",
    "folder_name_seen": "folder rename watch's last-seen name and parent per folder id, rebuilt from the index",
    "folder_rename_log": "append-only record of folder renames, moves and removals found in the index (names and ids only)",
    "agent_jobs": "agent job queue", "agent_job_events": "agent job queue",
    "agent_job_artifacts": "agent job queue",
    "outputs": "output-feedback telemetry", "feedback": "output-feedback telemetry",
    "derived_rules": "output-feedback telemetry",
    "runtime_activation_events": "telemetry", "runtime_activation_frequency_snapshots": "telemetry",
    "graph_api_calls": "telemetry", "runtime_event_hourly": "telemetry", "graph_call_hourly": "telemetry",
    "state_snapshots": "telemetry", "latest_state": "telemetry", "startup_scorecards": "telemetry",
    "client_search_events": "telemetry", "jsonl_events": "telemetry", "session_events": "telemetry",
    "document_field_sources": "telemetry", "model_context_events": "telemetry",
    "context_source_events": "telemetry",
}

_CHANGE_LOG_DDL = f"""
CREATE TABLE IF NOT EXISTS {CHANGE_LOG_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    table_name TEXT NOT NULL,
    op TEXT NOT NULL CHECK (op IN ('INSERT', 'UPDATE', 'DELETE')),
    pk TEXT,
    old_row TEXT,
    new_row TEXT,
    changed_columns TEXT
);
CREATE INDEX IF NOT EXISTS ix_ops_change_log_table_at ON {CHANGE_LOG_TABLE}(table_name, at);
CREATE TABLE IF NOT EXISTS {CHANGE_LOG_ACTOR_TABLE} (
    log_id INTEGER PRIMARY KEY,
    actor TEXT,
    app TEXT,
    conn_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_ops_change_log_actor_conn ON {CHANGE_LOG_ACTOR_TABLE}(conn_id);
"""

_ACTOR_ENV = "CASEFORGE_SQL_ACTOR"
_ACTOR: contextvars.ContextVar[str] = contextvars.ContextVar("ops_db_actor", default="")
_CHANGE_LOG_READY: dict[tuple[str, int, int], int] = {}


def application_name(argv0: str | None = None) -> str:
    raw = argv0 if argv0 is not None else (sys.argv[0] if sys.argv and sys.argv[0] else "")
    path = Path(raw) if raw and raw != "-c" else None
    name = f"{path.parent.name}/{path.name}" if path and path.parent.name else (path.name if path else "python")
    return "caseforge:" + "".join(ch for ch in name if ch.isprintable() and ord(ch) < 128)[:120]


def current_actor() -> str:
    actor = _ACTOR.get()
    if actor:
        return actor
    for name in ("clientdb_sql", "tools.clientdb_sql"):
        mod = sys.modules.get(name)
        getter = getattr(mod, "_ACTOR", None) if mod is not None else None
        if getter is not None:
            try:
                actor = getter.get()
            except Exception:
                actor = ""
            if actor:
                return actor
    return os.environ.get(_ACTOR_ENV, "").strip()


@contextlib.contextmanager
def acting_as(actor: str) -> Iterator[None]:
    token = _ACTOR.set(" ".join(str(actor or "").split())[:200])
    try:
        yield
    finally:
        _ACTOR.reset(token)


def set_actor(conn: sqlite3.Connection, actor: str) -> None:
    try:
        conn.execute("UPDATE temp._actor SET name = ?", (" ".join(str(actor or "").split())[:200],))
    except sqlite3.Error:
        pass


def label_connection(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS _actor (name TEXT, app TEXT, conn_id TEXT)")
        conn.execute("DELETE FROM temp._actor")
        conn.execute(
            "INSERT INTO temp._actor (name, app, conn_id) VALUES (?, ?, ?)",
            (current_actor(), application_name(), uuid.uuid4().hex[:12]),
        )
        conn.execute(
            f"CREATE TEMP TRIGGER IF NOT EXISTS _ops_change_log_actor AFTER INSERT ON main.{CHANGE_LOG_TABLE} "
            f"BEGIN INSERT INTO {CHANGE_LOG_ACTOR_TABLE} (log_id, actor, app, conn_id) "
            "SELECT NEW.id, NULLIF(name, ''), app, conn_id FROM temp._actor LIMIT 1; END"
        )
        conn.commit()
    except sqlite3.Error:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass


def connection_id(conn: sqlite3.Connection) -> str:
    try:
        row = conn.execute("SELECT conn_id FROM temp._actor LIMIT 1").fetchone()
    except sqlite3.Error:
        return ""
    return str(row[0]) if row else ""


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _json_value(ref: str, blob_capable: bool) -> str:
    if not blob_capable:
        return ref
    return f"CASE WHEN typeof({ref})='blob' THEN json_object('$blob',hex({ref})) ELSE {ref} END"


def _json_row(side: str, columns: Sequence[str], blob_columns: Iterable[str] = ()) -> str:
    blobs = set(blob_columns)
    pairs = [(c, _json_value(f"{side}.{_q(c)}", c in blobs)) for c in columns]
    head, rest = pairs[:30], pairs[30:]
    expr = "json_object(" + ",".join(f"{_lit(c)},{v}" for c, v in head) + ")"
    while rest:
        chunk, rest = rest[:30], rest[30:]
        expr = "json_insert(" + expr + "," + ",".join(f"{_lit(chr(36) + '.' + _q(c))},{v}" for c, v in chunk) + ")"
    return expr


def change_log_trigger_sql(
    table: str, columns: Sequence[str], pk: Sequence[str], blob_columns: Iterable[str] = ()
) -> dict[str, str]:
    key = list(pk) or ["rowid"]
    blobs = list(blob_columns)
    t = _q(table)

    def _pk(side: str) -> str:
        return "json_object(" + ",".join(f"{_lit(c)},{side}.{_q(c)}" for c in key) + ")"

    ins = f"INSERT INTO {CHANGE_LOG_TABLE}(table_name,op,pk,old_row,new_row,changed_columns)"
    name = _CHANGE_LOG_PREFIX + "{}_" + table
    return {
        name.format("ins"): (
            f"CREATE TRIGGER {_q(name.format('ins'))} AFTER INSERT ON {t} BEGIN {ins} "
            f"VALUES({_lit(table)},'INSERT',{_pk('NEW')},NULL,{_json_row('NEW', columns, blobs)},NULL); END"
        ),
        name.format("upd"): (
            f"CREATE TRIGGER {_q(name.format('upd'))} AFTER UPDATE ON {t} BEGIN {ins} "
            f"SELECT {_lit(table)},'UPDATE',k,o,n,(SELECT json_group_array(a.key) FROM json_each(n) a "
            "JOIN json_each(o) b ON a.key=b.key WHERE a.type IS NOT b.type OR a.value IS NOT b.value) "
            f"FROM (SELECT {_pk('OLD')} k,{_json_row('OLD', columns, blobs)} o,{_json_row('NEW', columns, blobs)} n) "
            "WHERE o IS NOT n; END"
        ),
        name.format("del"): (
            f"CREATE TRIGGER {_q(name.format('del'))} AFTER DELETE ON {t} BEGIN {ins} "
            f"VALUES({_lit(table)},'DELETE',{_pk('OLD')},{_json_row('OLD', columns, blobs)},NULL,NULL); END"
        ),
    }


def _append_only_sql() -> dict[str, str]:
    out = {}
    for log in (CHANGE_LOG_TABLE, CHANGE_LOG_ACTOR_TABLE):
        for op in ("UPDATE", "DELETE"):
            name = f"{_CHANGE_LOG_PREFIX}append_only_{op.lower()}_{log}"
            out[name] = (
                f"CREATE TRIGGER {_q(name)} BEFORE {op} ON {log} FOR EACH ROW BEGIN "
                f"SELECT RAISE(ABORT, '{log} is append-only'); END"
            )
    return out


def change_log_tables(conn: sqlite3.Connection) -> dict[str, tuple[list[str], list[str], list[str]]]:
    names = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite!_%' ESCAPE '!' ORDER BY name"
        )
    ]
    covered = set(CHANGE_LOG_COVERED)
    out: dict[str, tuple[list[str], list[str], list[str]]] = {}
    for name in names:
        if name in CHANGE_LOG_EXCLUDED:
            continue
        info = conn.execute(f"PRAGMA table_info({_q(name)})").fetchall()
        columns = [str(r[1]) for r in info]
        if name not in covered and "matter_id" not in columns:
            continue
        pk = [str(r[1]) for r in sorted((r for r in info if int(r[5]) > 0), key=lambda r: int(r[5]))]
        blobs = [str(r[1]) for r in info if not str(r[2] or "").strip() or "BLOB" in str(r[2]).upper()]
        out[name] = (columns, pk, blobs)
    return out


def _expected_change_log_triggers(conn: sqlite3.Connection) -> dict[str, str]:
    expected = _append_only_sql()
    for table, (columns, pk, blobs) in change_log_tables(conn).items():
        expected.update(change_log_trigger_sql(table, columns, pk, blobs))
    return expected


def _main_db_key(conn: sqlite3.Connection) -> tuple[str, int, int] | None:
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
    except sqlite3.Error:
        return None
    file = next((str(r[2]) for r in rows if r[1] == "main"), "")
    return _schema_key(Path(file)) if file else None


def _schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA schema_version").fetchone()[0])


def ensure_change_log(conn: sqlite3.Connection, *, force: bool = False) -> int:
    key = _main_db_key(conn)
    if not force and key is not None and _CHANGE_LOG_READY.get(key) == _schema_version(conn):
        return 0
    for statement in _CHANGE_LOG_DDL.split(";"):
        if statement.strip():
            conn.execute(statement)
    expected = _expected_change_log_triggers(conn)
    present = {
        str(r[0]): str(r[1] or "")
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND substr(name, 1, ?) = ?",
            (len(_CHANGE_LOG_PREFIX), _CHANGE_LOG_PREFIX),
        )
    }
    stale = [n for n in present if n not in expected]
    todo = {n: sql for n, sql in expected.items() if present.get(n, "").strip() != sql}
    if todo or stale:
        own = not conn.in_transaction
        if own:
            conn.execute("BEGIN IMMEDIATE")
        try:
            for name in stale + list(todo):
                conn.execute(f"DROP TRIGGER IF EXISTS {_q(name)}")
            for sql in todo.values():
                conn.execute(sql)
            if own:
                conn.commit()
        except Exception:
            if own:
                conn.rollback()
            raise
    if key is not None:
        _CHANGE_LOG_READY[key] = _schema_version(conn)
    return len(todo)


PIPELINE_TRIGGER_KINDS = ("court_reply", "sos")


def record_pipeline_trigger(
    conn: sqlite3.Connection,
    *,
    matter_id: str,
    kind: str,
    message_id: str,
    conversation_id: str = "",
    received_utc: str = "",
    match_reasons: Sequence[str] | dict[str, Any] = (),
    internet_message_id: str = "",
) -> bool:
    if kind not in PIPELINE_TRIGGER_KINDS:
        raise ValueError(f"unknown pipeline trigger kind: {kind!r}")
    mid, msg = str(matter_id or "").strip(), str(message_id or "").strip()
    if not mid or not msg:
        raise ValueError("a pipeline trigger needs a matter_id and a message_id")
    reasons = match_reasons if isinstance(match_reasons, dict) else list(match_reasons)
    cursor = conn.execute(
        "INSERT OR IGNORE INTO pipeline_triggers "
        "(matter_id, kind, message_id, conversation_id, received_utc, match_reasons, created_utc, internet_message_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            mid,
            kind,
            msg,
            str(conversation_id or ""),
            str(received_utc or ""),
            json.dumps(reasons, sort_keys=True),
            utc_now_z(),
            str(internet_message_id or "").strip(),
        ),
    )
    return cursor.rowcount == 1


def pipeline_triggers(
    conn: sqlite3.Connection,
    matter_id: str,
    *,
    kind: str | None = None,
    include_consumed: bool = False,
    include_void: bool = False,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT trigger_id, matter_id, kind, message_id, conversation_id, received_utc, match_reasons, "
        "consumed_utc, created_utc, internet_message_id FROM pipeline_triggers WHERE matter_id = ?"
    )
    params: list[Any] = [str(matter_id)]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if not include_consumed:
        sql += " AND consumed_utc IS NULL"
    rows = conn.execute(sql + " ORDER BY received_utc, trigger_id", params).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["match_reasons"] = json.loads(item.get("match_reasons") or "[]")
        except ValueError:
            item["match_reasons"] = []
        if include_void or not _trigger_void_reason(item["match_reasons"]):
            out.append(item)
    return out


def _trigger_void_reason(match_reasons: Any) -> str:
    return str(match_reasons.get("void") or "") if isinstance(match_reasons, dict) else ""


def void_pipeline_trigger(conn: sqlite3.Connection, trigger_id: int, reason: str) -> bool:
    row = conn.execute("SELECT match_reasons FROM pipeline_triggers WHERE trigger_id = ?", (int(trigger_id),)).fetchone()
    if row is None:
        return False
    try:
        reasons = json.loads(row[0] or "[]")
    except ValueError:
        reasons = []
    if not isinstance(reasons, dict):
        reasons = {"kind": reasons}
    if reasons.get("void"):
        return False
    reasons["void"] = str(reason or "void")[:80]
    conn.execute(
        "UPDATE pipeline_triggers SET match_reasons = ?, consumed_utc = COALESCE(consumed_utc, ?) WHERE trigger_id = ?",
        (json.dumps(reasons, sort_keys=True), utc_now_z(), int(trigger_id)),
    )
    return True


def consume_pipeline_trigger(conn: sqlite3.Connection, trigger_id: int) -> bool:
    cursor = conn.execute(
        "UPDATE pipeline_triggers SET consumed_utc = ? WHERE trigger_id = ? AND consumed_utc IS NULL",
        (utc_now_z(), int(trigger_id)),
    )
    return cursor.rowcount == 1


_PIPELINE_EVENT_KEYS = ("event_id", "step", "status", "summary", "by", "mode", "created_utc", "instance")


PIPELINE_STEP_CLAIM_SECONDS = 20 * 60


def claim_pipeline_step(conn: sqlite3.Connection, matter_id: str, step: str, by: str, *, now: dt.datetime | None = None) -> str:
    stamp = now or dt.datetime.now(dt.timezone.utc)
    token = uuid.uuid4().hex
    started = stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute(
        "INSERT OR IGNORE INTO pipeline_step_claims (matter_id, step, token, by_name, claimed_utc) VALUES (?, ?, ?, ?, ?)",
        (str(matter_id), str(step), token, str(by)[:80], started),
    )
    if cur.rowcount:
        conn.commit()
        return token
    old = conn.execute("SELECT token, claimed_utc FROM pipeline_step_claims WHERE matter_id = ? AND step = ?", (str(matter_id), str(step))).fetchone()
    if old is None:
        return claim_pipeline_step(conn, matter_id, step, by, now=now)
    try:
        age = (stamp - dt.datetime.strptime(str(old[1]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)).total_seconds()
    except ValueError:
        age = PIPELINE_STEP_CLAIM_SECONDS + 1
    if age <= PIPELINE_STEP_CLAIM_SECONDS:
        conn.commit()
        return ""
    cur = conn.execute(
        "UPDATE pipeline_step_claims SET token = ?, by_name = ?, claimed_utc = ? WHERE matter_id = ? AND step = ? AND token = ?",
        (token, str(by)[:80], started, str(matter_id), str(step), old[0]),
    )
    conn.commit()
    return token if cur.rowcount else ""


def release_pipeline_step(conn: sqlite3.Connection, matter_id: str, step: str, token: str) -> None:
    conn.execute("DELETE FROM pipeline_step_claims WHERE matter_id = ? AND step = ? AND token = ?", (str(matter_id), str(step), str(token)))
    conn.commit()


def log_pipeline_event(
    conn: sqlite3.Connection,
    *,
    matter_id: str,
    step: str,
    status: str,
    summary: str,
    by: str,
    mode: str,
    instance: str = "",
    links: list[dict[str, str]] | None = None,
    kind: str = "",
) -> str:
    event_id = uuid.uuid4().hex
    clean = [
        {"label": str(row.get("label") or "Open")[:80], "url": str(row.get("url") or "")[:2000]}
        for row in (links or [])
        if str((row or {}).get("url") or "").startswith("https://")
    ][:8]
    conn.execute(
        "INSERT INTO pipeline_events (event_id, matter_id, step, status, summary, by_name, mode, created_utc, instance, links, actor_kind) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event_id,
            str(matter_id),
            str(step),
            str(status),
            str(summary)[:300],
            str(by)[:80],
            str(mode),
            utc_now_z(),
            str(instance or "")[:200],
            json.dumps(clean),
            actor_kind.resolve(str(by), kind=kind),
        ),
    )
    return event_id


def last_ok_pipeline_event(
    conn: sqlite3.Connection,
    matter_id: str,
    step: str,
    *,
    instance: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT event_id, step, status, summary, by_name, mode, created_utc, instance, rowid FROM pipeline_events "
        "WHERE matter_id = ? AND step = ? AND status = 'ok' AND instance = ? "
        "ORDER BY created_utc DESC, rowid DESC LIMIT 1",
        (str(matter_id), str(step), str(instance)),
    ).fetchone()
    if row is None:
        return None
    reset = conn.execute(
        "SELECT created_utc, rowid FROM pipeline_events WHERE matter_id = ? AND (step = 'reset' OR (step = ? AND status = 'reset')) "
        "ORDER BY created_utc DESC, rowid DESC LIMIT 1",
        (str(matter_id), str(step)),
    ).fetchone()
    if reset is not None and (row[6], row[8]) < (reset[0], reset[1]):
        return None
    return dict(zip(_PIPELINE_EVENT_KEYS, tuple(row)[:8]))


def upsert_matter_routing_context(
    conn: sqlite3.Connection,
    *,
    matter_id: str,
    folder_path: str,
    root_name: str,
    folder_bucket: str,
    owner_bucket: str,
    lifecycle: str,
    attention_policy: str,
    priority: str,
    source: str,
    computed_utc: str | None = None,
) -> None:

    now = computed_utc or utc_now_z()
    conn.execute(
        """
        INSERT INTO matter_routing_context (
            matter_id, folder_path, root_name, folder_bucket, owner_bucket,
            lifecycle, attention_policy, priority, source, computed_utc,
            created_utc, updated_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(matter_id) DO UPDATE SET
            folder_path = excluded.folder_path,
            root_name = excluded.root_name,
            folder_bucket = excluded.folder_bucket,
            owner_bucket = excluded.owner_bucket,
            lifecycle = excluded.lifecycle,
            attention_policy = excluded.attention_policy,
            priority = excluded.priority,
            source = excluded.source,
            computed_utc = excluded.computed_utc,
            updated_utc = excluded.updated_utc
        """,
        (
            str(matter_id),
            normalise_graph_path(folder_path),
            str(root_name or ""),
            str(folder_bucket or "unknown"),
            str(owner_bucket or "standard_val"),
            str(lifecycle or "unknown"),
            str(attention_policy or "standard"),
            str(priority or "normal"),
            str(source or "unknown"),
            now,
            now,
            now,
        ),
    )


def _set_meta(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        """
        INSERT INTO ops_schema_meta (key, value, updated_utc)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_utc = excluded.updated_utc
        """,
        (key, json.dumps(value, ensure_ascii=False, sort_keys=True), utc_now_z()),
    )


def get_meta(key: str, default: Any = None, *, db_path: str | Path | None = None) -> Any:
    with connect(db_path) as conn:
        row = conn.execute("SELECT value FROM ops_schema_meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return default


def bump_counter(key: str, *, amount: int = 1, db_path: str | Path | None = None) -> int:
    amount = int(amount)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ops_schema_meta (key, value, updated_utc)
            VALUES (?, CAST(? AS TEXT), ?)
            ON CONFLICT(key) DO UPDATE SET
                value = CAST(CAST(ops_schema_meta.value AS INTEGER) + ? AS TEXT),
                updated_utc = excluded.updated_utc
            """,
            (key, amount, utc_now_z(), amount),
        )
        row = conn.execute("SELECT value FROM ops_schema_meta WHERE key = ?", (key,)).fetchone()
        conn.commit()
    return int(row[0])


def prune_meta(prefix: str, *, older_than_days: int, db_path: str | Path | None = None) -> int:
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max(1, int(older_than_days)))).isoformat().replace("+00:00", "Z")
    with connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM ops_schema_meta WHERE substr(key, 1, ?) = ? AND updated_utc < ?",
            (len(prefix), prefix, cutoff),
        )
        conn.commit()
        return int(cur.rowcount or 0)


def set_meta(key: str, value: Any, *, db_path: str | Path | None = None) -> None:
    with connect(db_path) as conn:
        _set_meta(conn, key, value)
        conn.commit()


def _normalise_search(value: str) -> str:
    text = str(value or "").replace("\\", "/").lower()
    text = text.replace("’", "'")
    text = re.sub(r"[^a-z0-9/._'&() -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalise_graph_path(value: str) -> str:
    return re.sub(r"/+", "/", str(value or "").replace("\\", "/")).strip("/")


def folder_name_from_path(path: str) -> str:
    cleaned = normalise_graph_path(path)
    return cleaned.rsplit("/", 1)[-1] if cleaned else ""


def root_name_from_path(path: str) -> str:
    cleaned = normalise_graph_path(path)
    marker = f"{LIVE_BASE}/"
    if marker in cleaned:
        rest = cleaned.split(marker, 1)[1]
        return rest.split("/", 1)[0]
    parts = [part for part in cleaned.split("/") if part]
    return parts[0] if parts else ""


def _row_to_onedrive_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "path": row["path"],
        "name": row["name"],
        "item_id": row["item_id"],
        "drive_id": row["drive_id"],
        "parent_item_id": row["parent_item_id"],
        "root_name": row["root_name"],
        "type": row["item_type"],
        "modified": row["modified_utc"],
        "size": row["size_bytes"],
        "deleted_at_utc": row["deleted_at_utc"],
        "last_seen_utc": row["last_seen_utc"],
    }


def _upsert_onedrive_rows(
    conn: sqlite3.Connection,
    items: Iterable[dict[str, Any]],
    *,
    root_name: str,
    default_drive_id: str,
    seen_at: str,
) -> int:
    written = 0
    for item in items:
        item_id = str(item.get("item_id") or item.get("id") or "").strip()
        drive_id = str(item.get("drive_id") or default_drive_id or "").strip()
        path = normalise_graph_path(str(item.get("path") or ""))
        name = str(item.get("name") or folder_name_from_path(path)).strip()
        item_type = str(item.get("item_type") or item.get("type") or "").strip().lower()
        if not item_id or not drive_id or not path or item_type not in {"folder", "file"}:
            continue
        resolved_root = str(item.get("root_name") or root_name or root_name_from_path(path)).strip()
        parent_item_id = str(item.get("parent_item_id") or "").strip()
        modified = str(item.get("modified_utc") or item.get("modified") or "").strip()
        size_raw = item.get("size_bytes", item.get("size"))
        try:
            size_bytes = None if size_raw is None or size_raw == "" else int(size_raw)
        except (TypeError, ValueError):
            size_bytes = None
        conn.execute(
            """
            DELETE FROM onedrive_items
            WHERE path = ? COLLATE NOCASE
              AND NOT (drive_id = ? AND item_id = ?)
            """,
            (path, drive_id, item_id),
        )
        conn.execute(
            """
            INSERT INTO onedrive_items (
                item_id, drive_id, parent_item_id, root_name, path, name, item_type,
                modified_utc, size_bytes, deleted_at_utc, last_seen_utc,
                name_normalised, path_normalised
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(drive_id, item_id) DO UPDATE SET
                parent_item_id = excluded.parent_item_id,
                root_name = excluded.root_name,
                path = excluded.path,
                name = excluded.name,
                item_type = excluded.item_type,
                modified_utc = excluded.modified_utc,
                size_bytes = excluded.size_bytes,
                -- An unchanged row keeps its stamp: the incremental RAG index selects on last_seen_utc, so
                -- restamping every row on a --full refresh re-embedded the whole tree each night (PERF-03).
                -- A row reset live by a full refresh has a deleted_at that differs from its last_seen; one that
                -- was really deleted has them equal (mark_onedrive_deleted, reset of a deleted row).
                last_seen_utc = CASE
                    WHEN (onedrive_items.deleted_at_utc IS NULL OR onedrive_items.deleted_at_utc <> onedrive_items.last_seen_utc)
                         AND onedrive_items.path = excluded.path
                         AND onedrive_items.name = excluded.name
                         AND onedrive_items.item_type = excluded.item_type
                         AND onedrive_items.modified_utc IS excluded.modified_utc
                         AND onedrive_items.size_bytes IS excluded.size_bytes
                    THEN onedrive_items.last_seen_utc
                    ELSE excluded.last_seen_utc
                END,
                deleted_at_utc = NULL,
                name_normalised = excluded.name_normalised,
                path_normalised = excluded.path_normalised
            """,
            (
                item_id,
                drive_id,
                parent_item_id,
                resolved_root,
                path,
                name,
                item_type,
                modified,
                size_bytes,
                seen_at,
                _normalise_search(name),
                _normalise_search(path),
            ),
        )
        written += 1
    return written


def upsert_onedrive_items(
    items: Iterable[dict[str, Any]],
    *,
    root_name: str = "",
    default_drive_id: str = "",
    seen_utc: str = "",
    db_path: str | Path | None = None,
) -> int:
    seen_at = seen_utc or utc_now_z()
    with connect(db_path) as conn:
        written = _upsert_onedrive_rows(
            conn, items, root_name=root_name, default_drive_id=default_drive_id, seen_at=seen_at
        )
        conn.commit()
    return written


def replace_onedrive_subtree(
    path: str,
    drive_id: str,
    items: Iterable[dict[str, Any]],
    *,
    deleted_item_ids: Iterable[str] = (),
    root_name: str = "",
    db_path: str | Path | None = None,
) -> int:
    cleaned = normalise_graph_path(path)
    if not cleaned:
        return 0
    now = utc_now_z()
    prefix = f"{cleaned}/"
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE onedrive_items
            SET deleted_at_utc = ?, last_seen_utc = ?
            WHERE drive_id = ?
              AND (path = ? COLLATE NOCASE OR (path >= ? COLLATE NOCASE AND path < ? COLLATE NOCASE))
            """,
            (now, now, str(drive_id or ""), cleaned, prefix, f"{cleaned}0"),
        )
        for item_id in deleted_item_ids:
            conn.execute(
                "UPDATE onedrive_items SET deleted_at_utc = ?, last_seen_utc = ? WHERE drive_id = ? AND item_id = ?",
                (now, now, str(drive_id or ""), str(item_id or "")),
            )
        written = _upsert_onedrive_rows(
            conn, items, root_name=root_name, default_drive_id=drive_id, seen_at=now
        )
        conn.commit()
    return written


def mark_onedrive_deleted(
    *,
    drive_id: str,
    item_id: str,
    deleted_at_utc: str = "",
    db_path: str | Path | None = None,
) -> int:
    deleted_at = deleted_at_utc or utc_now_z()
    drive = str(drive_id or "")
    with connect(db_path) as conn:
        conn.execute(
            """
            WITH RECURSIVE under_item(item_id) AS (
                SELECT ?
                UNION
                SELECT c.item_id FROM onedrive_items c
                JOIN under_item u ON c.parent_item_id = u.item_id
                WHERE c.drive_id = ?
            )
            UPDATE onedrive_items
            SET deleted_at_utc = ?, last_seen_utc = ?
            WHERE drive_id = ? AND item_id IN (SELECT item_id FROM under_item)
              AND (item_id = ? OR deleted_at_utc IS NULL)
            """,
            (str(item_id or ""), drive, deleted_at, deleted_at, drive, str(item_id or "")),
        )
        marked = int(conn.execute("SELECT changes()").fetchone()[0])
        conn.commit()
        return marked


def mark_root_deleted(root_name: str, *, db_path: str | Path | None = None) -> int:
    now = utc_now_z()
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE onedrive_items SET deleted_at_utc = ?, last_seen_utc = ? WHERE root_name = ? AND deleted_at_utc IS NULL",
            (now, now, str(root_name or "")),
        )
        conn.commit()
        return int(cur.rowcount or 0)


def reset_root_for_full_refresh(root_name: str, drive_id: str, *, db_path: str | Path | None = None) -> None:
    now = utc_now_z()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE onedrive_items
            SET deleted_at_utc = ?,
                last_seen_utc = CASE WHEN deleted_at_utc IS NULL THEN last_seen_utc ELSE ? END
            WHERE root_name = ? AND drive_id = ?
            """,
            (now, now, str(root_name or ""), str(drive_id or "")),
        )
        conn.commit()


def reset_path_for_full_refresh(path: str, drive_id: str, *, db_path: str | Path | None = None) -> None:
    cleaned = normalise_graph_path(path)
    if not cleaned:
        return
    now = utc_now_z()
    prefix = f"{cleaned}/"
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE onedrive_items
            SET deleted_at_utc = ?,
                last_seen_utc = CASE WHEN deleted_at_utc IS NULL THEN last_seen_utc ELSE ? END
            WHERE drive_id = ?
              AND (
                path = ? COLLATE NOCASE
                OR substr(path, 1, ?) = ? COLLATE NOCASE
              )
            """,
            (now, now, str(drive_id or ""), cleaned, len(prefix), prefix),
        )
        conn.commit()


def count_onedrive_items(*, include_deleted: bool = False, db_path: str | Path | None = None) -> int:
    with connect(db_path) as conn:
        where = "" if include_deleted else "WHERE deleted_at_utc IS NULL"
        row = conn.execute(f"SELECT COUNT(*) FROM onedrive_items {where}").fetchone()
        return int(row[0] if row else 0)


def list_onedrive_items(
    *,
    include_deleted: bool = False,
    limit: int = 0,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        where = "" if include_deleted else "WHERE deleted_at_utc IS NULL"
        sql = f"SELECT * FROM onedrive_items {where} ORDER BY path COLLATE NOCASE"
        params: tuple[Any, ...] = ()
        if limit:
            sql += " LIMIT ?"
            params = (max(1, int(limit)),)
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_onedrive_item(row) for row in rows]


def list_onedrive_items_under(
    prefix: str,
    *,
    folders_only: bool = False,
    include_deleted: bool = False,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    root = normalise_graph_path(prefix).rstrip("/")
    if not root:
        return []
    low = f"{root}/"
    high = f"{root}0"
    clauses = ["path >= ? COLLATE NOCASE", "path < ? COLLATE NOCASE"]
    if not include_deleted:
        clauses.append("deleted_at_utc IS NULL")
    if folders_only:
        clauses.append("item_type = 'folder'")
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM onedrive_items WHERE {' AND '.join(clauses)} ORDER BY path COLLATE NOCASE",
            (low, high),
        ).fetchall()
    return [_row_to_onedrive_item(row) for row in rows]


def list_onedrive_modified_since(
    since_utc: str,
    *,
    prefix: str = "",
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    clauses = ["deleted_at_utc IS NULL", "modified_utc >= ?"]
    params: list[Any] = [since_utc]
    root = normalise_graph_path(prefix).rstrip("/")
    if root:
        clauses += ["path >= ? COLLATE NOCASE", "path < ? COLLATE NOCASE"]
        params += [f"{root}/", f"{root}0"]
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM onedrive_items WHERE {' AND '.join(clauses)} ORDER BY path COLLATE NOCASE",
            params,
        ).fetchall()
    return [_row_to_onedrive_item(row) for row in rows]


def list_onedrive_folders(
    *,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM onedrive_items WHERE deleted_at_utc IS NULL AND item_type = 'folder' ORDER BY path COLLATE NOCASE"
        ).fetchall()
        return [_row_to_onedrive_item(row) for row in rows]


def search_onedrive_items(
    query: str,
    *,
    folders_only: bool = False,
    limit: int = 20,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    clean = _normalise_search(query)
    if not clean:
        return []
    max_rows = max(1, min(int(limit or 20), 500))
    like = f"%{clean}%"
    params: list[Any] = [like, like]
    where = "deleted_at_utc IS NULL AND (name_normalised LIKE ? OR path_normalised LIKE ?)"
    if folders_only:
        where += " AND item_type = 'folder'"
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM onedrive_items
            WHERE {where}
            ORDER BY
                CASE WHEN name_normalised = ? THEN 0 ELSE 1 END,
                length(path),
                path COLLATE NOCASE
            LIMIT ?
            """,
            (*params, clean, max_rows),
        ).fetchall()
        return [_row_to_onedrive_item(row) for row in rows]


def get_onedrive_item_by_path(path: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    wanted = normalise_graph_path(path)
    if not wanted:
        return None
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM onedrive_items
            WHERE deleted_at_utc IS NULL AND path = ? COLLATE NOCASE
            LIMIT 1
            """,
            (wanted,),
        ).fetchone()
        return _row_to_onedrive_item(row) if row else None


def list_onedrive_children(
    *,
    drive_id: str = "",
    parent_item_id: str = "",
    parent_path: str = "",
    item_type: str = "",
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    clauses = ["deleted_at_utc IS NULL"]
    params: list[Any] = []
    if drive_id:
        clauses.append("drive_id = ?")
        params.append(drive_id)
    if parent_item_id:
        clauses.append("parent_item_id = ?")
        params.append(parent_item_id)
    elif parent_path:
        parent = normalise_graph_path(parent_path)
        prefix = f"{parent}/"
        clauses.append("path LIKE ? COLLATE NOCASE")
        params.append(f"{prefix}%")
    if item_type:
        clauses.append("item_type = ?")
        params.append(item_type)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM onedrive_items WHERE {' AND '.join(clauses)} ORDER BY name COLLATE NOCASE",
            params,
        ).fetchall()
    items = [_row_to_onedrive_item(row) for row in rows]
    if parent_path and not parent_item_id:
        parent = normalise_graph_path(parent_path)
        prefix = f"{parent}/"
        items = [item for item in items if "/" not in item["path"][len(prefix):]]
    return items


def list_onedrive_subtree(root_path: str, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    root = normalise_graph_path(root_path)
    prefix = f"{root}/"
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM onedrive_items WHERE deleted_at_utc IS NULL AND path LIKE ? COLLATE NOCASE ORDER BY path COLLATE NOCASE",
            (f"{prefix}%",),
        ).fetchall()
    return [_row_to_onedrive_item(r) for r in rows]


def import_onedrive_index_json(index_path: Path, *, db_path: str | Path | None = None) -> int:
    if not index_path.exists():
        return 0
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"WARN: could not parse OneDrive index fallback {index_path}: {exc}", file=sys.stderr)
        return 0
    rows = [row for row in payload.get("items", []) or [] if isinstance(row, dict)]
    return upsert_onedrive_items(rows, db_path=db_path)


def export_onedrive_index_json(index_path: Path, *, db_path: str | Path | None = None) -> int:
    items = list_onedrive_items(db_path=db_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(
            {"generated": utc_now_z(), "items": items},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return len(items)


def upsert_matter_onedrive_root(
    *,
    matter_id: str,
    folder_item_id: str = "",
    drive_id: str = "",
    folder_path: str = "",
    root_name: str = "",
    source: str = "ops",
    verified_at: str = "",
    db_path: str | Path | None = None,
) -> None:
    mid = str(matter_id or "").strip()
    if not mid:
        return
    path = normalise_graph_path(folder_path)
    item = get_onedrive_item_by_path(path, db_path=db_path) if path else None
    resolved_drive_id = str(drive_id or (item or {}).get("drive_id") or "").strip()
    resolved_item_id = str(folder_item_id or (item or {}).get("item_id") or "").strip()
    resolved_path = path or str((item or {}).get("path") or "").strip()
    resolved_root = str(root_name or (item or {}).get("root_name") or root_name_from_path(resolved_path)).strip()
    now = utc_now_z()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO matter_onedrive_roots (
                matter_id, drive_id, folder_item_id, folder_path, root_name,
                source, verified_at, created_utc, updated_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(matter_id) DO UPDATE SET
                drive_id = COALESCE(NULLIF(excluded.drive_id, ''), drive_id),
                folder_item_id = COALESCE(NULLIF(excluded.folder_item_id, ''), folder_item_id),
                folder_path = COALESCE(NULLIF(excluded.folder_path, ''), folder_path),
                root_name = COALESCE(NULLIF(excluded.root_name, ''), root_name),
                source = excluded.source,
                verified_at = excluded.verified_at,
                updated_utc = excluded.updated_utc
            """,
            (
                mid,
                resolved_drive_id,
                resolved_item_id,
                resolved_path,
                resolved_root,
                str(source or "ops").strip(),
                verified_at or now,
                now,
                now,
            ),
        )
        conn.commit()


def _root_row_to_location(row: sqlite3.Row) -> dict[str, Any]:
    path = str(row["folder_path"] or "")
    return {
        "matter_id": row["matter_id"],
        "client_name": "",
        "matter_name": "",
        "storage_root": row["root_name"] or root_name_from_path(path),
        "site_id": "",
        "drive_id": row["drive_id"] or "",
        "matter_folder_id": row["folder_item_id"] or "",
        "matter_folder_path": path,
        "matter_folder_name": folder_name_from_path(path),
        "attendance_folder_id": "",
        "attendance_folder_name": "",
        "source": row["source"],
        "last_verified_utc": row["verified_at"],
    }


def find_matter_onedrive_roots(
    query: str = "",
    *,
    matter_id: str = "",
    limit: int = 5,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    text = " ".join(str(query or "").split())
    mid = str(matter_id or "").strip()
    if not mid and len(text) < 2:
        return []
    max_rows = max(1, min(int(limit or 5), 50))
    clauses: list[str] = []
    params: list[Any] = []
    if mid:
        clauses.append("matter_id = ?")
        params.append(mid)
    if text:
        clauses.append("(folder_path LIKE ? OR matter_id LIKE ?)")
        like = f"%{text}%"
        params.extend([like, like])
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM matter_onedrive_roots
            WHERE {' OR '.join(clauses)}
            ORDER BY CASE WHEN matter_id = ? THEN 0 ELSE 1 END, verified_at DESC
            LIMIT ?
            """,
            (*params, mid, max_rows),
        ).fetchall()
        return [_root_row_to_location(row) for row in rows]


def upsert_permission(
    matter_id: str,
    *,
    allow_email_print: bool | None | object = ...,
    allow_sos_to_court_draft: bool | None | object = ...,
    set_by: str = "operator",
    notes: str = "",
    db_path: str | Path | None = None,
) -> None:
    mid = str(matter_id or "").strip()
    if not mid:
        return
    now = utc_now_z()

    def _flag(value: bool | None | object) -> int | None | object:
        if value is ...:
            return ...
        return None if value is None else (1 if bool(value) else 0)

    fields: dict[str, Any] = {"notes": str(notes or ""), "updated_at": now}
    if allow_email_print is not ...:
        fields.update(
            {
                "allow_email_print": _flag(allow_email_print),
                "email_print_set_at": now,
                "email_print_set_by": str(set_by or "operator"),
            }
        )
    if allow_sos_to_court_draft is not ...:
        fields.update(
            {
                "allow_sos_to_court_draft": _flag(allow_sos_to_court_draft),
                "sos_to_court_draft_set_at": now,
                "sos_to_court_draft_set_by": str(set_by or "operator"),
            }
        )
    with connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM matter_permissions WHERE matter_id = ?", (mid,)).fetchone()
        if existing is None:
            payload = {
                "matter_id": mid,
                "allow_email_print": None,
                "email_print_set_at": None,
                "email_print_set_by": None,
                "allow_sos_to_court_draft": None,
                "sos_to_court_draft_set_at": None,
                "sos_to_court_draft_set_by": None,
                "notes": "",
                "updated_at": now,
            }
            payload.update(fields)
            cols = list(payload)
            conn.execute(
                f"INSERT INTO matter_permissions ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                [payload[col] for col in cols],
            )
        else:
            assignments = ", ".join(f"{col} = ?" for col in fields)
            conn.execute(
                f"UPDATE matter_permissions SET {assignments} WHERE matter_id = ?",
                [fields[col] for col in fields] + [mid],
            )
        conn.commit()


def get_permission_row(matter_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    mid = str(matter_id or "").strip()
    if not mid:
        return None
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM matter_permissions WHERE matter_id = ?", (mid,)).fetchone()
        return dict(row) if row else None


def list_permissions(*, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM matter_permissions ORDER BY matter_id").fetchall()]




def upsert_activity_status(
    matter_id: str,
    *,
    activity_status: str = "active",
    status_source: str = "manual",
    status_reason: str = "",
    effective_date: str = "",
    closing_letter_sent: bool | None = None,
    billing_pending: bool | None = None,
    billing_done: bool | None = None,
    legal_aid_pending: bool | None = None,
    legal_aid_done: bool | None = None,
    override: bool = False,
    db_path: str | Path | None = None,
) -> None:
    mid = str(matter_id or "").strip()
    if not mid:
        return
    status = str(activity_status or "active").strip().lower()
    if status not in {"active", "inactive"}:
        raise ValueError(f"invalid activity_status: {activity_status}")
    now = utc_now_z()
    with connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM matter_activity_status WHERE matter_id = ?", (mid,)).fetchone()
        if existing and int(existing["override"] or 0) and not override:
            return
        payload = dict(existing) if existing else {
            "matter_id": mid,
            "activity_status": "active",
            "status_source": status_source,
            "status_reason": "",
            "effective_date": "",
            "closing_letter_sent": 0,
            "billing_pending": 0,
            "billing_done": 0,
            "legal_aid_pending": 0,
            "legal_aid_done": 0,
            "override": 0,
            "created_utc": now,
            "updated_utc": now,
        }
        payload.update(
            {
                "activity_status": status,
                "status_source": str(status_source or "manual"),
                "status_reason": str(status_reason or ""),
                "effective_date": str(effective_date or ""),
                "override": 1 if override else int(payload.get("override") or 0),
                "updated_utc": now,
            }
        )
        for key, value in (
            ("closing_letter_sent", closing_letter_sent),
            ("billing_pending", billing_pending),
            ("billing_done", billing_done),
            ("legal_aid_pending", legal_aid_pending),
            ("legal_aid_done", legal_aid_done),
        ):
            if value is not None:
                payload[key] = 1 if value else 0
        cols = list(payload)
        if existing:
            assignments = ", ".join(f"{col} = ?" for col in cols if col != "matter_id")
            conn.execute(
                f"UPDATE matter_activity_status SET {assignments} WHERE matter_id = ?",
                [payload[col] for col in cols if col != "matter_id"] + [mid],
            )
        else:
            conn.execute(
                f"INSERT INTO matter_activity_status ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                [payload[col] for col in cols],
            )
        conn.commit()


def get_activity_status(matter_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    mid = str(matter_id or "").strip()
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM matter_activity_status WHERE matter_id = ?", (mid,)).fetchone()
        if row:
            return dict(row)
    return {
        "matter_id": mid,
        "activity_status": "active",
        "status_source": "default",
        "status_reason": "Default active until an ops activity backfill or override says otherwise.",
    }


def is_matter_active(matter_id: str, *, db_path: str | Path | None = None) -> bool:
    return str(get_activity_status(matter_id, db_path=db_path).get("activity_status") or "active") == "active"


def inactive_matter_ids(*, db_path: str | Path | None = None) -> set[str]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT matter_id FROM matter_activity_status "
            "WHERE COALESCE(NULLIF(activity_status, ''), 'active') <> 'active'"
        ).fetchall()
    return {str(row[0]).strip() for row in rows}


def _first_year_from_values(values: Sequence[str]) -> int | None:
    for value in values:
        match = re.search(r"\b(20\d{2})\b", str(value or ""))
        if match:
            return int(match.group(1))
    return None


def infer_activity_status(row: dict[str, Any], *, cutoff_year: int = 2025) -> dict[str, str]:
    values = [
        str(row.get("referral_sent_at") or ""),
        str(row.get("source_email_sent_at") or ""),
        str(row.get("created_utc") or ""),
        str(row.get("created_at") or ""),
    ]
    year = _first_year_from_values(values)
    source = "intake_date" if year else ""
    if year is None:
        year = _first_year_from_values([str(row.get("live_matter_folder") or ""), str(row.get("folder_path") or "")])
        source = "folder_year" if year else "default"
    if year is not None and year < cutoff_year:
        return {
            "activity_status": "inactive",
            "status_source": f"backfill:{source}",
            "status_reason": f"Pre-{cutoff_year} matter marked inactive for temporary ops filtering.",
            "effective_date": str(year),
        }
    return {
        "activity_status": "active",
        "status_source": f"backfill:{source}",
        "status_reason": "Default active; no pre-2025 rule matched.",
        "effective_date": str(year or ""),
    }


def backfill_activity_status(
    rows: Iterable[dict[str, Any]],
    *,
    cutoff_year: int = 2025,
    db_path: str | Path | None = None,
) -> dict[str, int]:
    counts = {"active": 0, "inactive": 0, "skipped": 0}
    for row in rows:
        matter_id = str(row.get("matter_id") or "").strip()
        if not matter_id:
            counts["skipped"] += 1
            continue
        inferred = infer_activity_status(row, cutoff_year=cutoff_year)
        upsert_activity_status(
            matter_id,
            activity_status=inferred["activity_status"],
            status_source=inferred["status_source"],
            status_reason=inferred["status_reason"],
            effective_date=inferred["effective_date"],
            db_path=db_path,
        )
        counts[inferred["activity_status"]] += 1
    return counts


def migrate_legacy_tables(
    table_names: Sequence[str],
    legacy_path: Path,
    *,
    db_path: str | Path | None = None,
    meta_key: str = "",
) -> dict[str, int]:
    if not legacy_path.exists():
        return {}
    target = resolve_ops_db_path(db_path).resolve()
    try:
        if legacy_path.resolve() == target:
            return {}
    except OSError:
        pass
    copied: dict[str, int] = {}
    with connect(target) as conn:
        if meta_key:
            existing = conn.execute("SELECT value FROM ops_schema_meta WHERE key = ?", (meta_key,)).fetchone()
            if existing:
                return {}
        conn.execute("ATTACH DATABASE ? AS legacy", (str(legacy_path),))
        try:
            for table in table_names:
                main_exists = conn.execute(
                    "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                legacy_exists = conn.execute(
                    "SELECT 1 FROM legacy.sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                if not main_exists or not legacy_exists:
                    continue
                main_cols = [str(row[1]) for row in conn.execute(f"PRAGMA main.table_info({table})").fetchall()]
                legacy_cols = [str(row[1]) for row in conn.execute(f"PRAGMA legacy.table_info({table})").fetchall()]
                cols = [col for col in main_cols if col in legacy_cols]
                if not cols:
                    continue
                col_sql = ", ".join(cols)
                cur = conn.execute(
                    f"INSERT OR IGNORE INTO main.{table} ({col_sql}) SELECT {col_sql} FROM legacy.{table}"
                )
                copied[table] = int(cur.rowcount or 0)
            if meta_key:
                _set_meta(conn, meta_key, {"legacy_path": str(legacy_path), "copied": copied})
            conn.commit()
        finally:
            conn.execute("DETACH DATABASE legacy")
    return copied


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="CaseForge operations SQLite database helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ensure-db", help="Create or upgrade the ops DB schema")
    sub.add_parser("path", help="Print the active ops DB path")

    p_lookup = sub.add_parser("lookup-onedrive", help="Search the OneDrive catalogue")
    p_lookup.add_argument("query")
    p_lookup.add_argument("--folders", action="store_true")
    p_lookup.add_argument("--limit", type=int, default=20)

    p_children = sub.add_parser("onedrive-children", help="List direct children from the OneDrive catalogue")
    p_children.add_argument("--parent-item-id", default="")
    p_children.add_argument("--parent-path", default="")
    p_children.add_argument("--type", choices=["folder", "file", ""], default="")

    args = parser.parse_args()
    if args.cmd == "ensure-db":
        print(str(ensure_database()))
        return 0
    if args.cmd == "path":
        print(str(resolve_ops_db_path()))
        return 0
    if args.cmd == "lookup-onedrive":
        print(json.dumps(search_onedrive_items(args.query, folders_only=args.folders, limit=args.limit), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "onedrive-children":
        print(
            json.dumps(
                list_onedrive_children(parent_item_id=args.parent_item_id, parent_path=args.parent_path, item_type=args.type),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
