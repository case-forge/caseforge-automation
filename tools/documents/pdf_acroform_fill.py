import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter


def on_state(field_info: dict[str, Any]) -> str:
    states = field_info.get("/_States_") or ["/Yes"]
    for state in states:
        if state != "/Off":
            return state
    return "/Yes"


def field_max_lengths(reader: PdfReader) -> dict[str, int]:
    limits: dict[str, int] = {}
    for page in reader.pages:
        for annot in page.get("/Annots") or []:
            widget = annot.get_object()
            if widget.get("/Subtype") != "/Widget":
                continue
            names: list[str] = []
            max_len = None
            node = widget
            while node is not None:
                if max_len is None and "/MaxLen" in node:
                    max_len = int(node["/MaxLen"])
                if "/T" in node:
                    names.append(str(node["/T"]))
                parent = node.get("/Parent")
                node = parent.get_object() if parent is not None else None
            if max_len is not None and names:
                limits[".".join(reversed(names))] = max_len
    return limits


def fit_text(text: str, limit: int | None) -> str | None:
    if not limit or len(text) <= limit:
        return text
    squeezed = re.sub(r"[^A-Za-z0-9]", "", text)
    return squeezed if squeezed and len(squeezed) <= limit else None


def fill_acroform(
    *,
    template: Path,
    output: Path,
    facts: dict[str, Any],
    flatten: bool = False,
) -> dict[str, Any]:
    reader = PdfReader(template)
    field_info = reader.get_fields() or {}
    limits = field_max_lengths(reader)

    text_updates: dict[str, Any] = {}
    check_updates: dict[str, Any] = {}
    missing: list[str] = []
    compacted: list[str] = []
    overlong: dict[str, dict[str, int]] = {}

    for name, value in facts.items():
        info = field_info.get(name)
        if info is None:
            missing.append(name)
            continue
        if info.get("/FT") == "/Btn":
            if value:
                check_updates[name] = on_state(info)
        else:
            text = str(value).strip()
            if not text:
                continue
            fitted = fit_text(text, limits.get(name))
            if fitted is None:
                overlong[name] = {"length": len(text), "max_length": limits[name]}
                continue
            if fitted != text:
                compacted.append(name)
            text_updates[name] = fitted

    writer = PdfWriter()
    writer.append(reader)
    updates = {**text_updates, **check_updates}
    for page in writer.pages:
        writer.update_page_form_field_values(page, updates, auto_regenerate=True)

    if flatten:
        writer.update_page_form_field_values(None, {}, auto_regenerate=False, flatten=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)

    return {
        "template": str(template),
        "output": str(output),
        "text_fields": len(text_updates),
        "checkbox_fields": len(check_updates),
        "total_fields": len(updates),
        "missing_fields": sorted(missing),
        "compacted_fields": sorted(compacted),
        "overlong_fields": dict(sorted(overlong.items())),
    }
