from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from documents import virtual_scanner as vp
from documents import virtual_scanner_preview as vprev
from vergil.http_headers import content_disposition
from scanned_docs import scan_resolver as sr

log = logging.getLogger(__name__)


class VirtualScanRequest(BaseModel):
    matter_id: str = Field(..., min_length=1, max_length=20)
    document_id: str = Field(..., min_length=1, max_length=200)
    date_received: str = Field(..., min_length=10, max_length=10)
    by: str = Field("", max_length=200)
    copies: int = Field(1, ge=1, le=20)


class ScanConfirmRequest(BaseModel):
    item_id: str = Field(..., min_length=1, max_length=200)
    matter_id: str = Field(..., min_length=1, max_length=20)
    copies: int = Field(1, ge=1, le=20)
    by: str = Field("", max_length=200)
    confirm: bool = False
    kind: str = Field("", max_length=30)


class VirtualScanUndoRequest(BaseModel):
    scan_id: str = Field(..., min_length=1, max_length=64)
    by: str = Field("", max_length=200)


class ScanOrderRequest(BaseModel):
    matter_id: str = Field(..., min_length=1, max_length=20)
    folder: str = Field(..., min_length=1, max_length=300)
    name: str = Field(..., min_length=1, max_length=300)
    confirm: bool = False
    by: str = Field("", max_length=200)


class CommonTitleAddRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    by: str = Field("", max_length=200)


class CommonTitleRemoveRequest(BaseModel):
    title_id: str = Field(..., min_length=1, max_length=70)
    by: str = Field("", max_length=200)


def _who(request: Request, typed: str) -> str:
    return (typed or "").strip() or (request.headers.get("Remote-User") or "").strip()


def _run(what: str, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except vp.VirtualScanError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except Exception as exc:
        log.error("virtual scanner %s failed: %s", what, type(exc).__name__)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Virtual scanner {what} unavailable") from exc


def _require_admin(request: Request) -> None:
    from vergil.api import verified_admin_email

    if not verified_admin_email(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")


def router(require_token: Callable[..., None]) -> APIRouter:
    r = APIRouter(dependencies=[Depends(require_token)])

    @r.get("/client-viewer/virtual-scanner", summary="Virtual scanner: the common documents, this client's scans, and whether scanning is possible")
    def virtual_scanner_view(matter_id: str = Query(..., min_length=1, max_length=20)) -> dict[str, Any]:
        out = _run("read", lambda: vp.view(matter_id))
        vprev.warm_async(out.get("documents") or [])
        return out

    @r.get("/client-viewer/virtual-scanner/file", summary="Virtual scanner: one stock PDF from the Common Scanned Docs folder, inline")
    def virtual_scanner_file(document_id: str = Query(..., min_length=1, max_length=200)) -> Response:
        name, data = _run("file", lambda: vp.stock_pdf(document_id))
        return Response(
            data,
            media_type="application/pdf",
            headers={"Content-Disposition": content_disposition("inline", name, "document.pdf"), "Cache-Control": "no-store"},
        )

    @r.get("/client-viewer/virtual-scanner/preview", summary="Virtual scanner: page 1 of one stock PDF as a small JPEG, rendered once and cached")
    def virtual_scanner_preview(document_id: str = Query(..., min_length=1, max_length=200)) -> Response:
        name, image = _run("preview", lambda: vprev.preview(document_id))
        stem = name.rsplit(".", 1)[0] or "document"
        return Response(
            image,
            media_type=vprev.MEDIA_TYPE,
            headers={"Content-Disposition": content_disposition("inline", f"{stem}.jpg", "preview.jpg"), "Cache-Control": "private, max-age=300"},
        )

    @r.post("/client-viewer/virtual-scanner/scan", summary="Virtual scanner: file a stock copy in the client's Court-Orders folder and bill it once")
    def virtual_scanner_print(payload: VirtualScanRequest, request: Request) -> dict[str, Any]:
        who = _who(request, payload.by)
        return _run("scan", lambda: vp.scan_document(payload.matter_id, payload.document_id, payload.date_received, who, copies=payload.copies))

    @r.get("/client-viewer/scans/candidates", summary="Scans: the clients one waiting scan probably belongs to, from the file name and the document's text (read only)")
    def scan_candidates(item_id: str = Query(..., min_length=1, max_length=200)) -> dict[str, Any]:
        return _run("candidates", lambda: sr.candidates_for_item(item_id))

    @r.get("/client-viewer/scans/for-client", summary="Scans: the waiting scans estimated to be this client's (read only)")
    def scans_for_client(matter_id: str = Query(..., min_length=1, max_length=20)) -> dict[str, Any]:
        return _run("candidates", lambda: sr.candidates_for_client(matter_id))

    @r.post("/client-viewer/scans/confirm", summary="Scans: move a confirmed scan from Scanned Docs into the client's folder, with its copies; not billed")
    def scan_confirm(payload: ScanConfirmRequest, request: Request) -> dict[str, Any]:
        who = _who(request, payload.by)
        return _run("confirm", lambda: vp.confirm_scan(payload.item_id, payload.matter_id, payload.copies, who, confirm=payload.confirm, kind=payload.kind))

    @r.post("/client-viewer/virtual-scanner/undo", summary="Virtual scanner: move the copy into 000 Removed, take the charge off the bill, mark it undone")
    def virtual_scanner_undo(payload: VirtualScanUndoRequest, request: Request) -> dict[str, Any]:
        who = _who(request, payload.by)
        return _run("undo", lambda: vp.undo_scan(payload.scan_id, who))

    @r.post("/client-viewer/scanner/scan-order", summary="Scanner: tell Case flow a scanned order filed in Court-Orders is the court's reply (one press, nothing sent)")
    def scanner_scan_order(payload: ScanOrderRequest, request: Request) -> dict[str, Any]:
        who = _who(request, payload.by)
        return _run("scan order", lambda: vp.scan_order(payload.matter_id, payload.folder, payload.name, who, confirm=payload.confirm))

    @r.post("/client-viewer/virtual-scanner/titles/add", summary="Virtual scanner: list a document by its title alone (admins only)")
    def virtual_scanner_title_add(payload: CommonTitleAddRequest, request: Request) -> dict[str, Any]:
        _require_admin(request)
        who = _who(request, payload.by)
        return _run("title", lambda: vp.add_title(payload.title, who))

    @r.post("/client-viewer/virtual-scanner/titles/remove", summary="Virtual scanner: take a typed title off the list (admins only)")
    def virtual_scanner_title_remove(payload: CommonTitleRemoveRequest, request: Request) -> dict[str, Any]:
        _require_admin(request)
        who = _who(request, payload.by)
        return {"removed": _run("title", lambda: vp.remove_title(payload.title_id, who))}

    return r
