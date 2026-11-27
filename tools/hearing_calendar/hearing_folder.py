from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def _default_matter_path(matter_id: str) -> str:
    import agwu

    found = agwu.resolve_folder(matter_id, caller="hearing_folder.ensure_hearing_folder")
    return str(getattr(found, "matter_folder_path", "") or "") if getattr(found, "status", "") != "not_found" else ""


def _default_surname(matter_id: str) -> str:
    import clientdb_sql
    from folder_surname import folder_surname

    row = clientdb_sql.get_client_by_matter_id(matter_id) or {}
    return folder_surname(str(row.get("canonical_name") or ""))


def ensure_hearing_folder(
    hearing: Mapping[str, Any],
    *,
    matter_path: Callable[[str], str] | None = None,
    surname_for: Callable[[str], str] | None = None,
    list_children: Callable[[str], dict[str, Any]] | None = None,
    create_folder: Callable[[str, str], Any] | None = None,
) -> dict[str, str]:
    try:
        import graph_files
        from hearing_calendar import hearing_dates

        matter_id = str(hearing.get("matter_id") or "").strip()
        days = hearing_dates.span_days(hearing)
        if not matter_id or not days or str(hearing.get("status") or "scheduled") != "scheduled":
            return {"status": "skipped"}
        path = (matter_path or _default_matter_path)(matter_id)
        surname = (surname_for or _default_surname)(matter_id)
        if not path or not surname:
            return {"status": "no_matter_folder"}
        listing = (list_children or graph_files.list_children)(path)
        for item in listing.get("value", []):
            if "folder" not in item:
                continue
            kind = graph_files.folder_kind(str(item.get("name") or ""))
            if kind.kind == "hearing" and kind.date == days[0]:
                return {"status": "exists"}
        (create_folder or graph_files.create_folder)(path, hearing_dates.folder_name(hearing, surname))
        return {"status": "created"}
    except Exception as exc:
        return {"status": "error", "reason": type(exc).__name__}
