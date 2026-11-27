#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


def document_identity_tokens(filename: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", Path(filename).stem.lower()))


def document_type_signatures() -> dict[str, dict[str, tuple]]:
    import order_codes
    from order_codes import ORDER_LABELS

    order_filename_groups = order_codes.FILENAME_TOKEN_GROUPS
    signatures: dict[str, dict[str, tuple]] = {}
    for code, full_name in ORDER_LABELS.items():
        lower_name = full_name.lower()
        body_phrases = tuple({lower_name, lower_name.replace("-", " ")})
        signatures[code] = {"body_phrases": body_phrases, "filename_token_groups": order_filename_groups[code]}
    signatures["SOS"] = {
        "body_phrases": ("statement of service", "certificate of service"),
        "filename_token_groups": (
            frozenset({"sos"}),
            frozenset({"statement", "service"}),
            frozenset({"certificate", "service"}),
        ),
    }
    signatures["NOTICE_OF_ACTING"] = {
        "body_phrases": ("notice of acting",),
        "filename_token_groups": (frozenset({"notice", "acting"}),),
    }
    signatures["WITNESS_STATEMENT"] = {
        "body_phrases": ("witness statement",),
        "filename_token_groups": (frozenset({"witness", "statement"}), frozenset({"ws"})),
    }
    signatures["FL401"] = {
        "body_phrases": ("fl401", "fl 401"),
        "filename_token_groups": (frozenset({"fl401"}),),
    }
    signatures["C100"] = {
        "body_phrases": ("c100", "c 100"),
        "filename_token_groups": (frozenset({"c100"}),),
    }
    signatures["LEGAL_AID_CERTIFICATE"] = {
        "body_phrases": ("legal aid certificate", "legal aid form"),
        "filename_token_groups": (frozenset({"legal", "aid"}),),
    }
    return signatures


CCL_TOKEN_RUNS: tuple[tuple[str, ...], ...] = (
    ("ccl",),
    ("ccls",),
    ("client", "care", "letter"),
    ("client", "care", "letters"),
)


def looks_like_client_care_letter(*names: str) -> bool:
    for name in names:
        raw = str(name or "")
        split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", raw)
        for text in (raw, split):
            tokens = re.findall(r"[a-z0-9]+", text.lower())
            for run in CCL_TOKEN_RUNS:
                if any(tuple(tokens[i : i + len(run)]) == run for i in range(len(tokens) - len(run) + 1)):
                    return True
    return False


def claimed_document_types(body: str) -> set[str]:
    text = re.sub(r"<[^>]+>", " ", body or "")
    text = re.sub(r"\s+", " ", text).lower()
    return {
        type_key
        for type_key, sig in document_type_signatures().items()
        if any(phrase in text for phrase in sig["body_phrases"])
    }


def attachment_document_type(path: str) -> str | None:
    tokens = document_identity_tokens(path)
    matches = {
        type_key
        for type_key, sig in document_type_signatures().items()
        if any(group <= tokens for group in sig["filename_token_groups"])
    }
    return matches.pop() if len(matches) == 1 else None


def attachment_identity_mismatch(body: str, attachments: list[str]) -> str | None:
    claimed = claimed_document_types(body)
    if not claimed:
        return None
    for path in attachments:
        actual = attachment_document_type(path)
        if actual and actual not in claimed:
            return f"the body claims {sorted(claimed)!r} but {Path(path).name!r} looks like a {actual!r} document instead"
    return None
