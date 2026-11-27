"use client";

import { useCallback, useEffect, useState } from "react";
import type { CommonDocument, LastOrder, ScanOrderResult, VirtualScan, VirtualScannerView, VirtualScanResult } from "./virtualScannerTypes";

async function readError(res: Response, fallback: string): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(typeof body?.error === "string" && body.error ? body.error : fallback);
}

async function postJson<T>(path: string, body: unknown, fallback: string): Promise<T> {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) return readError(res, fallback);
  return res.json();
}

export function virtualScannerFileUrl(documentId: string): string {
  return `/api/virtual-scanner/file?document_id=${encodeURIComponent(documentId)}`;
}

export const PREVIEW_WIDTH = 900;
export const PREVIEW_HEIGHT = 1273;

export function virtualScannerPreviewUrl(documentId: string): string {
  return `/api/virtual-scanner/preview?document_id=${encodeURIComponent(documentId)}`;
}

export async function fetchVirtualScanner(matterId: string): Promise<VirtualScannerView> {
  const res = await fetch(`/api/virtual-scanner?matter_id=${encodeURIComponent(matterId)}`, { cache: "no-store" });
  if (!res.ok) return readError(res, "Could not load the virtual scanner.");
  return res.json();
}

export function useVirtualScanner(matterId: string) {
  const [data, setData] = useState<VirtualScannerView | null>(null);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    fetchVirtualScanner(matterId)
      .then((view) => {
        if (!cancelled) {
          setData(view);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the virtual scanner.");
      });
    return () => {
      cancelled = true;
    };
  }, [matterId, nonce]);

  return { data, error, refresh };
}

export function scanCommonDocument(matterId: string, documentId: string, dateReceived: string, copies = 1): Promise<VirtualScanResult> {
  return postJson("/api/virtual-scanner/scan", { matter_id: matterId, document_id: documentId, date_received: dateReceived, copies }, "Nothing was scanned.");
}

export function undoVirtualScan(scanId: string): Promise<VirtualScan & { message: string }> {
  return postJson("/api/virtual-scanner/undo", { scan_id: scanId }, "The scan was not undone.");
}

export function scanOrder(matterId: string, order: LastOrder, confirm = false): Promise<ScanOrderResult> {
  return postJson("/api/scanner/scan-order", { matter_id: matterId, folder: order.folder, name: order.name, confirm }, "Case flow was not told.");
}

export function addCommonTitle(title: string): Promise<{ title_id: string; title: string }> {
  return postJson("/api/virtual-scanner/titles/add", { title }, "The title was not added.");
}

export function removeCommonTitle(document: CommonDocument): Promise<{ removed: boolean }> {
  return postJson("/api/virtual-scanner/titles/remove", { title_id: document.document_id }, "The title was not removed.");
}
