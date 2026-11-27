#!/usr/bin/env python3
"The misfiled-document sweep for the audit page's Folders view (gh#1815, owner 2026-11-17)."
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

_TOOLS = str(Path(__file__).resolve().parents[1])
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

try:
    import actor_kind
    import document_identity
    import ops_db
    from vergil import audit_folder_view as view
except ImportError:
    from tools import actor_kind, document_identity, ops_db
    from tools.vergil import audit_folder_view as view

RULES_PATH = Path(__file__).resolve().parents[2] / "runtime-data" / "audit-sweep-rules.json"
AUTOMATION_BY = "audit-sweep"
AGENT_BY = "AI session"
TYPE_LABELS = {
    "NOTICE_OF_ACTING": "a notice of acting", "SOS": "a statement of service", "WITNESS_STATEMENT": "a witness statement",
    "FL401": "an FL401", "C100": "a C100", "LEGAL_AID_CERTIFICATE": "a legal aid certificate",
}


def load_rules(path: Path | None = None) -> dict[str, Any]:
    data = json.loads((path or RULES_PATH).read_text(encoding="utf-8"))
    if not isinstance(data.get("folders"), list):
        raise ValueError("the rules file has no folders list")
    return data


def matchers(rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    "Every document type the rules can name: ``{key: {\"label\", \"groups\"}}``, groups being sets of words that must all be in the name."
    out: dict[str, dict[str, Any]] = {}
    try:
        import order_codes

        labels = dict(order_codes.ORDER_LABELS)
    except ImportError:
        labels = {}
    for key, sig in document_identity.document_type_signatures().items():
        label = TYPE_LABELS.get(key) or (f"a {labels[key].lower()}" if key in labels else key)
        out[key] = {"label": label, "groups": [frozenset(g) for g in sig["filename_token_groups"]]}
    for key, extra in (rules.get("extra_types") or {}).items():
        out[key] = {"label": extra.get("label", key), "groups": [frozenset(g) for g in extra["groups"]]}
    return out


def types_of(name: str, known: dict[str, dict[str, Any]]) -> set[str]:
    "The document types a file's name matches: a type matches when any one of its word groups is wholly in the name."
    tokens = document_identity.document_identity_tokens(name)
    return {key for key, m in known.items() if any(group <= tokens for group in m["groups"])}


def _folder_rule(segment: str, rules: dict[str, Any]) -> dict[str, Any] | None:
    plain = segment.replace("’", "'").casefold()
    return next((r for r in rules["folders"] if plain.startswith(str(r["prefix"]).replace("’", "'").casefold())), None)


def findings(conn: sqlite3.Connection, *, client: str | None = None, rules: dict[str, Any] | None = None) -> list[dict[str, str]]:
    "The files that look misfiled: ``{\"client\", \"path\" (below the client folder), \"folder\", \"reason\"}``, by client and path."
    rules = rules or load_rules()
    known = matchers(rules)
    base = f"{view.LIBRARY_ROOT}/{view.BOOK}/"
    prefix = f"{base}{client}/" if client else base
    try:
        paths = [r[0] for r in conn.execute(
            "SELECT path FROM onedrive_items WHERE deleted_at_utc IS NULL AND item_type = 'file' AND path LIKE ? ESCAPE '\\' ORDER BY path COLLATE NOCASE", (view._like(prefix) + "%",)
        )]
    except sqlite3.OperationalError:
        return []
    out: list[dict[str, str]] = []
    for path in paths:
        parts = path[len(base):].split("/")
        if len(parts) < 3:
            continue
        owner, folders, name = parts[0], parts[1:-1], parts[-1]
        matched = types_of(name, known)
        for segment in folders:
            rule = _folder_rule(segment, rules)
            if not rule or matched & set(rule.get("except", [])):
                continue
            bad = sorted(matched & set(rule["not_here"]))
            if bad:
                said = " and ".join(known[k]["label"] for k in bad)
                out.append({"client": owner, "path": "/".join(parts[1:]), "folder": str(rule["prefix"]), "reason": f"Named like {said}. {rule['belongs']}."})
                break
    return out


def scan(conn: sqlite3.Connection, *, write: bool, client: str | None = None, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    "Run the automation sweep. Without ``write`` nothing is written. With it, each finding gets an automation flag and the"
    found = findings(conn, client=client, rules=rules)
    summary: dict[str, Any] = {"found": len(found), "written": write, "by_folder": {}, "clients": len({f["client"] for f in found}), "cleared": 0}
    for f in found:
        summary["by_folder"][f["folder"]] = summary["by_folder"].get(f["folder"], 0) + 1
    if write:
        keep: set[str] = set()
        for f in found:
            view.set_flag(conn, client=f["client"], path=f["path"], item_type="file", flagged=True, by=AUTOMATION_BY, kind=actor_kind.AUTOMATION, note=f["reason"], commit=False)
            keep.add(view.item_key(conn, f["client"], f["path"], "file")[0])
        conn.commit()
        summary["cleared"] = view.clear_kind(conn, kind=actor_kind.AUTOMATION, by=AUTOMATION_BY, keep_keys=frozenset(keep), client=client)
    summary["findings"] = found
    return summary




def listing(conn: sqlite3.Connection, client: str) -> list[dict[str, str]]:
    "What an agent reads to judge a client folder: every item below it, with the kinds of flag it already carries."
    index = view._index(conn, client)
    flags = {f["item_key"]: [] for f in view._open_flags(conn, client=client)}
    for f in view._open_flags(conn, client=client):
        flags[f["item_key"]].append(f["kind"])
    out = []
    for info in index.values():
        kinds = sorted(set(flags.get(info.get("item_id") or "", []) + flags.get("path:" + view._key(f"{client}/{info['path']}"), [])))
        out.append({"path": info["path"].split("/", 1)[1], "type": info["type"], "flags": ",".join(kinds)})
    return out


def agent_flag(conn: sqlite3.Connection, *, client: str, path: str, reason: str, item_type: str = "file", by: str = AGENT_BY) -> dict[str, Any]:
    return view.set_flag(conn, client=client, path=path, item_type=item_type, flagged=True, by=by, kind=actor_kind.AGENT, note=reason)


def agent_unflag(conn: sqlite3.Connection, *, client: str, path: str, by: str = AGENT_BY) -> dict[str, Any]:
    return view.set_flag(conn, client=client, path=path, item_type="file", flagged=False, by=by, kind=actor_kind.AGENT)


def agent_clear(conn: sqlite3.Connection, *, client: str | None = None, by: str = AGENT_BY) -> int:
    return view.clear_kind(conn, kind=actor_kind.AGENT, by=by, client=client)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="the automation sweep; a dry run unless --write")
    s.add_argument("--write", action="store_true")
    s.add_argument("--client")
    s.add_argument("--show", action="store_true", help="also print each finding (client data: names)")
    ls = sub.add_parser("list", help="the items of a client folder, for an agent to judge")
    ls.add_argument("--client", required=True)
    f = sub.add_parser("flag", help="an agent's flag")
    f.add_argument("--client", required=True)
    f.add_argument("--path", required=True)
    f.add_argument("--reason", required=True)
    f.add_argument("--type", choices=("file", "folder"), default="file")
    u = sub.add_parser("unflag", help="clear an agent's own flag")
    u.add_argument("--client", required=True)
    u.add_argument("--path", required=True)
    c = sub.add_parser("clear-agent", help="clear every agent flag (one client's with --client)")
    c.add_argument("--client")
    args = parser.parse_args(argv)

    with ops_db.connect() as conn:
        if args.command == "scan":
            result = scan(conn, write=args.write, client=args.client)
            print(f"{'wrote' if args.write else 'dry run, nothing written:'} {result['found']} found in {result['clients']} client folders; cleared {result['cleared']} stale")
            for folder, n in sorted(result["by_folder"].items()):
                print(f"  {n:5d}  {folder}")
            if args.show:
                for item in result["findings"]:
                    print(f"{item['client']}\t{item['path']}\t{item['reason']}")
        elif args.command == "list":
            for row in listing(conn, args.client):
                print(f"{row['path']}\t{row['type']}\t{row['flags']}")
        elif args.command == "flag":
            print(agent_flag(conn, client=args.client, path=args.path, reason=args.reason, item_type=args.type))
        elif args.command == "unflag":
            print(agent_unflag(conn, client=args.client, path=args.path))
        else:
            print(f"cleared {agent_clear(conn, client=args.client)} agent flags")
    return 0


if __name__ == "__main__":
    sys.exit(main())
