from __future__ import annotations

import os
import sys

ENV_NAME = "SIGNIN_NAMES"
NAME_LIMIT = 60


def parse(text: str) -> dict[str, str]:
    names: dict[str, str] = {}
    for pair in str(text or "").split(";"):
        email, _, name = pair.partition("=")
        email, name = email.strip().lower(), " ".join(name.split())[:NAME_LIMIT]
        if email and name:
            names[email] = name
    return names


def display_name(remote_user: str, env: dict[str, str] | None = None) -> str:
    who = (remote_user or "").strip()
    if not who:
        return ""
    source = os.environ if env is None else env
    return parse(source.get(ENV_NAME, "")).get(who.lower(), who)


if __name__ == "__main__":
    print(display_name(sys.argv[1]) if len(sys.argv) > 1 else "")
