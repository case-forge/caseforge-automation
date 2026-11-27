#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import telemetry_sqlite

if TYPE_CHECKING:
    from agwu.client import ClientResolution
    from agwu.folder import FolderResolution


def _write_event(event_type: str, payload: dict) -> None:
    try:
        telemetry_sqlite.record_runtime_event(
            {
                "timestamp": telemetry_sqlite.utc_now_z(),
                "event_name": event_type,
                "runtime_label": os.environ.get("CASEFORGE_RUNTIME_LABEL", ""),
                "model_label": os.environ.get("CASEFORGE_MODEL_LABEL", ""),
                "command": "",
                "files_read": [],
                "files_written": [],
                "metrics": payload,
            }
        )
    except Exception:
        pass


def log_client_resolution(query: str, result: "ClientResolution", *, caller: str) -> None:
    top = result.top
    _write_event(
        "agwu_resolve_client",
        {
            "caller": caller,
            "query": query,
            "status": result.status,
            "score": top.score if top else None,
            "margin": top.margin if top else None,
            "matched_client": top.row.get("client_name") if top else None,
        },
    )


def log_folder_resolution(matter_id: str, result: "FolderResolution", *, caller: str) -> None:
    _write_event(
        "agwu_resolve_folder",
        {
            "caller": caller,
            "matter_id": matter_id,
            "status": result.status,
            "source": result.source,
        },
    )
