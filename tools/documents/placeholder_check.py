#!/usr/bin/env python3

from __future__ import annotations

import base64
import io
import re
import zipfile
from typing import Any, Iterable

from zip_safe import read_member

PLACEHOLDER_RE = re.compile(r"\bTBC\b|\bTBA\b|to be confirmed|to be advised", re.IGNORECASE)

_COURT_LINE_RE = re.compile(r"^\s*(in\s+the\b[^\t\n]*?)\s*(?:\t.*|case\s+no\b.*)?$", re.IGNORECASE)
_XXX_RE = re.compile(r"\b[Xx]{3,}\b")
_COURT_MARKER_RE = re.compile(r"\[[^\]\n]{0,60}\bcourt\b[^\]\n]{0,60}\]", re.IGNORECASE)
_MARKER_WORDS_RE = re.compile(r"insert|name|confirm|tbc|tba|\?", re.IGNORECASE)


_BRACKET_MARKER_RE = re.compile(
    r"\[(?:[^\]\n]{0,50}\b(?:confirm|tbc|tba|insert)\b[^\]\n]{0,50}|\s*(?:court|date(?: of [a-z ]{1,30})?|name|address)\s*)\]",
    re.IGNORECASE,
)
_TEMPLATE_KEY_RE = re.compile(r"\{\{[^}\n]{1,60}\}\}")


def _court_marker(marker: str) -> bool:
    inner = marker[1:-1]
    return inner == inner.upper() or bool(_MARKER_WORDS_RE.search(inner))


_NOT_A_PLACE_RE = re.compile(r"^\s*(?:case\s+no\b|between\b|applicant\b|respondent\b|in\s+the\b|and\b)", re.IGNORECASE)


def _place_on_next_line(lines: list[str], index: int) -> bool:
    for following in lines[index + 1 : index + 4]:
        candidate = following.strip()
        if not candidate:
            continue
        return not (_NOT_A_PLACE_RE.match(candidate) or _XXX_RE.search(candidate) or _COURT_MARKER_RE.search(candidate))
    return False


_NAMED_COURT_RE = re.compile(r"^\s*(?:the\s+)?(?:family|county|high|magistrates[’']?)\s+court(?:\s+sitting)?\s+at\s+\S", re.IGNORECASE)


def _court_named_on_next_line(lines: list[str], index: int) -> bool:
    for following in lines[index + 1 : index + 4]:
        candidate = following.strip()
        if not candidate:
            continue
        return bool(_NAMED_COURT_RE.match(candidate)) and not (_XXX_RE.search(candidate) or _COURT_MARKER_RE.search(candidate))
    return False


def heading_placeholders(text: str) -> list[str]:
    found: list[str] = []

    def add(phrase: str) -> None:
        if phrase not in found:
            found.append(phrase)

    lines = (text or "").splitlines()
    for index, line in enumerate(lines):
        match = _COURT_LINE_RE.match(line)
        if match:
            court = re.sub(r"\s+", " ", match.group(1)).strip()
            rest = court[len("in the"):].strip()
            if not rest:
                if not _court_named_on_next_line(lines, index):
                    add(f'court heading "{court}" names no court')
            elif re.search(r"(?i)\bcourt\s+(?:sitting\s+)?at$", rest):
                if not _place_on_next_line(lines, index):
                    add(f'court heading "{court}" names no court')
            elif _XXX_RE.search(rest) and ("court" in rest.lower() or _XXX_RE.fullmatch(rest)):
                add(f'court heading "{court}"')
        for marker in _COURT_MARKER_RE.findall(line):
            if _court_marker(marker):
                add(marker)
    return found


class PlaceholderInDraft(ValueError):
    pass


def find_hard_placeholders(text: str) -> list[str]:
    seen: list[str] = []
    for match in PLACEHOLDER_RE.finditer(text or ""):
        if match.group(0) not in seen:
            seen.append(match.group(0))
    return seen + [phrase for phrase in heading_placeholders(text) if phrase not in seen]


def find_unfinished_markers(text: str) -> list[str]:
    seen: list[str] = []
    for pattern in (_BRACKET_MARKER_RE, _TEMPLATE_KEY_RE):
        for match in pattern.finditer(text or ""):
            if match.group(0) not in seen:
                seen.append(match.group(0))
    return seen


def find_placeholders(text: str) -> list[str]:
    hard = find_hard_placeholders(text)
    return hard + [m for m in find_unfinished_markers(text) if m not in hard]


def attachment_text(name: str, data: bytes) -> str:
    lower = str(name or "").lower()
    try:
        if lower.endswith(".docx"):
            xml = read_member(zipfile.ZipFile(io.BytesIO(data)), "word/document.xml").decode("utf-8", "ignore")
            return re.sub(r"<[^>]+>", "", re.sub(r"<w:tab/>", "\t", xml.replace("</w:p>", "\n")))
        if lower.endswith(".pdf"):
            from pypdf import PdfReader

            return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return ""
    return ""


def _draft_texts(payload: dict[str, Any]) -> Iterable[tuple[str, str]]:
    body = str((payload.get("body") or {}).get("content") or "")
    yield "subject", str(payload.get("subject") or "")
    yield "body", re.sub(r"<[^>]+>", " ", body)
    attachments: Iterable[dict[str, Any]] = payload.get("attachments") or []
    for attachment in attachments:
        raw = attachment.get("contentBytes")
        if not raw:
            continue
        name = str(attachment.get("name") or "attachment")
        try:
            data = base64.b64decode(raw)
        except Exception:
            continue
        yield name, attachment_text(name, data)


def draft_hard_placeholders(payload: dict[str, Any]) -> list[str]:
    return [f"{where}: {phrase}" for where, text in _draft_texts(payload) for phrase in find_hard_placeholders(text)]


def draft_unfinished_markers(payload: dict[str, Any]) -> list[str]:
    return [f"{where}: {phrase}" for where, text in _draft_texts(payload) for phrase in find_placeholders(text)]


NOTE_PREFIX = "AI DRAFTED - NOT READY TO SEND"


def unfinished_note(found: list[str], content_type: str = "HTML") -> str:
    text = NOTE_PREFIX + ". Still to fill in or check: " + "; ".join(found)
    if str(content_type).upper() == "HTML":
        import html

        return f'<p><b style="color:#b00020">{html.escape(text)}</b></p>'
    return text + "\n\n"


def with_unfinished_note(payload: dict[str, Any]) -> dict[str, Any]:
    if NOTE_PREFIX in str((payload.get("body") or {}).get("content") or ""):
        return payload
    found = draft_unfinished_markers(payload)
    if not found:
        return payload
    import sys

    print(f"[placeholder_check] draft made with placeholder text: {'; '.join(found)}", file=sys.stderr)
    body = dict(payload.get("body") or {})
    body["content"] = unfinished_note(found, body.get("contentType", "HTML")) + str(body.get("content") or "")
    return {**payload, "body": body}
