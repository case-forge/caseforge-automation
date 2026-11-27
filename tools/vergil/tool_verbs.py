from __future__ import annotations

from vergil.retrieval import STEP_VERBS

_ROUTE_VERBS = {
    "legal_aid_signing_draft": "Preparing the legal aid signing draft",
    "notice_of_acting": "Drafting the Notice of Acting",
    "attendance_note": "Writing the attendance note",
    "local_lookup": "Looking up the matter",
}

_MODEL_TOOL_VERBS = {
    "read": "Reading a file",
    "write": "Writing a file",
    "edit": "Editing a file",
    "notebookedit": "Editing a notebook",
    "bash": "Running a command",
    "exec_command": "Running a command",
    "grep": "Searching the case files",
    "glob": "Finding files",
    "ls": "Listing a folder",
    "webfetch": "Fetching a page",
    "websearch": "Searching the web",
    "task": "Delegating to a helper",
    "todowrite": "Updating the task list",
}

_RETRIEVAL_VERBS = {key: value for key, value in STEP_VERBS.items()}

FALLBACK_VERB = "Working"


def verb_for(name: str) -> str:
    key = str(name or "").strip()
    if not key:
        return FALLBACK_VERB
    lowered = key.lower()
    for table in (_ROUTE_VERBS, _RETRIEVAL_VERBS, _MODEL_TOOL_VERBS):
        if lowered in table:
            return table[lowered]
        if key in table:
            return table[key]
    return key.replace("_", " ").replace("-", " ").strip().capitalize() or FALLBACK_VERB


def is_known(name: str) -> bool:
    lowered = str(name or "").strip().lower()
    return any(
        lowered in table or str(name).strip() in table
        for table in (_ROUTE_VERBS, _RETRIEVAL_VERBS, _MODEL_TOOL_VERBS)
    )


def all_verbs() -> dict[str, str]:
    merged: dict[str, str] = {}
    merged.update(_MODEL_TOOL_VERBS)
    merged.update(_RETRIEVAL_VERBS)
    merged.update(_ROUTE_VERBS)
    return merged


_GAP_VERBS = {
    "no matching matter in the case database for this question":
        "No matching matter found in the case database for this question.",
    "no matter record matches the anchored client id -- this is not a "
    "confirmed absence; the record may be temporarily unreachable":
        "The current client's record could not be found this time. This is not "
        "confirmation that it does not exist.",
    "the reference in this question was not found in the case database, and "
    "document matches for other matters were not used to guess a different one":
        "That reference was not found in the case database. Document matches "
        "for other matters were deliberately not used to guess a different "
        "one, so no matter has been assumed. Check the reference, or search "
        "by client name instead.",
    "no matching matter documents found":
        "No matching matter documents found.",
    "matching matter documents exist in the index but their text "
    "could not be read on this box, so they were not quoted; the "
    "live folder listing was used instead":
        "Matching matter documents were found, but their text could not be "
        "read on this system, so they are not quoted here. The live folder "
        "listing was checked instead.",
    "matching matter documents were found for a different, "
    "unconfirmed matter this turn and were not shown, to avoid "
    "quoting the wrong client's documents":
        "Matching matter documents were found, but for a different, "
        "unconfirmed matter. They were not shown, to avoid quoting the "
        "wrong client's documents.",
    "the live OneDrive folder listing returned nothing":
        "The live OneDrive folder listing returned nothing.",
    "the live OneDrive folder could not be checked this turn -- this is "
    "not a confirmed absence; documents may still exist":
        "The live OneDrive folder could not be checked this time. This is not "
        "confirmation that no documents exist.",
    "the live OneDrive folder was not checked because this question did "
    "not identify a client":
        "The live OneDrive folder was not checked, because this question did not "
        "identify a client whose folder to look in.",
    "the case database lookup could not be completed this turn -- this is not "
    "a confirmed absence; the client or matter may still exist":
        "The case database lookup could not be completed this time. This is not "
        "confirmation that the client or matter does not exist.",
    "the matter was found by matching the document search results, not the "
    "original search text":
        "The matter was found by matching the document search results, not the "
        "original search text.",
    "a document search match for a different matter than the one "
    "already established in this conversation was found and set "
    "aside -- the established matter was kept; ask explicitly if "
    "this question is actually about someone else":
        "A document search matched a different matter than the one already "
        "established in this conversation. That match was set aside and the "
        "established matter was kept -- ask explicitly if this question is "
        "actually about someone else.",
    "no matching messages found in the mailbox":
        "No matching messages found in the mailbox.",
    "the mailbox could not be searched this turn -- this is not a confirmed "
    "absence; correspondence may still exist":
        "The mailbox could not be searched this time. This is not confirmation "
        "that correspondence does not exist.",
    "the mailbox was not searched because this question did not identify a client":
        "The mailbox was not searched, because this question did not identify a "
        "client to search for.",
    "no live matter folder matched that name. the client may be "
    "recorded under a different spelling, or may have no folder yet":
        "No live matter folder matched that name. The client may be recorded "
        "under a different spelling, or may not have a folder yet.",
    "mailbox messages were found but not read into this answer, because the "
    "model answering it is not one cleared to receive client correspondence":
        "Mailbox messages were found but not read into this answer, because the "
        "model answering it is not one cleared to receive client correspondence.",
    "the most recent correspondence found significantly predates today and no live "
    "OneDrive folder or matter documents were found either -- this matter may be "
    "concluded or inactive. Do not draft present-tense time-sensitive content (an "
    "upcoming hearing, a \"you must attend\" instruction) from these dates without "
    "first confirming the case is still live -- check mail_hits' own sent_at dates":
        "The most recent correspondence found significantly predates today, and no "
        "live OneDrive folder or matter documents were found either. This matter may "
        "be concluded or inactive -- check before treating anything found as current.",
}


def gap_for(text: str) -> str:
    key = str(text or "")
    return _GAP_VERBS.get(key, key)


def known_gaps() -> dict[str, str]:
    return dict(_GAP_VERBS)
