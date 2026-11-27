#!/usr/bin/env python3

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _strip_braces(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("{{") and text.endswith("}}"):
        return text[2:-2].strip()
    return text


def _expanded_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    expanded: dict[str, Any] = {}
    for key, value in data.items():
        raw = str(key)
        bare = _strip_braces(raw)
        expanded[raw] = value
        expanded[bare] = value
        expanded[f"{{{bare}}}"] = value
        expanded[f"{{{{{bare}}}}}"] = value
    return expanded


def _replacement_items(data: Mapping[str, Any]) -> list[tuple[str, Any]]:
    expanded = _expanded_mapping(data)
    items = [(key, value) for key, value in expanded.items() if key and not isinstance(value, list)]
    return sorted(
        items,
        key=lambda item: (
            -len(item[0]),
            0 if item[0].startswith("{{") else 1 if item[0].startswith("{") else 2,
            item[0],
        ),
    )


def _value_for_label(label: str, data: Mapping[str, Any]) -> tuple[bool, Any]:
    expanded = _expanded_mapping(data)
    bare = _strip_braces(label)
    for key in (label, bare, f"{{{bare}}}", f"{{{{{bare}}}}}"):
        if key in expanded:
            return True, expanded[key]
    return False, ""


def replace_placeholder_in_runs(runs, placeholder: str, value: Any) -> bool:
    if not runs:
        return False

    full_text = "".join(run.text for run in runs)
    if placeholder not in full_text:
        return False

    replacement = str(value)
    start = full_text.find(placeholder)
    while start != -1:
        end = start + len(placeholder)
        positions = []
        cursor = 0
        for idx, run in enumerate(runs):
            run_text = run.text
            run_end = cursor + len(run_text)
            if run_text and not (run_end <= start or cursor >= end):
                positions.append((idx, cursor, run_end))
            cursor = run_end

        if not positions:
            break

        start_idx, start_run_start, _ = positions[0]
        end_idx, end_run_start, _ = positions[-1]

        start_run = runs[start_idx]
        end_run = runs[end_idx]

        prefix = start_run.text[: max(0, start - start_run_start)]
        suffix = end_run.text[max(0, end - end_run_start) :]

        start_run.text = prefix + replacement + suffix
        for idx, _, _ in positions[1:]:
            runs[idx].text = ""

        full_text = "".join(run.text for run in runs)
        start = full_text.find(placeholder)

    return True


def replace_placeholder_in_paragraph(paragraph, placeholder: str, value: Any) -> bool:
    return replace_placeholder_in_runs(paragraph.runs, placeholder, value)


def _content_control_label(sdt) -> str:
    sdt_pr = sdt.find(qn("w:sdtPr"))
    if sdt_pr is None:
        return ""
    for name in ("w:tag", "w:alias"):
        node = sdt_pr.find(qn(name))
        if node is not None:
            value = node.get(qn("w:val"))
            if value:
                return value
    return ""


def _clear_children(element) -> None:
    for child in list(element):
        element.remove(child)


def _paragraph(text: str = "", *, bold: bool = False, pPr=None):
    p = OxmlElement("w:p")
    if pPr is not None:
        p.append(deepcopy(pPr))
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), "Arial")
    fonts.set(qn("w:hAnsi"), "Arial")
    fonts.set(qn("w:cs"), "Arial")
    rPr.append(fonts)
    size = OxmlElement("w:sz")
    size.set(qn("w:val"), "24")
    rPr.append(size)
    size_cs = OxmlElement("w:szCs")
    size_cs.set(qn("w:val"), "24")
    rPr.append(size_cs)
    if bold:
        rPr.append(OxmlElement("w:b"))
    r.append(rPr)
    t = OxmlElement("w:t")
    t.set(XML_SPACE, "preserve")
    t.text = str(text)
    r.append(t)
    p.append(r)
    return p


def _normalise_block_value(value: Any) -> list[tuple[str, bool]]:
    if isinstance(value, list):
        items = value
    else:
        items = str(value).splitlines() or [""]

    result = []
    for item in items:
        if isinstance(item, dict):
            result.append((str(item.get("text", "")), bool(item.get("bold", False))))
        else:
            result.append((str(item), False))
    return result


def _replace_content_control(sdt, value: Any) -> bool:
    content = sdt.find(qn("w:sdtContent"))
    if content is None:
        return False

    direct_paragraphs = [child for child in content if child.tag == qn("w:p")]
    is_block = bool(direct_paragraphs) and len(list(content)) == len(direct_paragraphs)
    block_value = _normalise_block_value(value)

    if is_block and (len(block_value) > 1 or any(bold for _, bold in block_value)):
        base_ppr = direct_paragraphs[0].find(qn("w:pPr")) if direct_paragraphs else None
        _clear_children(content)
        for text, bold in block_value:
            content.append(_paragraph(text, bold=bold, pPr=base_ppr))
        return True

    text_nodes = content.findall(".//" + qn("w:t"))
    if not text_nodes:
        return False
    text_nodes[0].text = str(value)
    text_nodes[0].set(XML_SPACE, "preserve")
    for node in text_nodes[1:]:
        node.text = ""
    return True


def replace_content_controls(doc, data: Mapping[str, Any]) -> int:
    replaced = 0
    for sdt in doc.element.findall(".//" + qn("w:sdt")):
        label = _content_control_label(sdt)
        found, value = _value_for_label(label, data)
        if label and found and _replace_content_control(sdt, value):
            replaced += 1
    return replaced


def _split_multiline_placeholders(doc, replacements) -> None:
    for key, value in replacements:
        lines = [line for line in str(value).splitlines() if line.strip()]
        if not key or len(lines) < 2:
            continue
        for paragraph in list(doc.paragraphs):
            if paragraph.text.strip() != key:
                continue
            for line in reversed(lines[1:]):
                clone = deepcopy(paragraph._p)
                paragraph._p.addnext(clone)
                for i, node in enumerate(clone.iter(qn("w:t"))):
                    node.text = line if i == 0 else ""
            for i, node in enumerate(paragraph._p.iter(qn("w:t"))):
                node.text = lines[0] if i == 0 else ""


_IF_BLOCK_RE = re.compile(r"\{\{IF:([A-Za-z0-9_]+)\}\}(.*?)\{\{/IF\}\}", re.DOTALL)


def _all_paragraphs(doc) -> list:
    found = list(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                found.extend(cell.paragraphs)
    return found


def apply_conditionals(doc, data: Mapping[str, Any]) -> int:
    removed = 0
    for paragraph in _all_paragraphs(doc):
        emptied = False
        while True:
            match = _IF_BLOCK_RE.search(paragraph.text)
            if match is None:
                break
            found, value = _value_for_label(match.group(1), data)
            if found and str(value).strip():
                replace_placeholder_in_paragraph(paragraph, "{{IF:" + match.group(1) + "}}", "")
                replace_placeholder_in_paragraph(paragraph, "{{/IF}}", "")
            else:
                replace_placeholder_in_paragraph(paragraph, match.group(0), "")
                removed += 1
                emptied = True
        element = paragraph._p
        if emptied and not paragraph.text.strip() and element.getparent() is not None and element.getparent().tag == qn("w:body"):
            following = element.getnext()
            if following is not None and following.tag == qn("w:p") and not "".join(following.itertext()).strip():
                following.getparent().remove(following)
            element.getparent().remove(element)
    return removed


def populate_docx_template(template_path: Path | str, output_path: Path | str, data: Mapping[str, Any]) -> Path:
    source = Path(template_path)
    output = Path(output_path)
    doc = Document(source)
    expanded = _expanded_mapping(data)
    replacements = _replacement_items(data)

    apply_conditionals(doc, data)
    replace_content_controls(doc, expanded)
    _split_multiline_placeholders(doc, replacements)

    for paragraph in doc.paragraphs:
        for key, value in replacements:
            if key and key in paragraph.text:
                replace_placeholder_in_paragraph(paragraph, key, value)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for key, value in replacements:
                    if key and key in cell.text:
                        for paragraph in cell.paragraphs:
                            replace_placeholder_in_paragraph(paragraph, key, value)

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)
    return output


def populate_document(doc_path: Path | str, data: Mapping[str, Any]) -> Path:
    path = Path(doc_path)
    return populate_docx_template(path, path, data)


def remove_block_if_empty(doc, start_marker: str, end_marker: str, keep: bool) -> bool:
    paragraphs = doc.paragraphs
    start_idx = end_idx = None
    for i, paragraph in enumerate(paragraphs):
        if start_idx is None and paragraph.text.strip() == start_marker:
            start_idx = i
        elif start_idx is not None and paragraph.text.strip() == end_marker:
            end_idx = i
            break
    if start_idx is None or end_idx is None:
        return False
    targets = paragraphs[start_idx : end_idx + 1] if not keep else [paragraphs[start_idx], paragraphs[end_idx]]
    for paragraph in targets:
        element = paragraph._element
        element.getparent().remove(element)
    return True


SIGNATURE_BLOCK_LINES = (
    "SIGNED:______________________________",
    "NAME: _______________________________",
    "DATE:________________________________",
)


def replace_signature_lines(doc, labels: Sequence[str] = ("signed", "dated")) -> bool:
    wanted = {label.lower() for label in labels}
    matches = [p for p in doc.paragraphs if re.sub(r"[\s.:_…-]+$", "", p.text.strip()).lower() in wanted]
    if not matches:
        return False
    model = matches[0]._p
    for text in SIGNATURE_BLOCK_LINES:
        clone = deepcopy(model)
        for r in clone.findall(qn("w:r")):
            for t in r.findall(qn("w:t")):
                t.text = ""
        first_run = clone.find(qn("w:r"))
        first_run.find(qn("w:t")).text = text
        for extra in clone.findall(qn("w:r"))[1:]:
            clone.remove(extra)
        rpr = first_run.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            first_run.insert(0, rpr)
        if rpr.find(qn("w:b")) is None:
            rpr.insert(0, OxmlElement("w:b"))
        matches[0]._p.addprevious(clone)
    for paragraph in matches:
        paragraph._p.getparent().remove(paragraph._p)
    lines = [p for p in doc.paragraphs if p.text in SIGNATURE_BLOCK_LINES]
    for paragraph in lines[:-1]:
        paragraph.paragraph_format.keep_with_next = True
    return True
