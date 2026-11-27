#!/usr/bin/env python3
"Locate the most recent hearing bundle for a matter and count its pages."

from __future__ import annotations

import datetime as dt
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import graph_files
from hearing_calendar import hearing_dates
from agwu.children import children_of


def direct_children(parent_path: str, item_type: str = "", access_token: str | None = None) -> list[dict]:
    "A folder's direct children, index first and live Graph when the index has none."
    return children_of(parent_path, item_type=item_type, allow_live_fallback=True, access_token=access_token, caller="hearing_bundle_lookup")

HEARING_FOLDER_RE = re.compile(r"\bhearing\b", re.IGNORECASE)
BUNDLE_FILE_RE = re.compile(r"\bbundle\b", re.IGNORECASE)

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%y", "%d.%m.%Y", "%d/%m/%y", "%d/%m/%Y", "%d-%m-%y", "%d-%m-%Y")


def _parse_leading_date(name: str) -> dt.date | None:
    "The date token a hearing folder name starts with, in whichever of"
    year_first = hearing_dates.year_first_start(name)
    if year_first is not None:
        return year_first[0]
    multi = hearing_dates.label_start(name)
    if multi is not None:
        return multi[0]
    match = re.match(r"^\s*([\d./-]+)", name)
    if not match:
        return None
    token = match.group(1)
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def latest_hearing_folder(matter_path: str, access_token: str | None = None) -> dict[str, Any]:
    "The most recently dated ``... Hearing - SURNAME`` folder directly"
    children = direct_children(matter_path, item_type="folder", access_token=access_token)
    hearing_folders = [row for row in children if HEARING_FOLDER_RE.search(str(row.get("name") or ""))]
    if not hearing_folders:
        return {}
    undated = dt.date.min
    hearing_folders.sort(key=lambda row: _parse_leading_date(str(row.get("name") or "")) or undated, reverse=True)
    return dict(hearing_folders[0])


def find_bundle_file(hearing_folder_path: str, access_token: str | None = None) -> dict[str, Any]:
    "The bundle PDF in a hearing folder -- the most recently modified"
    children = direct_children(hearing_folder_path, item_type="file", access_token=access_token)
    candidates = [
        row for row in children
        if BUNDLE_FILE_RE.search(str(row.get("name") or "")) and str(row.get("name") or "").lower().endswith(".pdf")
    ]
    if not candidates:
        return {}
    candidates.sort(key=lambda row: str(row.get("modified_utc") or row.get("modified") or ""), reverse=True)
    return dict(candidates[0])


def count_pdf_pages(local_path: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(local_path).pages)


def latest_bundle_page_count(matter_path: str, access_token: str | None = None) -> dict[str, Any]:
    "Find the latest hearing bundle for a matter and count its pages."
    folder = latest_hearing_folder(matter_path, access_token=access_token)
    if not folder:
        return {"ok": False, "message": f"No hearing folder found directly under {matter_path!r}."}
    bundle = find_bundle_file(str(folder.get("path") or ""), access_token=access_token)
    if not bundle:
        return {"ok": False, "message": f"No bundle PDF found in {folder.get('path')!r}."}
    with tempfile.TemporaryDirectory(prefix="caseforge-bundle-pagecount-") as tmp:
        local_path = Path(tmp) / str(bundle.get("name") or "bundle.pdf")
        try:
            graph_files.download(str(bundle.get("path") or ""), local_path, access_token=access_token)
            page_count = count_pdf_pages(local_path)
        except Exception as exc:
            return {"ok": False, "message": f"Could not read {bundle.get('name')!r} as a PDF: {exc}"}
    return {
        "ok": True,
        "hearing_folder": folder.get("path"),
        "bundle_name": bundle.get("name"),
        "bundle_path": bundle.get("path"),
        "page_count": page_count,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("matter_path", help="Absolute OneDrive path to the matter's live folder root.")
    args = parser.parse_args(argv)
    result = latest_bundle_page_count(args.matter_path)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
