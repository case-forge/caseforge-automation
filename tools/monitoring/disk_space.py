
from __future__ import annotations

import os
from typing import NamedTuple


class DiskUsage(NamedTuple):
    total: int
    used: int
    available: int
    used_pct: float
    free_pct: float


def usage(path: str | os.PathLike = "/") -> DiskUsage:
    st = os.statvfs(path)
    used = (st.f_blocks - st.f_bfree) * st.f_frsize
    available = st.f_bavail * st.f_frsize
    total = used + available
    used_pct = 100.0 * used / total if total else 0.0
    return DiskUsage(total, used, available, used_pct, 100.0 - used_pct)


def used_pct(path: str | os.PathLike = "/") -> float:
    return usage(path).used_pct


def free_bytes(path: str | os.PathLike = "/") -> int:
    return usage(path).available
