from __future__ import annotations

import re


STATUS_PROMPT_RE = re.compile(
    r"\b(?:what(?:'s| is)\s+happening\s+(?:with|for)|where\s+are\s+we\s+up\s+to\s+(?:with|for)|status\s+(?:for|on)|snapshot\s+(?:for|on)|update\s+(?:for|on)|tell\s+me\s+about|what\s+do\s+we\s+know\s+about)\s+(.+)$",
    re.I,
)


def looks_like_status_prompt(prompt: str) -> bool:
    return STATUS_PROMPT_RE.search(" ".join(str(prompt or "").split())) is not None


def extract_status_query(prompt: str) -> str:
    text = " ".join(str(prompt or "").split())
    match = STATUS_PROMPT_RE.search(text)
    if not match:
        return text.strip()
    query = match.group(1).strip(" ?.")
    query = re.sub(r"\bplease\b$", "", query, flags=re.I).strip()
    return query
