from __future__ import annotations

import re
from typing import Any

_NAME = r"[A-Z][a-z]+(?:['’-][A-Z][a-z]+)?"
NAME_RE = re.compile(rf"\b(Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+({_NAME}(?:\s+{_NAME}){{0,2}})\b")
_NOT_COUNSEL = {"justice", "judge", "clerk", "recorder", "magistrate"}
_ACCEPTS_AFTER = re.compile(
    r"\s*(?:\([^)]{0,40}\)\s*)?(?:of counsel\s+)?(?:"
    r"(?:will|can|could|is able to|is happy to|has agreed to|would be happy to)\s+(?:be\s+)?(?:attend|attending|cover|covering|accept|do|take|represent)"
    r"|is available|is free|has accepted|accepts|is booked|has been booked|is instructed|has been instructed|confirmed)\b",
    re.IGNORECASE,
)
_ACCEPTS_BEFORE = re.compile(
    r"(?:counsel|barrister|offer|booked|instructed|allocated|attending will be|(?:brief|instructions)\s+to)\s*(?:is|will be|:|-|–)?\s*$",
    re.IGNORECASE,
)
_HOST_RE = re.compile(r"(?:@|\b(?:https?://)?(?:www\.)?)([a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+)", re.IGNORECASE)


def _full(title: str, name: str) -> str:
    words = name.split()
    if words[0].lower() in _NOT_COUNSEL:
        return ""
    return f"{title} {' '.join(w for w in words if w.lower() not in _NOT_COUNSEL)}"


def distinct(names: list[str]) -> list[str]:
    found: dict[str, str] = {}
    for n in names:
        if n.strip():
            found.setdefault(n.lower(), n)
    kept: list[str] = []
    for n in sorted(found.values(), key=len, reverse=True):
        title, rest = n.split(" ", 1)
        if not any(k.lower().endswith(rest.lower()) and k.split()[0].lower() == title.lower() for k in kept):
            kept.append(n)
    return kept


def titled_names(*texts: str) -> list[str]:
    return distinct([_full(t, n) for text in texts for t, n in NAME_RE.findall(text or "")])


def accepted_names(body: str) -> list[str]:
    text = " ".join(str(body or "").split())
    out = []
    for m in NAME_RE.finditer(text):
        if _ACCEPTS_AFTER.match(text, m.end()) or _ACCEPTS_BEFORE.search(text[max(0, m.start() - 40):m.start()]):
            out.append(_full(m.group(1), m.group(2)))
    return distinct(out)


def _chambers() -> list[dict[str, Any]]:
    try:
        from counsel.chambers import _load

        return list(_load().get("chambers") or [])
    except (Exception, SystemExit):
        return []


def _host(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^[a-z]+://", "", text).split("/", 1)[0]
    text = text.rpartition("@")[2]
    return text[4:] if text.startswith("www.") else text


def chambers_from_domain(domain: str) -> str:
    d = _host(domain)
    if not d:
        return ""
    names = {str(c.get("name") or "").strip() for c in _chambers() if (h := _host(c.get("email", ""))) and (d == h or d.endswith("." + h))}
    names.discard("")
    return names.pop() if len(names) == 1 else ""


def chambers_from_text(body: str) -> str:
    text = " ".join(str(body or "").split())
    if not text:
        return ""
    rows = _chambers()
    hosts = {_host(h) for h in _HOST_RE.findall(text)}
    spans: list[tuple[int, int, str]] = []
    by_host: set[str] = set()
    for c in rows:
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        own = {h for h in (_host(c.get("email", "")), _host(c.get("website", ""))) if h}
        if any(h == o or h.endswith("." + o) for h in hosts for o in own):
            by_host.add(name)
        for label in [name, *c.get("aliases", [])]:
            label = str(label or "").strip()
            if len(label.split()) < 2:
                continue
            for m in re.finditer(rf"(?<![\w]){re.escape(label)}(?![\w])", text, re.IGNORECASE):
                spans.append((m.start(), m.end(), name))
    named = {n for s, e, n in spans if not any(s2 <= s and e <= e2 and (s2, e2) != (s, e) for s2, e2, _ in spans)}
    found = named | by_host
    return found.pop() if len(found) == 1 else ""


def read(*, subject: str = "", summary: str = "", body: str = "", sender_domain: str = "") -> dict[str, Any]:
    in_summary = titled_names(summary, subject)
    in_body = accepted_names(body)
    names = distinct(in_summary + in_body)
    counsel_from = "the reply's summary or subject" if in_summary else ("the reply's acceptance wording" if in_body else "")
    chambers, chambers_from = chambers_from_domain(sender_domain), "the sender's domain"
    if not chambers:
        chambers, chambers_from = chambers_from_text(body), "the reply's signature"
    return {"counsel_names": names, "counsel_from": counsel_from, "chambers": chambers, "chambers_from": chambers_from if chambers else ""}
