from __future__ import annotations

import functools
import os
import sys
from typing import Any, Callable

MARKER_ENV = "VERGIL_CHAT_SESSION"
REFUSAL = "That check isn't available in chat."
GENERIC_FAILURE = "That didn't work just now. Tell the team if it keeps happening."


def in_chat() -> bool:
    return bool(os.environ.get(MARKER_ENV, "").strip())


TYPED_ADDRESSES_ENV = "VERGIL_TYPED_ADDRESSES"
TYPED_REFERENCES_ENV = "VERGIL_TYPED_REFERENCES"


def _typed(env_name: str) -> set[str]:
    return {v.strip().lower() for v in os.environ.get(env_name, "").split(",") if v.strip()}


def typed_addresses() -> set[str]:
    return _typed(TYPED_ADDRESSES_ENV)


def typed_references() -> set[str]:
    return _typed(TYPED_REFERENCES_ENV)


def person_confirmed(addresses: list[str]) -> bool:
    if not in_chat():
        return True
    typed = typed_addresses()
    return all(str(a or "").strip().lower() in typed for a in addresses if str(a or "").strip())


def refuse_in_chat(fn: Callable) -> Callable:

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if in_chat():
            return {"error": REFUSAL}
        return fn(*args, **kwargs)

    return wrapper


ANCHOR_ENV = "VERGIL_HARD_ANCHOR_MATTER_ID"
ANCHORED_REFUSAL = (
    "This conversation is for reading the open client's record only. Drafting, sending, signing and "
    "producing files are not available here."
)
ANCHORED_FOLDER_REFUSAL = "That folder is outside the open client's own folder, so it can't be opened here."


def anchored_matter_id() -> str:
    return os.environ.get(ANCHOR_ENV, "").strip()


def refuse_when_anchored(fn: Callable) -> Callable:

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if anchored_matter_id():
            return {"error": ANCHORED_REFUSAL}
        return fn(*args, **kwargs)

    wrapper.anchor_guard = True
    return wrapper


def path_within_anchor_folder(graph_path: str, folder: str) -> bool:
    from firm_profile import load_profile
    from graph_files import normalise_onedrive_path

    root_name = os.environ.get("CASEFORGE_ONEDRIVE_ROOT_NAME", "").strip() or load_profile().onedrive_root_name

    def raw_parts(value: str) -> list[str]:
        return [seg.strip() for seg in str(value or "").replace("\\", "/").strip().strip("/").split("/") if seg.strip()]

    def clean(value: str) -> list[str] | None:
        raw = raw_parts(value)
        if any(seg in (".", "..") for seg in raw):
            return None
        marks = [i for i, seg in enumerate(raw) if seg.casefold() == root_name.casefold()]
        if len(marks) > 1 or (marks and any(seg.casefold() == "company_data" for seg in raw[: marks[0]])):
            return None
        try:
            rel = raw_parts(normalise_onedrive_path(value).relative_path)
        except ValueError:
            return None
        if any(seg in (".", "..") or seg.casefold() == root_name.casefold() for seg in rel):
            return None
        return [seg.casefold() for seg in rel]

    want, got = clean(folder), clean(graph_path)
    if not want or got is None:
        return False
    return got[: len(want)] == want


def failure(legacy_text: str, exc: BaseException | None = None, *, plain: str = GENERIC_FAILURE, where: str = "") -> dict:
    if not in_chat():
        return {"error": legacy_text}
    detail = f"{type(exc).__name__}: {exc}" if exc is not None else legacy_text
    print(f"[chat_session] {where or 'tool'} failed: {detail}", file=sys.stderr)
    return {"error": plain}
