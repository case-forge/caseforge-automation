from __future__ import annotations

from typing import Any, Dict, List

RECORD_FIELDS = (
    "matter_id",
    "drive_id",
    "item_id",
    "path",
    "doc_type",
    "modified_utc",
    "chunk_index",
    "text",
    "c8_protected",
)

DOC_TYPE_KEYWORDS = (
    ("order", "order"),
    ("statement", "statement"),
    ("stmt", "statement"),
    ("bundle", "bundle"),
    ("witness", "statement"),
    ("position statement", "statement"),
)


def infer_doc_type(path: str) -> str:
    lowered = path.lower()
    for needle, doc_type in DOC_TYPE_KEYWORDS:
        if needle in lowered:
            return doc_type
    return "other"


def validate_record(record: Dict[str, Any]) -> None:
    missing = [f for f in RECORD_FIELDS if f not in record]
    if missing:
        raise ValueError(f"chunk record missing fields: {missing}")


def _split_paragraphs(text: str) -> List[str]:
    paras = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n")]
    return [p for p in paras if p]


def chunk_text(
    text: str,
    *,
    target_words: int = 650,
    overlap_ratio: float = 0.15,
) -> List[str]:
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_words = 0

    def flush() -> List[str]:
        nonlocal current, current_words
        if not current:
            return []
        chunks.append("\n\n".join(current))
        overlap_words = int(current_words * overlap_ratio)
        tail: List[str] = []
        tail_words = 0
        for para in reversed(current):
            words = len(para.split())
            if tail_words and tail_words + words > overlap_words:
                break
            tail.insert(0, para)
            tail_words += words
        current = []
        current_words = 0
        return tail

    for para in paragraphs:
        words = len(para.split())
        if current and current_words + words > target_words:
            tail = flush()
            current = tail
            current_words = sum(len(p.split()) for p in tail)
        current.append(para)
        current_words += words

    if current:
        chunks.append("\n\n".join(current))

    return chunks
