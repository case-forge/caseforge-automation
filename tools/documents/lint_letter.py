#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from documents import lint_closing_letter as _closing
from documents import lint_mid_letter as _mid
from documents import lint_opening_letter as _opening
from documents.letters import checks as letter_checks
from documents.letters import kinds

LintResult = _opening.LintResult

MODULES: dict[str, Any] = {
    "opening": _opening,
    "closing": _closing,
    "court-outcome": _mid,
}


def resolve_kind(raw: str) -> str:
    try:
        return kinds.resolve(raw)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def lint_file(path: Path, kind: str, *, final_hearing_date=None) -> LintResult:
    kind = resolve_kind(kind)
    if kind == "closing":
        return MODULES[kind].lint_file(path, final_hearing_date=final_hearing_date)
    return MODULES[kind].lint_file(path, anchor_date=final_hearing_date)


def lint_dir(directory: Path, kind: str) -> list[LintResult]:
    kind = resolve_kind(kind)
    results = []
    for path in sorted(directory.rglob("*.docx")):
        if path.name.startswith("~$"):
            continue
        if kinds.match_filename(kind, path.name):
            results.append(lint_file(path, kind))
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Lint a client letter .docx for format and policy compliance. --kind is "
            "required and is verified against the document's own template wording."
        )
    )
    parser.add_argument(
        "--kind",
        required=True,
        metavar="{opening,closing,court-outcome}",
        help=(
            "Which letter this is. Required, no default: the wrong kind runs the "
            "wrong checks. Aliases: mid=court-outcome, ccl=opening."
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="A single .docx to lint.")
    group.add_argument("--dir", type=Path, help="Scan for .docx files of this kind.")
    parser.add_argument("--json", action="store_true", help="Output results as JSON.")
    parser.add_argument(
        "--final-hearing-date", type=str, default=None,
        help="YYYY-MM-DD, --kind closing --file only. Caps the header-date check "
        "to this date plus one month instead of requiring today's date.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    import datetime as _dt

    args = build_parser().parse_args(argv)
    kind = resolve_kind(args.kind)

    if args.final_hearing_date and (kind != "closing" or not args.file):
        build_parser().error("--final-hearing-date only applies to --kind closing --file.")
    final_hearing_date = _dt.date.fromisoformat(args.final_hearing_date) if args.final_hearing_date else None

    if args.file:
        results = [lint_file(args.file.resolve(), kind, final_hearing_date=final_hearing_date)]
    else:
        results = lint_dir(args.dir.resolve(), kind)
        if not results:
            print(
                f"No {kinds.LABELS[kind]} .docx files found in {args.dir}.",
                file=sys.stderr,
            )
            return 0

    for result in results:
        letter_checks.print_result(result, use_json=args.json)
    return 1 if any(not r.passed() for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
