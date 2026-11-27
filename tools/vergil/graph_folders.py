
from __future__ import annotations

import re
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

from sql.client_name_resolver import strip_c8_tag
from vergil.attendance import choose_attendance_folder
from vergil.primitives import normalise_space, prompt_lower, safe_upload_name

try:
    import firm_profile
except ImportError:
    from tools import firm_profile

ONEDRIVE_ROOT_PREFIX = firm_profile.load_profile().onedrive_root_name + "/"


def normalise_matter_folder_path(path: str) -> str:
    cleaned = (path or "").replace("\\", "/").strip("/")
    if cleaned.startswith(ONEDRIVE_ROOT_PREFIX):
        cleaned = cleaned.split(ONEDRIVE_ROOT_PREFIX, 1)[1]
    return cleaned


def graph_children(tool, token: str, drive_id: str, path: str) -> list[dict]:
    encoded = urllib.parse.quote(path.strip("/"), safe="/")
    payload = tool._graph_json(f"{tool.GRAPH}/drives/{drive_id}/root:/{encoded}:/children", token)
    return list(payload.get("value") or [])


def graph_children_by_id(tool, token: str, drive_id: str, folder_id: str) -> list[dict]:
    payload = tool._graph_json(f"{tool.GRAPH}/drives/{drive_id}/items/{folder_id}/children", token)
    return list(payload.get("value") or [])


def graph_search(tool, token: str, drive_id: str, query: str, limit: int = 30) -> list[dict]:
    safe_query = urllib.parse.quote(query.strip())
    payload = tool._graph_json(f"{tool.GRAPH}/drives/{drive_id}/root/search(q='{safe_query}')", token)
    return list(payload.get("value") or [])[:limit]


def lookup_cached_folder_location(row: dict, client_query: str) -> dict:
    try:
        import agwu

        matter_id = str(row.get("matter_id") or "").strip()
        _result = agwu.resolve_folder(matter_id, caller="vergil.graph_folders.lookup_cached_folder_location")
        return _result.__dict__ if _result.status != "not_found" else {}
    except Exception:
        return {}


def cache_verified_folder_location(
    row: dict,
    *,
    drive_id: str,
    matter_folder: dict | None = None,
    matter_path: str = "",
    attendance_folder_id: str = "",
    attendance_folder_name: str = "",
) -> None:
    matter_id = str(row.get("matter_id") or "").strip()
    if not matter_id:
        return
    try:
        from clientdb_sql import upsert_matter_folder_location

        folder = matter_folder or {}
        parent_path = str((folder.get("parentReference") or {}).get("path") or "")
        folder_name = str(folder.get("name") or "").strip()
        path = matter_path
        if not path and parent_path and folder_name:
            root_marker = "/root:"
            if root_marker in parent_path:
                path = f"{parent_path.split(root_marker, 1)[1].strip('/')}/{folder_name}".strip("/")
        upsert_matter_folder_location(
            matter_id=matter_id,
            client_name=str(row.get("client_name") or "").strip(),
            matter_name=str(row.get("matter_name") or "").strip(),
            matter_folder_path=normalise_matter_folder_path(path),
            matter_folder_name=folder_name,
            matter_folder_id=str(folder.get("id") or "").strip(),
            attendance_folder_id=attendance_folder_id,
            attendance_folder_name=attendance_folder_name,
            drive_id=drive_id,
            source="caseforge-chat",
        )
    except Exception:
        return


def find_matter_folder_by_graph_search(tool, token: str, drive_id: str, client_name: str, prompt: str) -> dict:
    search_items = graph_search(tool, token, drive_id, client_name, limit=80)
    folders = [item for item in search_items if item.get("folder")]
    query_norm = normalise_space(client_name).lower()
    exact = next(
        (item for item in folders if str(item.get("name", "")).lower() == query_norm
         or strip_c8_tag(str(item.get("name", ""))).lower() == query_norm),
        None,
    )
    if exact:
        return exact
    contains = [item for item in folders if query_norm and query_norm in str(item.get("name", "")).lower()]
    if len(contains) == 1:
        return contains[0]
    lowered_prompt = prompt_lower(prompt)
    for keyword in ("pso", "cao", "nmo", "referralpartner"):
        if keyword in lowered_prompt:
            match = next((item for item in contains if keyword in str(item.get("name", "")).lower()), None)
            if match:
                return match
    if contains:
        return contains[0]
    surname = client_name.strip().split()[-1].lower() if client_name.strip().split() else ""
    if surname:
        match = next((item for item in folders if surname in str(item.get("name", "")).lower()), None)
        if match:
            return match
    raise RuntimeError(f"No OneDrive matter folder found for: {client_name}")


def find_attendance_folder(tool, token: str, drive_id: str, matter_path: str, prompt: str) -> tuple[str, str]:
    children = graph_children(tool, token, drive_id, matter_path)
    return choose_attendance_folder(children, prompt)


def find_attendance_folder_by_search(tool, token: str, drive_id: str, client_name: str, prompt: str) -> tuple[str, str]:
    matter_folder = find_matter_folder_by_graph_search(tool, token, drive_id, client_name, prompt)
    children = graph_children_by_id(tool, token, drive_id, str(matter_folder["id"]))
    return choose_attendance_folder(children, prompt)


def find_attendance_folder_location_by_search(tool, token: str, drive_id: str, client_name: str, prompt: str) -> tuple[dict, str, str]:
    matter_folder = find_matter_folder_by_graph_search(tool, token, drive_id, client_name, prompt)
    children = graph_children_by_id(tool, token, drive_id, str(matter_folder["id"]))
    folder_id, folder_name = choose_attendance_folder(children, prompt)
    return matter_folder, folder_id, folder_name


def extract_graph_matter_snapshot(tool, token: str, drive_id: str, client_query: str, prompt: str) -> dict:
    from docx import Document

    search_items = graph_search(tool, token, drive_id, client_query, limit=50)
    query_norm = normalise_space(client_query).lower()
    folders = [item for item in search_items if item.get("folder")]
    matter_folder = next((item for item in folders if str(item.get("name", "")).lower() == query_norm), None)
    if matter_folder is None:
        matches_contains = [item for item in folders if query_norm in str(item.get("name", "")).lower()]
        if len(matches_contains) == 1:
            matter_folder = matches_contains[0]
        elif len(matches_contains) > 1:
            lowered_prompt = prompt.lower()
            kw_map = [
                ("nmo", "nmo"), ("fl401", "nmo"), ("non-mol", "nmo"), ("non mol", "nmo"),
                ("referralpartner", "referralpartner"), ("referrer", "dv"), ("domestic violence", "dv"),
                ("c100", "c100"), ("cao", "cao"), ("children act", "cao"),
                ("pso", "pso"), ("fl404", "pso"),
            ]
            for kw, hint in kw_map:
                if kw in lowered_prompt:
                    for item in matches_contains:
                        if hint in str(item.get("name", "")).lower():
                            matter_folder = item
                            break
                    if matter_folder:
                        break
            if matter_folder is None:
                matter_folder = matches_contains[0]
    if matter_folder is None:
        surname = client_query.strip().split()[-1].lower()
        if surname and surname != query_norm:
            matter_folder = next(
                (item for item in folders if surname in str(item.get("name", "")).lower()),
                None,
            )
    if matter_folder is None:
        raise RuntimeError(f"No OneDrive matter folder found for: {client_query}")

    children = graph_children_by_id(tool, token, drive_id, str(matter_folder["id"]))
    folder_id, folder_name = choose_attendance_folder(children, prompt)
    ref_pattern = re.compile(r"\b(?:[A-Z]{2}/[A-Z0-9]+/\d{6}/\d+[A-Z]{2}|\d{6}/\d{2}[A-Z]{2})\b")
    laa_refs: list[str] = []
    internal_refs: list[str] = []
    an_phones_from_ans: list[str] = []
    an_matters_from_ans: list[str] = []
    root_docx_refs: list[str] = []
    an_folder_refs: list[str] = []

    noa_refs: list[str] = []

    with tempfile.TemporaryDirectory(prefix="caseforge-chat-graph-matter-") as tmp:
        tmp_path = Path(tmp)

        root_docx_items = [i for i in children if str(i.get("name","")).lower().endswith(".docx")]
        for item in root_docx_items:
            name = str(item.get("name") or "")
            name_lower = name.lower()
            is_noa = any(kw in name_lower for kw in ("notice of acting", "noa", "notice_of_acting"))
            try:
                local_path = tmp_path / safe_upload_name(name)
                local_path.write_bytes(tool._graph_bytes(f"{tool.GRAPH}/drives/{drive_id}/items/{item['id']}/content", token))
                doc = Document(local_path)
                text = "\n".join(p.text for p in doc.paragraphs)
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            text += "\n" + "\n".join(p.text for p in cell.paragraphs)
                found = ref_pattern.findall(text)
                if is_noa:
                    noa_refs.extend(found)
                else:
                    root_docx_refs.extend(found)
            except Exception:
                continue

        try:
            att_children = graph_children_by_id(tool, token, drive_id, folder_id)
            recent_ans = sorted(
                [i for i in att_children if str(i.get("name","")).lower().endswith(".docx")],
                key=lambda x: x.get("lastModifiedDateTime", ""),
                reverse=True,
            )[:5]
            for item in recent_ans:
                name = str(item.get("name") or "")
                try:
                    local_path = tmp_path / ("an_" + safe_upload_name(name))
                    local_path.write_bytes(tool._graph_bytes(f"{tool.GRAPH}/drives/{drive_id}/items/{item['id']}/content", token))
                    doc = Document(local_path)
                    text = "\n".join(p.text for p in doc.paragraphs)
                    for table in doc.tables:
                        for row in table.rows:
                            cells = [c.text.strip() for c in row.cells]
                            if len(cells) >= 2:
                                key = cells[0].strip("*| ").lower()
                                val = cells[1].strip("*| ")
                                if key in ("phone", "tel", "telephone") and re.match(r"0\d", val):
                                    an_phones_from_ans.append(re.sub(r"[\s\-]", "", val))
                                elif key in ("order type", "matter", "order") and val and len(val) <= 15:
                                    an_matters_from_ans.append(val.upper())
                            for cell in row.cells:
                                text += "\n" + "\n".join(p.text for p in cell.paragraphs)
                    an_folder_refs.extend(ref_pattern.findall(text))
                except Exception:
                    continue
        except Exception:
            pass

        laa_pdfs = [i for i in children if str(i.get("name","")).lower().endswith(".pdf")
                    and any(kw in str(i.get("name","")).lower() for kw in ("laa", "certificate", "cert"))]
        for item in laa_pdfs:
            try:
                pdf_path = tmp_path / safe_upload_name(str(item.get("name","")))
                pdf_path.write_bytes(tool._graph_bytes(f"{tool.GRAPH}/drives/{drive_id}/items/{item['id']}/content", token))
                txt_path = pdf_path.with_suffix(".txt")
                subprocess.run(["pdftotext", str(pdf_path), str(txt_path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
                if txt_path.exists():
                    laa_refs.extend(ref_pattern.findall(txt_path.read_text(errors="ignore")))
            except Exception:
                continue

    from collections import Counter
    def _majority(refs: list[str]) -> str:
        if not refs:
            return ""
        counts = Counter(refs)
        top = counts.most_common(1)[0][1]
        return sorted(r for r, c in counts.items() if c == top)[-1]

    if noa_refs:
        internal_ref = _majority(noa_refs)
    elif laa_refs:
        internal_ref = _majority(laa_refs)
    elif an_folder_refs:
        internal_ref = _majority(an_folder_refs)
    elif root_docx_refs:
        internal_ref = _majority(root_docx_refs)
    else:
        internal_ref = ""

    phones: list[str] = []
    c8_phones: list[str] = []
    for item in search_items:
        name = str(item.get("name") or "")
        if not name.lower().endswith(".pdf") or not any(token in name.lower() for token in ("intro", "c8", "contact")):
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="caseforge-chat-pdf-contact-") as tmp:
                pdf = Path(tmp) / "contact.pdf"
                txt = Path(tmp) / "contact.txt"
                pdf.write_bytes(tool._graph_bytes(f"{tool.GRAPH}/drives/{drive_id}/items/{item['id']}/content", token))
                subprocess.run(["pdftotext", str(pdf), str(txt)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
                text = txt.read_text(errors="ignore") if txt.exists() else ""
                found = re.findall(r"\b0\d(?:[\s-]?\d){9,10}\b", text)
                phones.extend(found)
                if "c8" in name.lower():
                    c8_phones.extend(found)
        except Exception:
            continue

    raw_folder_name = str(matter_folder.get("name") or client_query).strip()
    clean_client_name = re.sub(
        r"[\s]*[-–][\s]*(?:referralpartner|nmo|cao|pso|sio|oo|solace|ncdv|dv[\s\-]?assist)\b.*$",
        "",
        strip_c8_tag(raw_folder_name),
        flags=re.I,
    ).strip() or raw_folder_name

    lp = prompt.lower()
    fn_lower = raw_folder_name.lower()
    _has_nmo = any(k in lp for k in ("nmo", "non-mol", "fl401", "non molestation", "non-molestation")) or "nmo" in fn_lower
    _has_pso = any(k in lp for k in ("pso", "prohibited steps", "fl404")) or "pso" in fn_lower
    _has_cao = any(k in lp for k in ("cao", "child arrangement", "c100", "contact order")) or "cao" in fn_lower
    _has_sio = any(k in lp for k in ("sio", "specific issue")) or "sio" in fn_lower
    if _has_nmo and _has_pso and _has_cao:
        order_text = "NMO-CAO-PSO"
    elif _has_nmo and _has_pso:
        order_text = "NMO-PSO"
    elif _has_nmo and _has_cao:
        order_text = "NMO-CAO"
    elif _has_cao and _has_pso:
        order_text = "CAO-PSO"
    elif _has_nmo:
        order_text = "NMO"
    elif _has_cao:
        order_text = "CAO"
    elif _has_pso:
        order_text = "PSO"
    elif _has_sio:
        order_text = "SIO"
    else:
        order_text = ""

    if not phones:
        for item in search_items:
            name = str(item.get("name") or "")
            if not name.lower().endswith(".pdf"):
                continue
            if not any(kw in name.lower() for kw in ("new client", "client form", "contact", "intro", "c8")):
                continue
            try:
                with tempfile.TemporaryDirectory(prefix="caseforge-chat-pdf2-") as tmp2:
                    pdf2 = Path(tmp2) / "doc.pdf"
                    txt2 = Path(tmp2) / "doc.txt"
                    pdf2.write_bytes(tool._graph_bytes(f"{tool.GRAPH}/drives/{drive_id}/items/{item['id']}/content", token))
                    subprocess.run(["pdftotext", str(pdf2), str(txt2)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
                    text2 = txt2.read_text(errors="ignore") if txt2.exists() else ""
                    found2 = re.findall(r"\b0\d(?:[\s-]?\d){9,10}\b", text2)
                    phones.extend(found2)
            except Exception:
                continue

    if not phones:
        for item in children:
            name = str(item.get("name") or "")
            if not name.lower().endswith(".docx"):
                continue
            n = name.lower()
            if not ("client" in n and ("form" in n or "new" in n)):
                continue
            try:
                with tempfile.TemporaryDirectory(prefix="caseforge-chat-nc-") as tmp3:
                    local = Path(tmp3) / "nc.docx"
                    local.write_bytes(tool._graph_bytes(f"{tool.GRAPH}/drives/{drive_id}/items/{item['id']}/content", token))
                    nc_doc = Document(local)
                    nc_text = "\n".join(p.text for p in nc_doc.paragraphs)
                    for tbl in nc_doc.tables:
                        for row in tbl.rows:
                            for cell in row.cells:
                                nc_text += "\n" + "\n".join(p.text for p in cell.paragraphs)
                    phones.extend(re.findall(r"\b0\d(?:[\s-]?\d){9,10}\b", nc_text))
            except Exception:
                continue

    if not phones and not c8_phones and an_phones_from_ans:
        phones = [_majority(an_phones_from_ans)] if an_phones_from_ans else []

    if not order_text and an_matters_from_ans:
        order_text = _majority(an_matters_from_ans)

    return {
        "client_name": clean_client_name,
        "company_reference": internal_ref,
        "phone_primary": (
            sorted(set(p.replace(" ", "").replace("-", "") for p in (c8_phones or phones)))[-1]
            if (c8_phones or phones) else ""
        ),
        "order_requested_text": order_text,
        "has_c8": any("c8" in str(item.get("name", "")).lower() for item in search_items),
        "attendance_folder_id": folder_id,
        "attendance_folder_name": folder_name,
    }
