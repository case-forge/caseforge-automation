from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

ANSWER_EXCERPT_CHARS = 300
QUESTION_MAX_CHARS = 500
TITLE_MAX_CHARS = 60
TITLE_MAX_TOKENS = 400

_SYSTEM = (
    "Write a title of 3 to 6 words for this chat between a solicitor and a case assistant. "
    "Reply with the title only: no quotes, no full stop, no preamble."
)


def clean_title(raw: str) -> Optional[str]:
    text = (raw or "").strip().splitlines()[0].strip() if (raw or "").strip() else ""
    text = re.sub(r"^(title\s*:\s*)", "", text, flags=re.IGNORECASE)
    text = text.strip("\"'`*# ").rstrip(".")
    text = text.replace("—", ",").replace("–", "-").replace(" -- ", ", ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if len(text) > TITLE_MAX_CHARS:
        text = text[:TITLE_MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;:- ")
    return text or None


def make_title(question: str, answer: str) -> Optional[str]:
    question = (question or "").strip()[:QUESTION_MAX_CHARS]
    if not question:
        return None
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import model_backend as mb

    excerpt = (answer or "").strip()[:ANSWER_EXCERPT_CHARS]
    prompt = f"Question: {question}\n\nAnswer: {excerpt}"
    try:
        result = mb.run_model(
            mb.ROLE_CHAT_TITLE,
            prompt,
            backend="openrouter",
            reasoning="low",
            max_tokens=TITLE_MAX_TOKENS,
            system_prompt=_SYSTEM,
            telemetry=False,
        )
    except Exception:
        return None
    if not result.ok:
        return None
    return clean_title(result.text)
