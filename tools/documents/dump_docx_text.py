#!/usr/bin/env python3
"Print the plain text of a downloaded .docx/.pdf source document to stdout."
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from documents.audit_opening_letter_sources import read_text_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Path to a .docx or .pdf file")
    args = parser.parse_args(argv)
    print(read_text_file(args.path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
