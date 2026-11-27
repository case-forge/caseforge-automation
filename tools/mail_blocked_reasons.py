from __future__ import annotations

from typing import Any

QUEUE_LABEL = "Improve classifier: could not classify"

BLOCKED_REASON_LABELS: dict[str, str] = {
    "matter_unmatched": "No matter found",
    "route_uncertain": "Route not decided",
    "matter_ambiguous": "Matter unclear",
    "matter_low_confidence": "Matter unclear",
    "matter_folder_not_found": "Folder problem",
    "target_folder_missing": "Folder problem",
    "onedrive_index_unavailable": "Folder problem",
    "load_onedrive_index_failed": "Folder problem",
    "documenso_completion_id_unresolved": "Envelope not tied to a matter",
    "referralpartner_intake_route": "Client needs onboarding",
    "counsel_relationship_uncertain": "Counsel relationship unclear",
}

AI_FAILED = "ai_failed"
MODEL_UNAVAILABLE_NOTICE = "the classifier model was unavailable"

VETO_PREFIXES = (
    "ai_route_without_court_or_chambers_participant",
    "ai_client_sender_veto",
    "ai_source_route_without_source_participant",
    "ai_client_to_val_only_veto",
)


def blocked_reason_label(code: Any) -> str:
    return BLOCKED_REASON_LABELS.get(str(code or "").strip(), "")


def blocked_headline(code: Any, *, model_unavailable: bool = False) -> str:
    label = blocked_reason_label(code)
    if model_unavailable:
        label = f"{label}; {MODEL_UNAVAILABLE_NOTICE}" if label else MODEL_UNAVAILABLE_NOTICE
    return f"{QUEUE_LABEL} - {label}" if label else QUEUE_LABEL


def veto_kind(reasons: Any) -> str:
    for reason in reasons or ():
        text = str(reason or "")
        for prefix in VETO_PREFIXES:
            if text == prefix or text.startswith(prefix + ":"):
                return prefix
    return ""


UNSORTED_EXCLUDED_ROUTES = frozenset({"Junk", "Work Experience", "Junk/Auto Replies", "Junk/Newsletters"})
UNSORTED_NEEDS_READING = "Unsorted - needs reading"


def unsorted_bucket(route: Any, reason: Any) -> str:
    route_text = str(route or "").strip()
    reason_text = str(reason or "").strip()
    if not route_text or route_text in UNSORTED_EXCLUDED_ROUTES:
        return ""
    if route_text == "Review":
        return UNSORTED_NEEDS_READING if reason_text in {"route_uncertain", "matter_unmatched"} else ""
    if reason_text == "matter_unmatched":
        return f"Unsorted - {route_text}"
    return ""
