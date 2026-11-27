#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import sys

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from env_bootstrap import load_repo_secrets
from graph_mail_safe_ops import GraphClient, _must, get_message_hidden_state, set_message_hidden_state
from telemetry_sqlite import record_jsonl_event, record_state_snapshot


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MONITOR_ROOT = REPO_ROOT / "telemetry"
DEFAULT_REGISTER = MONITOR_ROOT / "counsel-status-register.jsonl"
DEFAULT_INDEX = MONITOR_ROOT / "counsel-status-index.json"
DOMAIN = "counsel"
VALID_STATUSES = {
    "requested",
    "offered",
    "booked",
    "declined",
    "stood_down",
    "brief_sent",
    "bundle_sent",
}
WHITESPACE_RE = re.compile(r"\s+")
MAIL_ENV_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("GRAPH_TENANT_ID",),
    ("GRAPH_MAILBOX_UPN",),
    ("GRAPH_MAIL_CLIENT_ID", "GRAPH_CLIENT_ID"),
    ("GRAPH_MAIL_CLIENT_SECRET", "GRAPH_CLIENT_SECRET"),
)


def _env_group_present(group: Sequence[str]) -> bool:
    return any(os.getenv(key, "").strip() for key in group)


def bootstrap_runtime_env() -> List[str]:

    if all(_env_group_present(group) for group in MAIL_ENV_GROUPS):
        return []
    return load_repo_secrets(repo_root=REPO_ROOT, required_keys=())


def parse_args() -> argparse.Namespace:
    bootstrap_runtime_env()
    parser = argparse.ArgumentParser(description="Track invisible counsel status on mailbox messages.")
    parser.add_argument("--tenant-id", default=os.getenv("GRAPH_TENANT_ID", ""))
    parser.add_argument("--client-id", default=os.getenv("GRAPH_MAIL_CLIENT_ID", os.getenv("GRAPH_CLIENT_ID", "")))
    parser.add_argument("--client-secret", default=os.getenv("GRAPH_MAIL_CLIENT_SECRET", os.getenv("GRAPH_CLIENT_SECRET", "")))
    parser.add_argument("--mailbox-upn", default=os.getenv("GRAPH_MAILBOX_UPN", ""))
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--retry-base-seconds", type=float, default=0.8)
    parser.add_argument("--register-path", default=str(DEFAULT_REGISTER))
    parser.add_argument("--index-path", default=str(DEFAULT_INDEX))

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_record = sub.add_parser("record", help="Record counsel state for a hearing/message")
    p_record.add_argument("--message-id", required=True)
    p_record.add_argument("--case-no", required=True)
    p_record.add_argument("--hearing-date", required=True, help="YYYY-MM-DD")
    p_record.add_argument("--status", required=True, choices=sorted(VALID_STATUSES))
    p_record.add_argument("--hearing-time", default="")
    p_record.add_argument("--hearing-mode", default="")
    p_record.add_argument("--court", default="")
    p_record.add_argument("--client", default="")
    p_record.add_argument("--respondent", default="")
    p_record.add_argument("--chambers", default="")
    p_record.add_argument("--barrister", default="")
    p_record.add_argument("--source", default="manual")
    p_record.add_argument("--note", action="append", default=[])

    p_lookup = sub.add_parser("lookup", help="Lookup latest counsel state from the local index")
    p_lookup.add_argument("--case-no", required=True)
    p_lookup.add_argument("--hearing-date", default="", help="Optional YYYY-MM-DD")

    p_message = sub.add_parser("message-get", help="Read hidden counsel state from one message")
    p_message.add_argument("--message-id", required=True)

    return parser.parse_args()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def normalise_space(value: str) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "").strip())


def normalise_case_no(value: str) -> str:
    return normalise_space(value).upper()


def hearing_key(case_no: str, hearing_date: str) -> str:
    return f"{normalise_case_no(case_no)}|{normalise_space(hearing_date)}"


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    try:
        record_jsonl_event("counsel_status_register", str(path), row)
    except Exception:
        pass


def load_index(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"version": 1, "items": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "items": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "items": {}}
    items = payload.get("items", {})
    if not isinstance(items, dict):
        payload["items"] = {}
    payload.setdefault("version", 1)
    return payload


def write_index(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".tmp-{path.name}.{os.getpid()}"
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)
    try:
        record_state_snapshot("counsel_status_index", str(path), payload, observed_utc=utc_now())
    except Exception:
        pass


def build_record(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "schema": "caseforge.counsel-state.v1",
        "message_id": normalise_space(args.message_id),
        "case_no": normalise_case_no(args.case_no),
        "hearing_date": normalise_space(args.hearing_date),
        "hearing_time": normalise_space(args.hearing_time),
        "hearing_mode": normalise_space(args.hearing_mode),
        "court": normalise_space(args.court),
        "client": normalise_space(args.client),
        "respondent": normalise_space(args.respondent),
        "status": normalise_space(args.status),
        "chambers": normalise_space(args.chambers),
        "barrister": normalise_space(args.barrister),
        "source": normalise_space(args.source) or "manual",
        "notes": [normalise_space(item) for item in (args.note or []) if normalise_space(item)],
        "updated_utc": utc_now(),
    }


def client(args: argparse.Namespace) -> GraphClient:
    return GraphClient(
        tenant_id=_must(args.tenant_id, "GRAPH_TENANT_ID / --tenant-id"),
        client_id=_must(args.client_id, "GRAPH_MAIL_CLIENT_ID or GRAPH_CLIENT_ID / --client-id"),
        client_secret=_must(args.client_secret, "GRAPH_MAIL_CLIENT_SECRET or GRAPH_CLIENT_SECRET / --client-secret"),
        mailbox_upn=_must(args.mailbox_upn, "GRAPH_MAILBOX_UPN / --mailbox-upn"),
        max_retries=max(0, int(args.max_retries)),
        retry_base_seconds=max(0.1, float(args.retry_base_seconds)),
    )


def run_record(args: argparse.Namespace) -> int:
    if not args.allow_write:
        raise SystemExit("Write operation blocked: record counsel state. Re-run with --allow-write.")
    graph = client(args)
    record = build_record(args)
    set_message_hidden_state(graph, record["message_id"], DOMAIN, record)

    register_path = Path(args.register_path)
    index_path = Path(args.index_path)
    append_jsonl(register_path, record)

    payload = load_index(index_path)
    items = payload.setdefault("items", {})
    items[hearing_key(record["case_no"], record["hearing_date"])] = record
    write_index(index_path, payload)

    print(json.dumps({"ok": True, "record": record, "register_path": str(register_path), "index_path": str(index_path)}, indent=2, ensure_ascii=False))
    return 0


def run_lookup(args: argparse.Namespace) -> int:
    payload = load_index(Path(args.index_path))
    items = payload.get("items", {})
    if not isinstance(items, dict):
        items = {}
    case_no = normalise_case_no(args.case_no)
    hearing_date = normalise_space(args.hearing_date)
    if hearing_date:
        row = items.get(hearing_key(case_no, hearing_date))
        print(json.dumps(row or {}, indent=2, ensure_ascii=False))
        return 0 if row else 1

    matches: List[Dict[str, Any]] = []
    for row in items.values():
        if not isinstance(row, dict):
            continue
        if normalise_case_no(row.get("case_no", "")) != case_no:
            continue
        matches.append(row)
    matches.sort(key=lambda item: str(item.get("updated_utc", "")), reverse=True)
    print(json.dumps(matches[0] if matches else {}, indent=2, ensure_ascii=False))
    return 0 if matches else 1


def run_message_get(args: argparse.Namespace) -> int:
    graph = client(args)
    payload = get_message_hidden_state(graph, args.message_id, DOMAIN)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    args = parse_args()
    if args.cmd == "record":
        return run_record(args)
    if args.cmd == "lookup":
        return run_lookup(args)
    if args.cmd == "message-get":
        return run_message_get(args)
    raise SystemExit(f"Unsupported command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
