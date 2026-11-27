#!/usr/bin/env python3
from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from todos import todo_store

SOURCE = "todo_email_client"


def _first_name(full_name: str) -> str:
    parts = [p for p in str(full_name or "").split() if p]
    return parts[0].capitalize() if parts else ""


def build_body(title: str, client_name: str) -> str:
    first = _first_name(client_name)
    greeting = f"Dear {html.escape(first)}," if first else "Dear client,"
    return f"<p>{greeting}</p><p>I am writing about: {html.escape(title)}.</p><p></p>"


def draft_for_todo(todo_id: str, *, by: str = "", owner: str | None = None) -> dict[str, Any]:
    task = todo_store.get(todo_id, owner=owner)
    if task is None:
        raise todo_store.TodoError(f"no such task: {todo_id}")
    if task.get("matter_id") is None:
        raise todo_store.TodoError("this task is not tied to a client")
    if task.get("draft_link"):
        return {"todo": task, "draft_link": task["draft_link"], "warning": "", "created": False}

    from graph_mail_safe_ops import _prepare_draft_body, _recipient_rows, post_draft_payload
    from onboarding.pipeline import load_context
    from onboarding.pipeline.court_common import mail_client
    from onboarding.pipeline.step_email import address_warning

    ctx = load_context(str(task["matter_id"]))
    try:
        warning = address_warning(ctx)
    except Exception:
        warning = "the address could not be checked; look at it before sending."
    if not ctx.email:
        warning = "no email address is on record for this client; add one before sending."
    payload = {
        "subject": str(task["title"]),
        "body": {"contentType": "HTML", "content": _prepare_draft_body(build_body(str(task["title"]), ctx.client_name), "HTML")},
        "toRecipients": _recipient_rows([ctx.email] if ctx.email else []),
        "ccRecipients": [],
        "bccRecipients": [],
        "isDraft": True,
    }
    created = post_draft_payload(mail_client(), payload, matter_id=ctx.matter_id, client_name=ctx.client_name, source=SOURCE)
    link = str((created or {}).get("webLink") or "")
    if not str((created or {}).get("id") or "") or not link:
        raise RuntimeError("Outlook did not return the new draft.")
    return {"todo": todo_store.set_draft_link(todo_id, link, owner=owner), "draft_link": link, "warning": warning, "created": True}
