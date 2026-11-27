#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import sys
from pathlib import Path


_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from documents.docx_template_fill import populate_document


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: python populate-client-docs.py <docx_path> <client_data_json>")
        return 1

    doc_path = Path(argv[1])
    data = json.loads(argv[2])

    if not doc_path.exists():
        print(f"Error: File not found: {doc_path}")
        return 1

    populate_document(doc_path, data)
    print(f"Populated: {doc_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
