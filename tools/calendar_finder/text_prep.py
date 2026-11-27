
from __future__ import annotations

import datetime as dt
import html
import re
from typing import Any
from zoneinfo import ZoneInfo

try:
    LONDON = ZoneInfo("Europe/London")
except Exception:
    LONDON = dt.timezone.utc

CASE_REF_RE = re.compile(r"\b[A-Z]{1,3}\d{2}[A-Z]\d{5}\b", re.IGNORECASE | re.ASCII)

_BLOCK_TAG_RE = re.compile(r"</?(?:p|div|br|tr|li|ul|ol|table|thead|tbody|h[1-6]|blockquote|hr|section|article)\b[^>]*>", re.IGNORECASE)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_BLOCK_RE = re.compile(r"<(?:style|script|head)\b.*?</(?:style|script|head)>", re.IGNORECASE | re.DOTALL)

_STRONG_HEADER_RE = re.compile(
    r"^\s*(?:(?:from|sent|to|cc|bcc|received|importance|reply-to|priority)\s*:"
    r"|(?:sent|received)\s+(?:on\s+)?(?:(?:mon|tues|wednes|thurs|fri|satur|sun)day,?\s+)?\d{1,2}\b)",
    re.IGNORECASE,
)
_WEAK_HEADER_RE = re.compile(r"^\s*date\s*:", re.IGNORECASE)
_SUBJECT_LABEL_RE = re.compile(r"^(\s*)subject\s*:\s*", re.IGNORECASE)
_ORIGINAL_MESSAGE_RE = re.compile(r"^\s*[-_=*]{2,}\s*(?:original message|forwarded message|forwarded by.*?)\s*[-_=*]*\s*$", re.IGNORECASE)
_WROTE_RE = re.compile(r"(?im)^[ \t>]*on\s[^\n]{0,160}(?:\n[^\n]{0,100})?\bwrote\s*:[ \t]*$")
_INLINE_SENT_RE = re.compile(r"(?:\bSent|(?<![A-Za-z]\s)\bDate)\s*:\s*[^\n]{0,90}?(?=\s+(?:To|Cc|Bcc|Subject)\s*:)", re.IGNORECASE)
_INLINE_FROM_RE = re.compile(r"\bFrom\s*:\s*[^\n]{0,160}?(?=\s+Sent\s*:)", re.IGNORECASE)
_WEAK_NEIGHBOUR_LINES = 3


def html_to_text(content: str) -> str:
    text = _STYLE_BLOCK_RE.sub(" ", str(content or ""))
    text = _BLOCK_TAG_RE.sub("\n", text)
    text = _ANY_TAG_RE.sub(" ", text)
    return html.unescape(text)


def _tidy_lines(text: str) -> str:
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out: list[str] = []
    blank = 0
    for line in lines:
        if line:
            blank = 0
            out.append(line)
        else:
            blank += 1
            if blank == 1 and out:
                out.append("")
    return "\n".join(out).strip()


def body_text_with_lines(message: dict[str, Any], limit: int = 12000) -> str:
    body = message.get("body") or {}
    if isinstance(body, dict):
        content = str(body.get("content") or "")
        content_type = str(body.get("contentType") or "").lower()
    else:
        content, content_type = str(body or ""), ""
    if content_type == "html" or (content_type != "text" and re.search(r"<\s*(?:html|body|div|p|br|table)\b", content, re.IGNORECASE)):
        content = html_to_text(content)
    return _tidy_lines(content)[:limit]


def strip_email_headers(text: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    text = str(text or "")
    for match in _WROTE_RE.finditer(text):
        removed.append(match.group(0).strip())
    text = _WROTE_RE.sub("", text)
    lines = text.split("\n")
    strong = [bool(_STRONG_HEADER_RE.match(line)) for line in lines]
    keep: list[str] = []
    for index, line in enumerate(lines):
        if strong[index] or _ORIGINAL_MESSAGE_RE.match(line):
            removed.append(line.strip())
            continue
        if _WEAK_HEADER_RE.match(line):
            lo, hi = max(0, index - _WEAK_NEIGHBOUR_LINES), min(len(lines), index + _WEAK_NEIGHBOUR_LINES + 1)
            if any(strong[i] for i in range(lo, hi)):
                removed.append(line.strip())
                continue
        subject = _SUBJECT_LABEL_RE.match(line)
        if subject and any(strong[i] for i in range(max(0, index - _WEAK_NEIGHBOUR_LINES), min(len(lines), index + _WEAK_NEIGHBOUR_LINES + 1))):
            line = line[subject.end():]
        keep.append(line)
    cleaned, inline_removed = strip_inline_headers("\n".join(keep))
    return _tidy_lines(cleaned), removed + inline_removed


def strip_inline_headers(text: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    text = str(text or "")

    def _drop(match: re.Match[str]) -> str:
        stamp = match.group(0)
        if re.match(r"\s*Date\b", stamp, re.IGNORECASE) and re.search(r"\bTime\s*:", stamp, re.IGNORECASE):
            return stamp
        removed.append(stamp.strip())
        return " "

    text = _INLINE_SENT_RE.sub(_drop, text)
    text = _INLINE_FROM_RE.sub(_drop, text)
    return text, removed


def _parse_stamp(value: Any) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(LONDON)


def message_local_stamps(message: dict[str, Any]) -> list[dt.datetime]:
    stamps = [_parse_stamp(message.get(key)) for key in ("receivedDateTime", "sentDateTime", "createdDateTime")]
    return [stamp for stamp in stamps if stamp is not None]


_HEADER_CONTEXT_RE = re.compile(r"\b(?:sent|received|date|from|to|cc|bcc|subject)\s*:|\bwrote\s*:|\bsent\s+(?:on\s+)?\d", re.IGNORECASE)


def has_header_context(text: str) -> bool:
    return bool(_HEADER_CONTEXT_RE.search(str(text or "")))


def is_datetime_echo(hearing_date: str, hearing_time: str, stamps: list[dt.datetime], *, minutes: int = 1) -> bool:
    if not hearing_date or not hearing_time:
        return False
    try:
        date = dt.date.fromisoformat(hearing_date)
        hour, minute = (int(part) for part in hearing_time.split(":", 1))
    except ValueError:
        return False
    for stamp in stamps:
        if stamp.date() != date:
            continue
        if abs((stamp.hour * 60 + stamp.minute) - (hour * 60 + minute)) <= minutes:
            return True
    return False
