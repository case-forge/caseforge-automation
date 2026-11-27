#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def flatten_content_controls(doc_path: Path, output_path: Path) -> int:
    try:
        from docx import Document
        from lxml import etree
    except ImportError as exc:
        print(f"ERROR: {exc}. Run: pip install python-docx", file=sys.stderr)
        return 1

    doc = Document(str(doc_path))

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def strip_sdt(element: etree._Element) -> None:
        for sdt in element.findall(f".//{{{W}}}sdt"):
            parent = sdt.getparent()
            if parent is None:
                continue
            idx = list(parent).index(sdt)
            content = sdt.find(f"{{{W}}}sdtContent")
            if content is not None:
                for child in list(content):
                    parent.insert(idx, child)
                    idx += 1
            parent.remove(sdt)

    strip_sdt(doc.element.body)
    for section in doc.sections:
        for hf in (section.header, section.footer,
                   section.first_page_header, section.first_page_footer,
                   section.even_page_header, section.even_page_footer):
            if hf is not None:
                try:
                    strip_sdt(hf._element)
                except Exception:
                    pass

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    print(f"Flattened: {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Flatten Word document content controls.")
    parser.add_argument("--doc", required=True, type=Path, help="Input .docx path.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output path (default: overwrites input).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    doc_path = args.doc.resolve()
    if not doc_path.exists():
        print(f"ERROR: File not found: {doc_path}", file=sys.stderr)
        return 1
    output_path = args.output.resolve() if args.output else doc_path
    if output_path == doc_path:
        tmp = doc_path.with_suffix(".flatten_tmp.docx")
        shutil.copy2(doc_path, tmp)
        rc = flatten_content_controls(tmp, doc_path)
        tmp.unlink(missing_ok=True)
        return rc
    return flatten_content_controls(doc_path, output_path)


if __name__ == "__main__":
    raise SystemExit(main())
