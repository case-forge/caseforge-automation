from __future__ import annotations

import logging

_LOG = logging.getLogger("vergil_chat.errors")


def user_safe_error(exc: BaseException, action: str = "That step") -> str:
    _LOG.warning("%s failed: %s", action, type(exc).__name__)
    return f"{action} did not work. Please try again; if it keeps happening, tell the team."
