from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import env_names

RETENTION_DAYS = 30

MAX_HISTORY_TURNS = 8
MAX_QUESTION_CHARS = 1500
MAX_ANSWER_CHARS = 3000
MAX_HISTORY_CHARS = 16000

_STORED_TEXT_CHARS = 20000

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_lock = threading.Lock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    session_id TEXT PRIMARY KEY,
    anchor TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL DEFAULT '',
    created_utc REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    turn_no INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    client_hint TEXT NOT NULL DEFAULT '',
    created_utc REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_by_session ON turns (session_id, turn_no);
"""


def db_path() -> Path:
    override = os.environ.get("VERGIL_CONVERSATION_DB", "").strip()
    if override:
        return Path(override)
    root = os.environ.get(env_names.TELEMETRY_ROOT, "").strip()
    return (Path(root) if root else _REPO_ROOT / "telemetry") / "vergil-conversations.sqlite3"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5)
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _warn(what: str, exc: BaseException) -> None:
    print(f"[conversation_log] {what}: {type(exc).__name__}", file=sys.stderr)


def _pair(anchor: Optional[str], user: Optional[str]) -> tuple[str, str]:
    return str(anchor or "").strip(), str(user or "").strip()


def bind(session_id: str, anchor: Optional[str], user: Optional[str]) -> None:
    if not session_id:
        return
    try:
        with _lock, _connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO conversations (session_id, anchor, username, created_utc) VALUES (?, ?, ?, ?)",
                (session_id, *_pair(anchor, user), time.time()),
            )
    except (sqlite3.Error, OSError) as exc:
        _warn("binding not saved", exc)


def binding(session_id: Optional[str]) -> Optional[tuple[str, str]]:
    if not session_id:
        return None
    try:
        with _lock, _connect() as conn:
            row = conn.execute("SELECT anchor, username FROM conversations WHERE session_id = ?", (session_id,)).fetchone()
    except (sqlite3.Error, OSError) as exc:
        _warn("binding not read", exc)
        return None
    return (str(row[0]), str(row[1])) if row else None


def append_turn(session_id: Optional[str], question: str, answer: str, *, client_hint: str = "") -> None:
    if not session_id or not str(answer or "").strip():
        return
    try:
        with _lock, _connect() as conn:
            conn.execute(
                "INSERT INTO turns (session_id, question, answer, client_hint, created_utc) VALUES (?, ?, ?, ?, ?)",
                (
                    session_id,
                    str(question or "")[:_STORED_TEXT_CHARS],
                    str(answer)[:_STORED_TEXT_CHARS],
                    str(client_hint or "")[:1000],
                    time.time(),
                ),
            )
    except (sqlite3.Error, OSError) as exc:
        _warn("turn not saved", exc)


def _clip(text: str, limit: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " ...[shortened]"


def recent_turns(session_id: Optional[str], anchor: Optional[str], user: Optional[str]) -> list[dict]:
    if not session_id or binding(session_id) != _pair(anchor, user):
        return []
    try:
        with _lock, _connect() as conn:
            rows = conn.execute(
                "SELECT question, answer, client_hint FROM turns WHERE session_id = ? ORDER BY turn_no DESC LIMIT ?",
                (session_id, MAX_HISTORY_TURNS),
            ).fetchall()
    except (sqlite3.Error, OSError) as exc:
        _warn("history not read", exc)
        return []
    kept: list[dict] = []
    used = 0
    for question, answer, client_hint in rows:
        turn = {
            "question": _clip(question, MAX_QUESTION_CHARS),
            "answer": _clip(answer, MAX_ANSWER_CHARS),
            "client_hint": str(client_hint or ""),
        }
        size = len(turn["question"]) + len(turn["answer"])
        if kept and used + size > MAX_HISTORY_CHARS:
            break
        kept.append(turn)
        used += size
    kept.reverse()
    return kept


def prune(*, days: int = RETENTION_DAYS, now: Optional[float] = None) -> int:
    cutoff = (time.time() if now is None else now) - days * 86400
    with _lock, _connect() as conn:
        stale = (
            "SELECT c.session_id FROM conversations c WHERE c.created_utc < ? AND NOT EXISTS "
            "(SELECT 1 FROM turns t WHERE t.session_id = c.session_id AND t.created_utc >= ?)"
        )
        removed = conn.execute(f"DELETE FROM turns WHERE session_id IN ({stale})", (cutoff, cutoff)).rowcount
        conn.execute(f"DELETE FROM conversations WHERE session_id IN ({stale})", (cutoff, cutoff))
        removed += conn.execute(
            "DELETE FROM turns WHERE created_utc < ? AND session_id NOT IN (SELECT session_id FROM conversations)", (cutoff,)
        ).rowcount
    return int(removed)
