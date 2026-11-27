#!/usr/bin/env python3

from __future__ import annotations

import urllib.error
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from documents import docx_template_fill, order_registry
from onboarding import notice_of_acting
from documents import draft_orders


class PsoPackError(RuntimeError):
    pass


def record_runtime_event(status: str, details: Mapping[str, Any], *, files_written: Sequence[str]) -> None:
    try:
        from telemetry_sqlite import record_runtime_event as _record, utc_now_z

        _record(
            {
                "timestamp": utc_now_z(),
                "event_name": "pso_pack_from_sql",
                "runtime_label": os.environ.get("CASEFORGE_RUNTIME_LABEL", ""),
                "model_label": os.environ.get("CASEFORGE_MODEL_LABEL", ""),
                "command": "tools.draft_order_packs.make_pso_pack_from_sql",
                "files_read": [],
                "files_written": list(files_written),
                "metrics": {
                    "status": status,
                    "matter_id": draft_orders.clean_text(details.get("matter_id")),
                },
            }
        )
    except Exception:
        pass


def find_existing_pso(children: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    def is_pso(name: str) -> bool:
        lowered = name.lower()
        if not re.search(r"(?<![a-z])draft(?![a-z])", lowered):
            return False
        return ("prohibited" in lowered and "steps" in lowered) or bool(re.search(r"(?<![a-z])pso(?![a-z])", lowered))

    matches = [dict(item) for item in children if is_pso(draft_orders.clean_text(item.get("name")))]
    if not matches:
        return None
    matches.sort(key=lambda item: draft_orders.clean_text(item.get("name")).lower())
    return matches[0]


def signed_statement_date_for(matter_path: str, children: list[Mapping[str, Any]], surname: str, access_token: str | None = None) -> str:
    import tempfile

    wanted = f"ws.{surname}.pdf".lower()
    files = draft_orders.list_candidate_files(matter_path, children, access_token=access_token)
    signed = [f for f in files if draft_orders.clean_text(f.get("name")).lower() == wanted]
    if not signed:
        return ""
    signed.sort(key=draft_orders._modified_key, reverse=True)
    try:
        with tempfile.TemporaryDirectory(prefix="caseforge-pso-ws-") as tmp:
            path = Path(tmp) / "ws.pdf"
            draft_orders._download_item(signed[0], path, access_token=access_token)
            return draft_orders.signed_statement_date(draft_orders.extract_document_text(path))
    except Exception:
        return ""


def make_pso_pack_from_sql(matter_id: str, details: Mapping[str, Any], *, access_token: str | None = None) -> dict[str, Any]:
    codes = notice_of_acting.normalise_order_codes(details)
    if "PSO" not in codes:
        return {"ok": False, "message": "This matter has no PSO in its order codes."}

    matter_path = draft_orders.normalise_graph_path(details.get("live_matter_folder"))
    if not matter_path:
        return {"ok": False, "message": "No live matter folder is recorded for this matter."}
    parties = draft_orders.load_parties(matter_id)

    children = draft_orders.direct_children(matter_path, access_token=access_token)
    if not children:
        return {"ok": False, "message": "Could not list the live matter folder."}
    preliminary = draft_orders.choose_folder(children, "preliminary")
    if not preliminary:
        return {"ok": False, "message": "No Preliminary Docs folder found under the matter folder."}

    existing_files = draft_orders.direct_children(
        draft_orders.clean_text(preliminary.get("path")), item_type="file", access_token=access_token
    )
    existing = find_existing_pso(existing_files)
    if existing:
        return {"ok": True, "status": "exists", "message": "Draft Prohibited Steps Order already exists.", "item": existing}

    client_name = draft_orders.clean_text(details.get("client_name") or details.get("matter_name"))
    surname = draft_orders._surname(client_name)
    sql_source_facts = draft_orders.sql_facts(details, parties)
    sql_source_facts["statement_date"] = signed_statement_date_for(matter_path, children, surname, access_token) or "[date of statement]"
    order_data = draft_orders.order_template_data(sql_source_facts, details, order_codes_override={"PSO"})

    import tempfile

    with tempfile.TemporaryDirectory(prefix="caseforge-pso-pack-") as tmp:
        tmp_path = Path(tmp)
        pso_filename = draft_orders.safe_filename(f"Draft-PSO-{surname}.docx")
        pso_output = tmp_path / pso_filename
        order_registry.fill_house_order("PSO", pso_output, draft_orders.judge_order_data(order_data, children_required=True))
        try:
            uploaded = draft_orders.upload_file(
                pso_output, draft_orders.clean_text(preliminary.get("path")), pso_filename, access_token=access_token
            )
        except urllib.error.HTTPError as exc:
            if exc.code != 409:
                raise
            return {"ok": True, "status": "exists", "message": "Draft Prohibited Steps Order already exists.", "item": {"name": pso_filename}}

    has_c8 = bool(details.get("has_c8"))
    message = f"Created Draft Prohibited Steps Order for {client_name}."
    if has_c8:
        message = "C8: applicant contact details withheld. " + message

    record_runtime_event(
        "created",
        details,
        files_written=[draft_orders.clean_text(uploaded.get("webUrl") or uploaded.get("destination"))],
    )

    return {
        "ok": True,
        "status": "created",
        "message": message,
        "client_name": client_name,
        "matter_id": matter_id,
        "has_c8": has_c8,
        "files": [{**uploaded, "kind": "Draft PSO"}],
    }
