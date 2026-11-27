#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import graph_files
from calendar_finder.core import DATE_TOKEN_RE, deterministic_extract, extract_attachment_text
from env_bootstrap import load_repo_secrets
from scanned_docs import scan_setting
from scanned_docs.intake_facts import DEFAULT_SCANNED_DOCS_PATH


TELEMETRY_DIR = REPO_ROOT / "telemetry" / "scanned-docs-monitor"
STATE_PATH = TELEMETRY_DIR / "state.json"
RUN_LOG_PATH = TELEMETRY_DIR / "runs.jsonl"
LATEST_PATH = TELEMETRY_DIR / "latest.json"
DEFAULT_MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
SUPPORTED_DOWNLOAD_SUFFIXES = {
    ".csv",
    ".docx",
    ".eml",
    ".htm",
    ".html",
    ".md",
    ".pdf",
    ".rtf",
    ".txt",
    ".zip",
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_now_z() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def normalise_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def sha_text(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    state = read_json(path, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("version", 1)
    state.setdefault("items", {})
    return state


def _item_kind(item: dict[str, Any]) -> str:
    if isinstance(item.get("folder"), dict):
        return "folder"
    if isinstance(item.get("file"), dict):
        return "file"
    return "item"


def _item_key(drive_id: str, item: dict[str, Any], item_path: str) -> str:
    item_id = normalise_text(item.get("id"))
    if item_id:
        return f"{drive_id}:{item_id}"
    return f"path:{sha_text(item_path)}"


def _item_record(path: str, drive_id: str, item: dict[str, Any]) -> dict[str, Any]:
    name = normalise_text(item.get("name"))
    item_path = f"{path.strip('/')}/{name}".strip("/")
    record = {
        "key": _item_key(drive_id, item, item_path),
        "id": normalise_text(item.get("id")),
        "name": name,
        "kind": _item_kind(item),
        "path": item_path,
        "size": int(item.get("size") or 0),
        "createdDateTime": normalise_text(item.get("createdDateTime")),
        "lastModifiedDateTime": normalise_text(item.get("lastModifiedDateTime")),
        "eTag": normalise_text(item.get("eTag")),
        "cTag": normalise_text(item.get("cTag")),
        "webUrl": normalise_text(item.get("webUrl")),
    }
    record["fingerprint"] = sha_text(
        {
            "name": record["name"],
            "kind": record["kind"],
            "size": record["size"],
            "lastModifiedDateTime": record["lastModifiedDateTime"],
            "eTag": record["eTag"],
            "cTag": record["cTag"],
        }
    )
    return record


def index_graph_items(path: str, drive_id: str, items: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        record = _item_record(path, drive_id, item)
        indexed[record["key"]] = record
    return indexed


def changed_fields(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    fields = ("name", "kind", "size", "lastModifiedDateTime", "eTag", "cTag")
    return [field for field in fields if previous.get(field) != current.get(field)]


def detect_changes(
    previous_items: dict[str, dict[str, Any]],
    current_items: dict[str, dict[str, Any]],
    *,
    first_run_as_new: bool = False,
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    first_run = not previous_items

    for key, current in sorted(current_items.items(), key=lambda pair: str(pair[1].get("name", "")).lower()):
        previous = previous_items.get(key)
        if previous is None:
            change_type = "new" if first_run_as_new or not first_run else "baseline"
            changes.append({"change_type": change_type, "changed_fields": [], "item": current})
            continue
        fields = changed_fields(previous, current)
        if not fields:
            continue
        change_type = "renamed" if fields == ["name"] else "modified"
        changes.append({"change_type": change_type, "changed_fields": fields, "item": current, "previous": previous})

    for key, previous in sorted(previous_items.items(), key=lambda pair: str(pair[1].get("name", "")).lower()):
        if key not in current_items:
            changes.append({"change_type": "removed", "changed_fields": [], "item": previous})

    return changes


def _parse_date_token(raw: str) -> str:
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", raw, flags=re.IGNORECASE)
    formats = (
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d %B %Y",
        "%d %b %Y",
    )
    for fmt in formats:
        try:
            return dt.datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def extract_date_tokens(text: str, *, limit: int = 20) -> list[dict[str, str]]:
    dates: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in DATE_TOKEN_RE.finditer(str(text or "")):
        raw = normalise_text(match.group(0))
        iso = _parse_date_token(raw)
        if not iso or iso in seen:
            continue
        seen.add(iso)
        try:
            weekday = dt.date.fromisoformat(iso).strftime("%A")
        except ValueError:
            weekday = ""
        dates.append({"date": iso, "weekday": weekday, "source": raw[:80]})
        if len(dates) >= limit:
            break
    return dates


def _calendar_message(item: dict[str, Any], extracted_text: str, extract_status: str) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("key") or item.get("name") or "",
        "internetMessageId": item.get("key") or item.get("id") or item.get("name") or "",
        "subject": item.get("name") or "",
        "receivedDateTime": item.get("lastModifiedDateTime") or item.get("createdDateTime") or utc_now_z(),
        "bodyPreview": item.get("name") or "",
        "body": {"contentType": "Text", "content": ""},
        "webLink": item.get("webUrl") or "",
        "_calendar_finder_attachments": [
            {
                "name": item.get("name") or "",
                "extract_status": extract_status,
                "text": extracted_text,
            }
        ],
    }


def extract_calendar_candidates_from_text(
    item: dict[str, Any],
    extracted_text: str,
    *,
    extract_status: str,
) -> dict[str, Any]:
    combined = "\n".join(part for part in (str(item.get("name") or ""), extracted_text) if part)
    date_tokens = extract_date_tokens(combined)
    extraction, model_info = deterministic_extract(_calendar_message(item, extracted_text, extract_status))
    action = normalise_text(extraction.get("action")).lower()
    candidate: dict[str, Any] = {
        "item_key": item.get("key", ""),
        "item_name": item.get("name", ""),
        "extract_status": extract_status,
        "text_chars": len(extracted_text or ""),
        "date_tokens": date_tokens,
        "hearing_candidate": action not in {"", "none"},
        "extraction": {},
        "model": model_info.get("model", ""),
    }
    if candidate["hearing_candidate"]:
        hearing_date = normalise_text(extraction.get("hearing_date"))
        hearing_weekday = ""
        if hearing_date:
            try:
                hearing_weekday = dt.date.fromisoformat(hearing_date).strftime("%A")
            except ValueError:
                hearing_weekday = ""
        candidate["extraction"] = {
            "action": action,
            "case_ref": normalise_text(extraction.get("case_ref")),
            "client_name": normalise_text(extraction.get("client_name")),
            "applicant": normalise_text(extraction.get("applicant")),
            "respondent": normalise_text(extraction.get("respondent")),
            "hearing_date": hearing_date,
            "hearing_date_weekday": hearing_weekday,
            "hearing_time": normalise_text(extraction.get("hearing_time")),
            "court": normalise_text(extraction.get("court")),
            "mode": normalise_text(extraction.get("mode")),
            "hearing_type": normalise_text(extraction.get("hearing_type")),
            "duration_minutes": int(extraction.get("duration_minutes") or 0),
            "confidence": float(extraction.get("confidence") or 0),
            "reason": normalise_text(extraction.get("reason"))[:300],
        }
    return candidate


def should_download(item: dict[str, Any], max_bytes: int) -> tuple[bool, str]:
    if item.get("kind") != "file":
        return False, "not_file"
    suffix = Path(str(item.get("name") or "")).suffix.lower()
    if suffix not in SUPPORTED_DOWNLOAD_SUFFIXES:
        return False, "unsupported"
    size = int(item.get("size") or 0)
    if size > max_bytes:
        return False, "too_large"
    return True, "ok"


def inspect_item_for_calendar(
    item: dict[str, Any],
    *,
    access_token: str,
    drive_id: str,
    max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    no_download: bool = False,
) -> dict[str, Any]:
    if no_download:
        return extract_calendar_candidates_from_text(item, "", extract_status="not_downloaded")

    ok, reason = should_download(item, max_download_bytes)
    if not ok:
        return extract_calendar_candidates_from_text(item, "", extract_status=reason)

    try:
        raw = graph_files.graph_bytes(graph_files.item_url(drive_id, str(item.get("path") or "")) + ":/content", access_token)
    except Exception as exc:
        result = extract_calendar_candidates_from_text(item, "", extract_status="download_failed")
        result["error"] = str(exc)[:300]
        return result

    text, status = extract_attachment_text(str(item.get("name") or ""), raw)
    return extract_calendar_candidates_from_text(item, text, extract_status=status)


def _safe_change_for_log(change: dict[str, Any]) -> dict[str, Any]:
    item = change.get("item") or {}
    previous = change.get("previous") or {}
    safe = {
        "change_type": change.get("change_type", ""),
        "changed_fields": list(change.get("changed_fields") or []),
        "item": {
            "key": item.get("key", ""),
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "kind": item.get("kind", ""),
            "path": item.get("path", ""),
            "size": item.get("size", 0),
            "createdDateTime": item.get("createdDateTime", ""),
            "lastModifiedDateTime": item.get("lastModifiedDateTime", ""),
            "webUrl": item.get("webUrl", ""),
        },
    }
    if previous:
        safe["previous"] = {
            "name": previous.get("name", ""),
            "size": previous.get("size", 0),
            "lastModifiedDateTime": previous.get("lastModifiedDateTime", ""),
        }
    return safe


def _runtime_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    counts = summary.get("change_counts") or {}
    return {
        "status": summary.get("status", ""),
        "path": summary.get("path", ""),
        "item_count": summary.get("item_count", 0),
        "file_count": summary.get("file_count", 0),
        "new_count": counts.get("new", 0),
        "modified_count": counts.get("modified", 0),
        "renamed_count": counts.get("renamed", 0),
        "removed_count": counts.get("removed", 0),
        "baseline_count": counts.get("baseline", 0),
        "calendar_candidate_count": summary.get("calendar_candidate_count", 0),
        "date_token_item_count": summary.get("date_token_item_count", 0),
        "dry_run": summary.get("dry_run", False),
    }


def record_runtime(summary: dict[str, Any], *, state_path: Path, run_log_path: Path, latest_path: Path) -> None:
    try:
        from telemetry_sqlite import record_runtime_event, record_state_snapshot

        files_written = [] if summary.get("dry_run") else [str(state_path), str(run_log_path), str(latest_path)]
        record_runtime_event(
            {
                "timestamp": utc_now_z(),
                "event_name": "scanned_docs_monitor",
                "runtime_label": os.getenv("CASEFORGE_RUNTIME_LABEL", ""),
                "model_label": os.getenv("CASEFORGE_MODEL_LABEL", ""),
                "command": "python3 tools/scanned_docs/scanned_docs_monitor.py",
                "files_read": [f"Graph:{summary.get('path', DEFAULT_SCANNED_DOCS_PATH)}", str(state_path)],
                "files_written": files_written,
                "sections_skipped": summary.get("sections_skipped", []),
                "metrics": _runtime_metrics(summary),
            }
        )
        if not summary.get("dry_run"):
            record_state_snapshot(
                "scanned_docs_monitor_latest",
                str(latest_path),
                _runtime_metrics(summary),
                observed_utc=str(summary.get("created_utc") or utc_now_z()),
            )
    except Exception:
        pass


def run_monitor(args: argparse.Namespace) -> dict[str, Any]:
    path = normalise_text(getattr(args, "path", "") or scan_setting.scanned_docs_path())
    state_path = Path(getattr(args, "state_path", "") or STATE_PATH)
    run_log_path = Path(getattr(args, "run_log_path", "") or RUN_LOG_PATH)
    latest_path = Path(getattr(args, "latest_path", "") or LATEST_PATH)
    max_download_bytes = max(0, int(getattr(args, "max_download_bytes", DEFAULT_MAX_DOWNLOAD_BYTES) or 0))
    max_files = max(1, int(getattr(args, "max_files", 250) or 250))
    dry_run = bool(getattr(args, "dry_run", False))

    state = load_state(state_path)
    access_token = graph_files.token()
    listing = graph_files.list_children(path, access_token=access_token)
    drive_id = str(listing.get("drive_id") or "")
    raw_items = [row for row in listing.get("value", []) or [] if isinstance(row, dict)]
    if len(raw_items) > max_files:
        raw_items = raw_items[:max_files]
    current_items = index_graph_items(path, drive_id, raw_items)
    previous_items = state.get("items") if isinstance(state.get("items"), dict) else {}
    changes = detect_changes(previous_items, current_items, first_run_as_new=bool(getattr(args, "first_run_as_new", False)))

    inspect_types = {"baseline", "new", "modified", "renamed"}
    inspections: list[dict[str, Any]] = []
    sections_skipped: list[str] = []
    if bool(getattr(args, "skip_calendar_extraction", False)):
        sections_skipped.append("calendar_extraction")
    else:
        for change in changes:
            if change.get("change_type") not in inspect_types:
                continue
            item = change.get("item") or {}
            if not isinstance(item, dict):
                continue
            inspections.append(
                inspect_item_for_calendar(
                    item,
                    access_token=access_token,
                    drive_id=drive_id,
                    max_download_bytes=max_download_bytes,
                    no_download=bool(getattr(args, "no_download", False)),
                )
            )

    change_counts = Counter(str(change.get("change_type") or "unknown") for change in changes)
    calendar_candidates = [item for item in inspections if item.get("hearing_candidate")]
    date_token_items = [item for item in inspections if item.get("date_tokens")]
    created = utc_now_z()
    summary = {
        "status": "ok",
        "created_utc": created,
        "path": path,
        "drive_id_hash": sha_text(drive_id),
        "dry_run": dry_run,
        "item_count": len(current_items),
        "file_count": sum(1 for item in current_items.values() if item.get("kind") == "file"),
        "folder_count": sum(1 for item in current_items.values() if item.get("kind") == "folder"),
        "change_count": len(changes),
        "change_counts": dict(sorted(change_counts.items())),
        "calendar_candidate_count": len(calendar_candidates),
        "date_token_item_count": len(date_token_items),
        "sections_skipped": sections_skipped,
        "changes": [_safe_change_for_log(change) for change in changes],
        "calendar_inspections": inspections,
        "calendar_candidates": calendar_candidates,
    }

    if not dry_run:
        state.update(
            {
                "version": 1,
                "path": path,
                "last_run_utc": created,
                "drive_id_hash": summary["drive_id_hash"],
                "items": current_items,
            }
        )
        write_json(state_path, state)
        write_json(latest_path, summary)
        append_jsonl(run_log_path, summary)

    record_runtime(summary, state_path=state_path, run_log_path=run_log_path, latest_path=latest_path)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Scanned Docs monitor.")
    parser.add_argument("--path", default="", help="Folder to list (default: the Settings-menu value, else CASEFORGE_SCANNED_DOCS_PATH, else the built-in default)")
    parser.add_argument("--state-path", default=str(STATE_PATH))
    parser.add_argument("--run-log-path", default=str(RUN_LOG_PATH))
    parser.add_argument("--latest-path", default=str(LATEST_PATH))
    parser.add_argument("--max-download-bytes", type=int, default=DEFAULT_MAX_DOWNLOAD_BYTES)
    parser.add_argument("--max-files", type=int, default=250)
    parser.add_argument("--no-download", action="store_true", help="Do not download file content; inspect filenames only.")
    parser.add_argument("--skip-calendar-extraction", action="store_true", help="List and diff only.")
    parser.add_argument("--first-run-as-new", action="store_true", help="Treat every current item as new when no state file exists.")
    parser.add_argument("--dry-run", action="store_true", help="Do not update state or JSONL logs.")
    parser.add_argument("--json", action="store_true", help="Print the full summary JSON.")
    parser.add_argument("--auto", action="store_true", help="No-op marker for scheduled runs.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_repo_secrets(
        repo_root=REPO_ROOT,
        required_keys=("GRAPH_TENANT_ID", "GRAPH_FILES_CLIENT_ID", "GRAPH_FILES_CLIENT_SECRET"),
    )
    args = build_parser().parse_args(argv)
    summary = run_monitor(args)
    if bool(getattr(args, "json", False)):
        print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        counts = summary.get("change_counts") or {}
        print(
            "scanned-docs-monitor "
            f"status={summary.get('status')} "
            f"items={summary.get('item_count')} "
            f"new={counts.get('new', 0)} "
            f"modified={counts.get('modified', 0)} "
            f"renamed={counts.get('renamed', 0)} "
            f"removed={counts.get('removed', 0)} "
            f"baseline={counts.get('baseline', 0)} "
            f"calendar_candidates={summary.get('calendar_candidate_count')} "
            f"date_token_items={summary.get('date_token_item_count')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
