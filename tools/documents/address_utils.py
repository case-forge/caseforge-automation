#!/usr/bin/env python3
from __future__ import annotations

import re


POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
LOW_VALUE_ADDRESS_PARTS = {
    "england",
    "united kingdom",
    "uk",
    "great britain",
    "gb",
    "wales",
    "scotland",
    "northern ireland",
}


def clean_text(value: str) -> str:
    return " ".join(str(value or "").split())


def split_address_parts(raw_lines: list[str]) -> list[str]:
    parts: list[str] = []
    for line in raw_lines:
        for part in re.split(r"\s*,\s*", str(line or "")):
            part = clean_text(part)
            if part:
                parts.append(part)
    return parts


def normalise_postal_address_lines(raw_lines: list[str], max_lines: int = 4) -> list[str]:
    parts = split_address_parts(raw_lines)
    if len(parts) <= max_lines:
        return parts

    postcode_part = next((part for part in parts if POSTCODE_RE.search(part)), "")
    if not postcode_part:
        return parts[:max_lines]

    filtered = [
        part for part in parts
        if clean_text(part).lower().strip(".") not in LOW_VALUE_ADDRESS_PARTS
    ]
    if len(filtered) <= max_lines:
        return filtered

    postcode_part = next((part for part in filtered if POSTCODE_RE.search(part)), postcode_part)
    non_postcode = [part for part in filtered if part != postcode_part]
    return non_postcode[: max_lines - 1] + [postcode_part]


_UK_WORD = r"(?:U\.?K\.?|United\s+Kingdom)"
_UK_SUFFIX_RE = re.compile(r"(?:[\s,]+|^)" + _UK_WORD + r"[\s,.]*$", re.IGNORECASE)
_UK_ANYWHERE_RE = re.compile(r"\b" + _UK_WORD + r"(?![\w])", re.IGNORECASE)


_UK_BEFORE_POSTCODE_RE = re.compile(
    r"[\s,]+" + _UK_WORD + r"(?=[\s,]+[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b)", re.IGNORECASE
)


def strip_uk_label(text: str) -> str:
    return strip_uk_suffix(_UK_BEFORE_POSTCODE_RE.sub(",", text))


def strip_uk_suffix(text: str) -> str:
    out = text.rstrip()
    while True:
        new = _UK_SUFFIX_RE.sub("", out).rstrip(" ,")
        if new == out:
            return out
        out = new


def clean_address_lines(lines: list[str]) -> list[str] | None:
    cleaned: list[str] = []
    for line in lines:
        line = (line or "").strip()
        if not line:
            continue
        line = strip_uk_suffix(line)
        if not line:
            continue
        if _UK_ANYWHERE_RE.search(line):
            return None
        cleaned.append(line)
    return cleaned


def is_bare_country(text: str) -> bool:
    parts = split_address_parts([str(text or "")])
    return bool(parts) and all(part.lower().strip(".") in LOW_VALUE_ADDRESS_PARTS for part in parts)


def normalise_address_text(text: str) -> str:
    text = str(text or "")
    if not text.strip() or is_bare_country(text):
        return ""
    stripped = strip_uk_label(text)
    return stripped if stripped != text.rstrip() else text


def normalise_address_line_values(lines: list[str]) -> list[str]:
    cleaned = clean_address_lines(list(lines))
    if cleaned is None:
        return list(lines)
    if cleaned == [str(line or "").strip() for line in lines if str(line or "").strip()]:
        return list(lines)
    return (cleaned + [""] * len(lines))[: len(lines)]


STREET_SUFFIX_RE = re.compile(
    r"^(.*\b(?:road|rd|street|lane|avenue|ave|close|drive|way|court|crescent|gardens|place|terrace|"
    r"grove|square|walk|rise|mews|row|parade))\b\.?\s+(.+)$",
    re.I,
)


def split_form_address(value: str) -> dict[str, str]:
    parts = [
        part for part in split_address_parts(str(value or "").splitlines())
        if part.lower().strip(".") not in LOW_VALUE_ADDRESS_PARTS
    ]
    postcode = ""
    for index in range(len(parts) - 1, -1, -1):
        match = POSTCODE_RE.search(parts[index])
        if match:
            compact = re.sub(r"\s+", "", match.group(0).upper())
            postcode = f"{compact[:-3]} {compact[-3:]}"
            rest = clean_text(parts[index][: match.start()] + parts[index][match.end():]).strip(" ,")
            parts = parts[:index] + ([rest] if rest else []) + parts[index + 1:]
            break
    if len(parts) == 1:
        match = STREET_SUFFIX_RE.match(parts[0])
        if match and match.group(2).strip():
            parts = [match.group(1).strip(), match.group(2).strip()]
    return {
        "line1": parts[0] if parts else "",
        "line2": ", ".join(parts[1:-1]) if len(parts) > 2 else "",
        "town": parts[-1] if len(parts) > 1 else "",
        "postcode": postcode,
    }


def postcode_is_last_visible_line(lines: list[str]) -> bool:
    visible = [clean_text(line) for line in lines if clean_text(line)]
    return bool(visible and POSTCODE_RE.search(visible[-1]))
