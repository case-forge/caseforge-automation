#!/usr/bin/env python3
"Cheap Brief to Counsel content drafting: deterministic gather + one bounded"
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import model_backend
from agents.ccl_pipeline import (
    GatherError,
    gather_client_facts,
)
from folder_surname import surname_of

INSTRUCTIONS_PATH = REPO_ROOT / "templates" / "Brief to Counsel Instructions.md"

PROMPT_TEMPLATE = """{instructions}

CASE FACTS (from the real referral and signed witness statement -- use only \
what these actually state; where the instructions template asks for a \
hearing-specific field not present in these sources -- case number, court, \
hearing date/time, counsel name -- write "TBC" rather than invent one, and \
say so plainly rather than guessing):

CLIENT: {client_name}
{phone}
SOURCE -- referral email (from referrer):
{referral}

SOURCE -- signed witness statement:
{ws}
{hearing}
Produce only the completed Brief to Counsel, following the format and \
Compression Rules in the instructions above exactly.
"""


HEARING_FIELDS = (
    ("hearing_date", "Date"),
    ("hearing_time", "Time"),
    ("hearing_type", "Type"),
    ("court", "Court"),
    ("case_ref", "Case number"),
    ("counsel", "Counsel"),
    ("chambers", "Chambers"),
)


def hearing_block(hearing: dict[str, Any] | None) -> str:
    "The hearing this brief is for, from the firm's hearing calendar, as prompt lines. Only fields the"
    if not hearing:
        return ""
    lines = [f"{label}: {str(hearing.get(key) or '').strip()[:200]}" for key, label in HEARING_FIELDS if str(hearing.get(key) or "").strip()]
    if not lines:
        return ""
    return (
        "\nTHE HEARING THIS BRIEF IS FOR (from the firm's hearing calendar; use these exactly and do not "
        "name any other hearing date as the one counsel attends):\n" + "\n".join(lines) + "\n"
    )


def phone_block(client_phone: str) -> str:
    "The client's number from OUR record, as a prompt line. The referral and statement hold other people's numbers (the"
    if client_phone.strip():
        return (
            f"CLIENT'S TELEPHONE NUMBER (from our own record; write it exactly, in the line that says how to contact the "
            f"client, and never take a number for the client from the sources below): {client_phone.strip()}\n"
        )
    return (
        "CLIENT'S TELEPHONE NUMBER: none on our record. Do not write a telephone number for the client, and never take one "
        "from the sources below (they hold other people's numbers).\n"
    )


_CONTACT_LINE = re.compile(r"(you can contact (?:them|her|him) on)\s*[^.\n]*", re.IGNORECASE)


def ensure_client_number(text: str, client_phone: str) -> str:
    "The brief with the client's own number in it, exactly once, whatever the model wrote."
    phone = client_phone.strip()
    if not phone:
        return _CONTACT_LINE.sub("", text).replace("  ", " ")
    if _CONTACT_LINE.search(text):
        return _CONTACT_LINE.sub(lambda m: f"{m.group(1)} {phone}", text, count=1)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if re.search(r"our client|applicant is", line, re.IGNORECASE):
            lines[i] = line.rstrip() + f" You can contact them on **{phone}**."
            return "\n".join(lines)
    for i, line in enumerate(lines):
        if line.lstrip("*# ").lower().startswith("key points"):
            lines[i:i] = [f"You can contact our client on **{phone}**.", ""]
            return "\n".join(lines)
    return text.rstrip() + f"\n\nYou can contact our client on **{phone}**.\n"


def draft_brief(
    client_name: str, *, timeout: float = 120, folder=None, hearing: dict[str, Any] | None = None, client_phone: str = ""
) -> dict[str, Any]:
    "Deterministic gather + one bounded model call. Never raises for a"
    facts = gather_client_facts(client_name) if folder is None else gather_client_facts(client_name, folder=folder)
    instructions = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    prompt = PROMPT_TEMPLATE.format(
        instructions=instructions,
        client_name=client_name,
        phone=phone_block(client_phone),
        referral=facts["referral_body_text"][:6000],
        ws=facts["ws_text"][:12000],
        hearing=hearing_block(hearing),
    )
    result = model_backend.run_model(model_backend.ROLE_BRIEF_TO_COUNSEL, prompt, backend="openrouter", timeout=timeout)
    if not result.ok:
        return {"ok": False, "client_name": client_name, "error": "model call failed", "attempts": [
            {"backend": a.backend, "model": a.model, "error": a.error} for a in result.attempts
        ]}
    return {
        "ok": True,
        "client_name": client_name,
        "surname": folder.surname if folder is not None else surname_of(client_name),
        "text": ensure_client_number(result.text, client_phone),
        "client_number_written": bool(client_phone.strip()),
        "model": result.model,
        "served_by": result.served_by,
        "usage": result.usage,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True, help="Full client name, exactly as the AI-EXP folder is named")
    parser.add_argument("--out", help="Write the drafted brief text here instead of stdout")
    args = parser.parse_args(argv)

    try:
        facts_result = draft_brief(args.client)
    except GatherError as exc:
        print(f"blocked: {exc}", file=sys.stderr)
        return 1

    if not facts_result["ok"]:
        print(f"failed: {facts_result['error']}", file=sys.stderr)
        for attempt in facts_result.get("attempts", []):
            print(f"  attempt: {attempt}", file=sys.stderr)
        return 1

    if args.out:
        Path(args.out).write_text(facts_result["text"], encoding="utf-8")
        print(f"Written to {args.out}")
    else:
        print(facts_result["text"])
    print(
        f"model={facts_result['model']} served_by={facts_result['served_by']} usage={facts_result['usage']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
