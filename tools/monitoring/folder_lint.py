#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tools"))

_CORRESPONDENCE_RE = re.compile(r"correspondence", re.IGNORECASE)

_LAA_EVIDENCE_RE = re.compile(
    r"\blaa\b"
    r"|legal\s*aid"
    r"|gateway\s*evidence"
    r"|gateway\b"
    r"|means\s*test"
    r"|notice\s*of\s*issue"
    r"|cw\s*[1-9]\b"
    r"|civil\s*legal\s*advice",
    re.IGNORECASE,
)

_FINANCE_RE = re.compile(
    r"\binvoice\b"
    r"|fee\s*note"
    r"|fee\s*notes"
    r"|\bdisbursement\b"
    r"|\breceipt\b"
    r"|statement\s*of\s*account"
    r"|counsel.*\bfee\b"
    r"|barrister.*\bfee\b",
    re.IGNORECASE,
)

DEST_LABELS: dict[str, str] = {
    "laa_evidence": "LAA Evidence",
    "invoice_fee_notes": "Invoice and Fee Notes",
}


def is_correspondence_folder(name: str) -> bool:
    return bool(_CORRESPONDENCE_RE.search(name or ""))


def _is_file(item: dict[str, Any]) -> bool:
    return bool(item.get("file")) and not item.get("folder")


def _extension(name: str) -> str:
    return name.rpartition(".")[2].lower() if "." in name else ""


def classify_file_destination(name: str) -> str | None:
    stem = name.rpartition(".")[0] or name
    if _LAA_EVIDENCE_RE.search(stem):
        return "laa_evidence"
    if _FINANCE_RE.search(stem):
        return "invoice_fee_notes"
    return None


def lint_folder(folder_path: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    folder_name = folder_path.rstrip("/").rpartition("/")[2]
    if not is_correspondence_folder(folder_name):
        return []
    findings: list[dict[str, Any]] = []
    for item in items:
        if not _is_file(item):
            continue
        name = str(item.get("name") or "")
        ext = _extension(name)
        if ext != "pdf":
            findings.append(
                {
                    "folder": folder_path,
                    "name": name,
                    "ext": ext or "(none)",
                    "rule": "pdf_only_correspondence",
                    "detail": "Correspondence folders should hold PDFs only (mail is printed to PDF).",
                    "suggested_action": "Human review: convert to PDF if it is correspondence, else move to the right subfolder.",
                }
            )
    return findings


def lint_folder_rule2(folder_path: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    folder_name = folder_path.rstrip("/").rpartition("/")[2]
    if not is_correspondence_folder(folder_name):
        return []
    findings: list[dict[str, Any]] = []
    for item in items:
        if not _is_file(item):
            continue
        name = str(item.get("name") or "")
        ext = _extension(name)
        if ext != "pdf":
            continue
        dest_type = classify_file_destination(name)
        if dest_type is None:
            continue
        dest_label = DEST_LABELS[dest_type]
        findings.append(
            {
                "folder": folder_path,
                "name": name,
                "ext": "pdf",
                "rule": "laa_routing",
                "dest_type": dest_type,
                "detail": f"Looks like {dest_label} material filed in a Correspondence folder.",
                "suggested_action": f"Move to the '{dest_label}' subfolder.",
            }
        )
    return findings


_STATEMENT_RE = re.compile(
    r"(?:^|[.\-_ ])ws\d*(?:[.\-_ (]|$)|witness[\s._-]*statement"
    r"|\b(?:supplementary|further|oo|nmo|cao|pso|draft)[\s._-]*(?:oo[\s._-]*)?statement\b"
    r"|\bstatement\b(?![\s._-]*of[\s._-]*(?:service|truth|means|arrangements|case))",
    re.IGNORECASE,
)
_COURT_STAMP_RE = re.compile(r"seal|issued", re.IGNORECASE)
_OTHER_STATEMENT_RE = re.compile(
    r"\b(?:bank|account|mortgage|credit[\s._-]*card|card|loan|pension|benefits?|universal[\s._-]*credit|uc|pay|wages?|tax|billing|rent"
    r"|position)[\s._-]*statements?\b",
    re.IGNORECASE,
)


def is_client_statement_name(name: str) -> bool:
    return bool(_STATEMENT_RE.search(name)) and not _OTHER_STATEMENT_RE.search(name)


def lint_clients_docs(folder_path: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import graph_files

    if graph_files.folder_kind(folder_path.rstrip("/").rpartition("/")[2]).kind != "clients_docs":
        return []
    return [
        {
            "folder": folder_path,
            "name": str(i.get("name") or ""),
            "rule": "clients_docs_not_statement",
            "detail": "Client's Docs holds the client's statement only.",
            "suggested_action": "Human review: file it in its own folder (a counsel, court, police or evidence folder).",
        }
        for i in items
        if _is_file(i) and not is_client_statement_name(str(i.get("name") or ""))
    ]


def lint_statement_strays(folder_path: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import graph_files

    kind = graph_files.folder_kind(folder_path.rstrip("/").rpartition("/")[2]).kind
    if kind not in {"other_sides_docs", "court_orders"}:
        return []
    return [
        {
            "folder": folder_path,
            "name": str(i.get("name") or ""),
            "rule": "own_statement_stray",
            "detail": f"Looks like our statement in {'Other Side\'s Docs' if kind == 'other_sides_docs' else 'Court Orders'}; only the court's sealed copy belongs there.",
            "suggested_action": "Check it with court_copies.verdict (sealed or ours); if ours, move it to Client's Docs.",
        }
        for i in items
        if _is_file(i)
        and is_client_statement_name(str(i.get("name") or ""))
        and not _COURT_STAMP_RE.search(str(i.get("name") or ""))
    ]


def index_report(*, db_path: Any = None) -> dict[str, Any]:
    import hashlib

    import graph_files
    import ops_db

    with ops_db.connect(db_path) as conn:
        folders = conn.execute(
            "SELECT item_id, name, path, parent_item_id FROM onedrive_items WHERE deleted_at_utc IS NULL AND item_type = 'folder'"
        ).fetchall()
        files = conn.execute(
            "SELECT parent_item_id, name FROM onedrive_items WHERE deleted_at_utc IS NULL AND item_type = 'file'"
        ).fetchall()
    watched = {}
    for item_id, name, path, matter in folders:
        kind = graph_files.folder_kind(name).kind
        if kind in {"clients_docs", "other_sides_docs", "court_orders"}:
            watched[str(item_id)] = (str(path), str(matter))
    by_folder: dict[str, list[dict[str, Any]]] = {}
    for parent, name in files:
        if str(parent) in watched:
            by_folder.setdefault(str(parent), []).append({"name": name, "file": {"indexed": True}})
    rows: list[dict[str, str]] = []
    for item_id, items in by_folder.items():
        path, matter = watched[item_id]
        found = lint_clients_docs(path, items) + lint_statement_strays(path, items)
        for f in found:
            rows.append({"matter": hashlib.sha1(matter.encode()).hexdigest()[:8], "rule": f["rule"], "folder": path.rsplit("/", 1)[-1][:2], "name": f["name"]})
    counts: dict[str, int] = {}
    matters: dict[str, set[str]] = {}
    for r in rows:
        counts[r["rule"]] = counts.get(r["rule"], 0) + 1
        matters.setdefault(r["rule"], set()).add(r["matter"])
    return {"findings": counts, "matters": {k: len(v) for k, v in matters.items()}, "rows": rows}


ORIGIN_FILER = "mail filer"
ORIGIN_PROGRAM = "another program"
ORIGIN_PERSON = "a person"
ORIGIN_UNKNOWN = "unknown"
ORIGIN_GONE = "no longer there"
_APP_ONLY_USERS = frozenset({"", "sharepoint app", "system account"})


def _norm_path(path: str) -> str:
    return "/".join(part for part in str(path or "").replace("\\", "/").split("/") if part).lower()


def filer_register(path: Any = None) -> dict[str, dict[str, Any]]:
    from agents import email_print_archive as epa

    saved: dict[str, dict[str, Any]] = {}
    register = Path(path or epa.REGISTER_JSONL)
    if not register.is_file():
        return saved
    for line in register.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("status") != "printed":
            continue
        for dest in str(row.get("attachment_destinations") or "").split(";"):
            if dest.strip():
                saved[_norm_path(dest.strip())] = row
    return saved


def origin_of(child: dict[str, Any] | None, in_register: bool) -> tuple[str, str]:
    by = (child or {}).get("createdBy") or {}
    app = str((by.get("application") or {}).get("displayName") or "")
    user = str((by.get("user") or {}).get("displayName") or "")
    if in_register:
        return ORIGIN_FILER, app
    if user.strip().lower() not in _APP_ONLY_USERS and user.strip().lower() != app.strip().lower():
        return ORIGIN_PERSON, app
    return (ORIGIN_PROGRAM, app) if app else (ORIGIN_UNKNOWN, "")


def touched_by_a_person_since(child: dict[str, Any] | None) -> bool:
    if not child:
        return False
    user = str(((child.get("lastModifiedBy") or {}).get("user") or {}).get("displayName") or "").strip().lower()
    app = str(((child.get("lastModifiedBy") or {}).get("application") or {}).get("displayName") or "").strip().lower()
    changed = str(child.get("lastModifiedDateTime") or "")[:16] > str(child.get("createdDateTime") or "")[:16]
    return changed and user not in _APP_ONLY_USERS and user != app


def _graph_children(drive_id: str, item_id: str, token: str) -> list[dict[str, Any]]:
    import graph_files

    url = f"{graph_files.GRAPH}/drives/{drive_id}/items/{item_id}/children?$top=999&$select=id,name,createdBy,createdDateTime,lastModifiedBy,lastModifiedDateTime"
    items: list[dict[str, Any]] = []
    while url:
        payload = graph_files.graph_json(url, token)
        items.extend(payload.get("value", []))
        url = str(payload.get("@odata.nextLink") or "")
    return items


def move_plan(*, db_path: Any = None, register_path: Any = None, children: Any = None) -> dict[str, Any]:
    import graph_files
    import ops_db
    from agents import email_print_archive as epa

    if children is None:
        token = graph_files.token()
        children = lambda drive_id, item_id: _graph_children(drive_id, item_id, token)
    saved = filer_register(register_path)
    with ops_db.connect(db_path) as conn:
        folders = [dict(r) for r in conn.execute(
            "SELECT item_id, drive_id, name, path, parent_item_id FROM onedrive_items WHERE deleted_at_utc IS NULL AND item_type = 'folder'"
        )]
        files = [dict(r) for r in conn.execute(
            "SELECT item_id, name, path, parent_item_id FROM onedrive_items WHERE deleted_at_utc IS NULL AND item_type = 'file'"
        )]
    docs = {str(f["item_id"]): f for f in folders if graph_files.folder_kind(str(f["name"])).kind == "clients_docs"}
    siblings: dict[str, list[dict[str, Any]]] = {}
    for f in folders:
        siblings.setdefault(str(f["parent_item_id"]), []).append(f)
    found = [f for f in files if str(f["parent_item_id"]) in docs and not is_client_statement_name(str(f["name"]))]

    listed: dict[str, dict[str, Any]] = {}
    read_folders: set[str] = set()
    gone_folders: set[str] = set()
    unlisted = 0
    for folder_id in sorted({str(f["parent_item_id"]) for f in found}):
        try:
            for child in children(str(docs[folder_id]["drive_id"]), folder_id):
                listed[str(child.get("id"))] = child
            read_folders.add(folder_id)
        except Exception as exc:
            if "404" in str(exc) or "itemNotFound" in str(exc):
                gone_folders.add(folder_id)
            else:
                unlisted += 1

    rows: list[dict[str, Any]] = []
    for f in found:
        child = listed.get(str(f["item_id"]))
        register_row = saved.get(_norm_path(str(f["path"])))
        origin, via = origin_of(child, register_row is not None)
        if child is None and (str(f["parent_item_id"]) in gone_folders or str(f["parent_item_id"]) in read_folders):
            origin, via = ORIGIN_GONE, ""
        touched = touched_by_a_person_since(child)
        row = {
            "item_id": str(f["item_id"]), "path": str(f["path"]), "name": str(f["name"]), "origin": origin, "via": via,
            "created": str((child or {}).get("createdDateTime") or "")[:10], "touched_by_a_person_since": touched,
            "proposed_folder": "", "proposed_kind": "", "rule": "",
        }
        if origin == ORIGIN_FILER and not touched:
            folder = docs[str(f["parent_item_id"])]
            matter_path = epa.normalise_graph_path(str(folder["path"]).rsplit("/", 1)[0])
            index_items = [{"type": "folder", "path": epa.normalise_graph_path(str(s["path"])), "name": str(s["name"])} for s in siblings.get(str(folder["parent_item_id"]), [])]
            target, rule = epa.attachment_archive_target(
                message={}, attachment={"name": str(f["name"])},
                matter=epa.MatterTarget(matter_id=str(register_row.get("matter_id") or ""), canonical_name=str(register_row.get("client_name") or ""), live_matter_folder=matter_path),
                matter_path=matter_path, category=str(register_row.get("category") or ""), index_items=index_items,
                email_folder=epa.normalise_graph_path(str(register_row.get("pdf_destination") or "").rsplit("/", 1)[0]),
            )
            if target and _norm_path(target) != _norm_path(str(folder["path"])):
                row.update(proposed_folder=target, proposed_kind=graph_files.folder_kind(target.rsplit("/", 1)[-1]).kind or "unrecognised", rule=rule)
        rows.append(row)

    def tally(key: Any) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in rows:
            label = key(row)
            if label:
                out[label] = out.get(label, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    return {
        "files": len(rows),
        "folders": len({str(f["parent_item_id"]) for f in found}),
        "folders_not_listed": unlisted,
        "folders_no_longer_there": len(gone_folders),
        "origin": tally(lambda r: r["origin"]),
        "people_used": tally(lambda r: r["via"] or "(no application named)" if r["origin"] == ORIGIN_PERSON else ""),
        "programs": tally(lambda r: r["via"] if r["origin"] == ORIGIN_PROGRAM else ""),
        "filer_touched_since": sum(1 for r in rows if r["origin"] == ORIGIN_FILER and r["touched_by_a_person_since"]),
        "proposed": tally(lambda r: f"{r['proposed_kind']} ({r['rule']})" if r["proposed_folder"] else ""),
        "rows": rows,
    }


def _scan_matter(root_path: str) -> dict[str, Any]:
    import graph_files

    token = graph_files.token()
    root = graph_files.list_children(root_path, token)
    rule1_findings: list[dict[str, Any]] = []
    rule2_findings: list[dict[str, Any]] = []
    folders_scanned = 0
    for child in root.get("value", []):
        if not child.get("folder"):
            continue
        name = str(child.get("name") or "")
        if not is_correspondence_folder(name):
            continue
        sub_path = f"{root_path.rstrip('/')}/{name}"
        folders_scanned += 1
        sub_items = graph_files.list_children(sub_path, token).get("value", [])
        rule1_findings.extend(lint_folder(sub_path, sub_items))
        rule2_findings.extend(lint_folder_rule2(sub_path, sub_items))
    return {
        "root": root_path,
        "correspondence_folders_scanned": folders_scanned,
        "findings": rule1_findings,
        "rule2_findings": rule2_findings,
    }


def _emit_telemetry(root_path: str, folders: int, r1: int, r2: int) -> None:
    try:
        import os

        from telemetry_sqlite import record_runtime_event, utc_now_z

        record_runtime_event(
            {
                "timestamp": utc_now_z(),
                "event_name": "folder_lint_report",
                "runtime_label": os.getenv("CASEFORGE_RUNTIME_LABEL", ""),
                "model_label": os.getenv("CASEFORGE_MODEL_LABEL", ""),
                "command": "folder_lint",
                "files_read": [root_path],
                "files_written": [],
                "metrics": {
                    "correspondence_folders": folders,
                    "rule1_findings": r1,
                    "rule2_findings": r2,
                },
            }
        )
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Auto-print folder lint: Rule 1 (PDF-only) + Rule 2 (LAA routing)."
    )
    ap.add_argument(
        "--index",
        action="store_true",
        help="Rules 3 and 4 over every live case folder in the local index (names only, nothing downloaded or written).",
    )
    ap.add_argument(
        "--path",
        required=False,
        help="Exact OneDrive matter-root path to scan (scoped). Find it first with "
        "`python tools/graph_files.py lookup <name> --folders`.",
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--move-plan",
        action="store_true",
        help="Rule 3's files with who put each there (mail filer, another program, a person) and where today's rule would "
        "put the mail filer's own. Read only; prints counts.",
    )
    ap.add_argument("--out", default="", help="With --move-plan: write the full list (real paths) to this file, for a person to read.")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="(Owner-gated G9) Move Rule-2 files to their correct subfolders. "
        "Not yet wired — requires move_item in graph_files.py (Graph PATCH).",
    )
    args = ap.parse_args(argv)

    if args.move_plan:
        if args.apply:
            raise SystemExit("--move-plan is read only: it proposes, and a person decides.")
        plan = move_plan()
        if args.out:
            import atomic_json

            out = Path(args.out)
            atomic_json.atomic_write_json(out, plan["rows"])
            out.chmod(0o600)
        summary = {k: v for k, v in plan.items() if k != "rows"}
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"# Client's Docs move plan: {plan['files']} files that are not the client's statement, in {plan['folders']} folders")
            print(f"folders that would not list: {plan['folders_not_listed']}; folders the index lists that are no longer there: {plan['folders_no_longer_there']}")
            for title, key in (("who put it there", "origin"), ("a person, using", "people_used"), ("another program", "programs"),
                               ("mail filer's files: proposed folder (rule)", "proposed")):
                print(f"\n## {title}")
                for label, n in plan[key].items():
                    print(f"{n:6d}  {label}")
            print(f"\nmail filer's files a person has changed since (left alone): {plan['filer_touched_since']}")
        return 0
    if args.index:
        report = index_report()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print("# Folder hygiene, local index (names only)")
            for rule, n in sorted(report["findings"].items()):
                print(f"{rule}: {n} files in {report['matters'][rule]} case folders")
        return 0
    if not args.path:
        ap.error("--path is required unless --index is given")
    if args.apply:
        raise SystemExit(
            "--apply (Rule-2 moves) is owner-gated (G9) and not yet wired.\n"
            "Next step: add move_item() to tools/graph_files.py using Graph PATCH "
            "parentReference, then call it here per rule2_findings."
        )

    root_path = args.path
    report = _scan_matter(root_path)
    r1 = report["findings"]
    r2 = report["rule2_findings"]
    _emit_telemetry(root_path, report["correspondence_folders_scanned"], len(r1), len(r2))

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"# Folder lint — {root_path}")
    print(f"correspondence folders scanned: {report['correspondence_folders_scanned']}")
    print(f"Rule-1 (non-PDF in correspondence): {len(r1)}")
    print(f"Rule-2 (misrouted to correspondence): {len(r2)}\n")
    for f in r1:
        print(f"  [R1/{f['ext']}] {f['folder']}/{f['name']}")
    for f in r2:
        print(f"  [R2/{f['dest_type']}] {f['folder']}/{f['name']}  →  {f['suggested_action']}")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = REPO_ROOT / "artifacts" / f"folder-lint-{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Folder lint — {root_path}\n\n"]
    lines.append(f"folders scanned: {report['correspondence_folders_scanned']}\n\n")
    if r1:
        lines.append("## Rule 1 — non-PDF in correspondence\n\n")
        lines.extend(f"- [{f['ext']}] {f['folder']}/{f['name']}\n" for f in r1)
    if r2:
        lines.append("\n## Rule 2 — misrouted (move to correct subfolder)\n\n")
        lines.extend(
            f"- [{f['dest_type']}] {f['folder']}/{f['name']} → {f['suggested_action']}\n"
            for f in r2
        )
    out.write_text("".join(lines), encoding="utf-8")
    print(f"\n(written to {out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
