
import { MAX_COPIES, WARN_COPIES, parseCopies } from "./virtualScannerTypes";

export type ScanKind = "order" | "notice_of_hearing" | "other";

export interface ScanCandidate {
  matter_id: string;
  client_name: string;
  closed: boolean;

  confidence: number;

  words: string;
  reasons: string[];

  ambiguous: boolean;
}

export interface ScanCandidates {
  id: string;
  name: string;
  text_read: boolean;
  kind: ScanKind;
  candidates: ScanCandidate[];
  label: string;
}

export interface ClientScan extends ScanCandidates {
  scan_date: string;
  date_source: string;
  web_url: string;
}

export interface ConfirmResult {
  message: string;
  already: boolean;
  copies: number;
  case_flow: { ok: boolean; message: string; needs_confirm: boolean } | null;
}

export { MAX_COPIES, WARN_COPIES, parseCopies };

export function confidenceLabel(c: Pick<ScanCandidate, "confidence" | "words">): string {
  return `${c.confidence} out of 100, ${c.words}`;
}

export function ambiguityNote(c: ScanCandidate | undefined): string {
  return c?.ambiguous ? "Two clients are close. Check the reasons and pick the right one." : "";
}

export function kindLabel(kind: ScanKind): string {
  return kind === "order" ? "Court order: Case flow will be told it came in" : kind === "notice_of_hearing" ? "Notice of hearing" : "";
}

export function confirmBlockedReason(matterId: string, copiesText: string, busy: boolean): string {
  if (busy) return "Working...";
  if (!matterId) return "Pick the client first.";
  const n = Number(copiesText);
  if (!Number.isInteger(n) || n < 1 || n > MAX_COPIES) return `Copies must be a whole number from 1 to ${MAX_COPIES}.`;
  return "";
}

export function confirmCopiesWarning(copiesText: string): string {
  const n = parseCopies(copiesText);
  return n > WARN_COPIES ? `${n} copies is more than usual (two: one for the file, one to serve). Check before you press Confirm.` : "";
}

export function bestGuess(c: ScanCandidates | undefined): ScanCandidate | undefined {
  return c?.candidates[0];
}

async function readError(res: Response, fallback: string): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(typeof body?.error === "string" && body.error ? body.error : fallback);
}

export async function fetchCandidates(itemId: string): Promise<ScanCandidates> {
  const res = await fetch(`/api/scans/candidates?item_id=${encodeURIComponent(itemId)}`, { cache: "no-store" });
  if (!res.ok) return readError(res, "Could not estimate the client for this scan.");
  return res.json();
}

export async function fetchClientScans(matterId: string): Promise<ClientScan[]> {
  const res = await fetch(`/api/scans/for-client?matter_id=${encodeURIComponent(matterId)}`, { cache: "no-store" });
  if (!res.ok) return readError(res, "Could not look for this client's waiting scans.");
  const body = await res.json();
  return Array.isArray(body?.scans) ? body.scans : [];
}

export async function confirmScan(itemId: string, matterId: string, copies: number, kind: ScanKind, confirm = false): Promise<ConfirmResult> {
  const res = await fetch("/api/scans/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ item_id: itemId, matter_id: matterId, copies, kind, confirm }),
  });
  if (!res.ok) return readError(res, "The scan was not filed.");
  return res.json();
}
