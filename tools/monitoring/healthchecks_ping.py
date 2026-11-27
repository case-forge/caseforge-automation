#!/usr/bin/env python3
from __future__ import annotations

import os
import threading
import urllib.parse
import urllib.request

try:
    from . import job_stamp
except ImportError:
    import job_stamp

PING_TIMEOUT_SECONDS = 10


def _post(url: str, message: str) -> bool:
    try:
        req = urllib.request.Request(url, data=message.encode("utf-8"), method="POST")
        with urllib.request.urlopen(req, timeout=PING_TIMEOUT_SECONDS):
            return True
    except Exception:
        return False


def ping(base: str, slug: str, *, fail: bool, message: str) -> bool:
    job_stamp.record(slug, not fail, message)
    suffix = "/fail" if fail else ""
    url = f"{base}/{slug}{suffix}?create=1"
    if _post(url, message):
        return True
    parsed = urllib.parse.urlsplit(url)
    if parsed.hostname and parsed.hostname != "127.0.0.1":
        local_url = urllib.parse.urlunsplit(
            parsed._replace(netloc=f"127.0.0.1:{parsed.port}" if parsed.port else "127.0.0.1")
        )
        return _post(local_url, message)
    return False


_HEARTBEAT_THREADS: dict[str, threading.Thread] = {}
_HEARTBEAT_STOPS: dict[str, threading.Event] = {}


def start_heartbeat(slug: str, *, interval_seconds: float = 60.0, message: str = "alive") -> threading.Thread | None:
    base = os.environ.get("CASEFORGE_HEALTHCHECKS_PING_BASE", "").strip().rstrip("/")
    if not base:
        return None
    existing = _HEARTBEAT_THREADS.get(slug)
    if existing is not None and existing.is_alive():
        return existing

    stop = threading.Event()

    def _loop() -> None:
        while not stop.is_set():
            ping(base, slug, fail=False, message=message)
            stop.wait(interval_seconds)

    thread = threading.Thread(target=_loop, name=f"hc-ping-{slug}", daemon=True)
    thread.start()
    _HEARTBEAT_THREADS[slug] = thread
    _HEARTBEAT_STOPS[slug] = stop
    return thread


def stop_heartbeat(slug: str) -> None:
    stop = _HEARTBEAT_STOPS.pop(slug, None)
    thread = _HEARTBEAT_THREADS.pop(slug, None)
    if stop is not None:
        stop.set()
    if thread is not None:
        thread.join(timeout=2.0)
