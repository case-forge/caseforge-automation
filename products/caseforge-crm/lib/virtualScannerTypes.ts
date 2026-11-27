
export interface CommonDocument {
  document_id: string;
  title: string;
  file_name: string;
  has_file: boolean;

  also_named: string[];
  web_url: string;
  added_by: string;
}

export interface VirtualScan {
  scan_id: string;
  matter_id: string;
  document_id: string;
  document_title: string;
  date_received: string;
  pressed_by: string;
  pressed_utc: string;
  filed_path: string;
  filed_url: string;
  file_name: string;
  billing_item_id: string;
  billing_note: string;
  pages: number | null;
  text_chars: number | null;
  status: "filed" | "undone";
  undone_by: string;
  undone_utc: string;
  moved_to: string;

  copies: number;
}

export interface LastOrder {
  name: string;
  kind: "order" | "notice_of_hearing";
  date: string;

  date_source: string;

  hearing_date: string;
  folder: string;
  web_url: string;

  recorded?: boolean;
}

export interface ScanOrderResult {
  ok: boolean;
  message: string;
  needs_confirm: boolean;
}

export interface OrderExpected {
  hearing_date: string;
  line: string;
}

export interface ScanHint {
  name: string;
  web_url: string;
  hearing_date: string;
  surname_matches: boolean;
  line: string;
  label: string;
}

export interface VirtualScannerView {
  last_order: LastOrder | null;

  orders: LastOrder[];

  email_reply_filed: boolean;
  orders_expected: OrderExpected[];
  scan_hints: ScanHint[];
  hint_errors: string[];
  matter_id: string;
  today: string;
  can_scan: boolean;
  refusal: string;
  court_orders_folder: string;
  folder: string;
  documents: CommonDocument[];
  other_files: string[];
  folder_error: string;
  scans: VirtualScan[];
}

export interface VirtualScanResult extends VirtualScan {
  already: boolean;
  message: string;
}

const DATE_SOURCE_WORDS: Record<string, string> = {
  filename: "from the file name",
  uploaded: "the upload date",
  modified: "the last changed date",
  unknown: "date not known",
};

export function lastOrderLine(order: LastOrder): string {
  const when = order.date ? `${longDate(order.date)}, ${DATE_SOURCE_WORDS[order.date_source] ?? order.date_source}` : "Date not known";
  const kind = order.kind === "notice_of_hearing" ? "Notice of hearing" : "Order";
  const forHearing = order.hearing_date ? ` (for the hearing on ${longDate(order.hearing_date)})` : "";
  return `${kind}${forHearing}: ${when}`;
}

export function longDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  if (!m) return iso;
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m[2]) - 1];
  return `${Number(m[3])} ${month} ${m[1]}`;
}

export function ukShortDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${m[3]}.${m[2]}.${m[1].slice(2)}` : iso;
}

export function filedScansOf(scans: VirtualScan[], documentId: string): VirtualScan[] {
  return scans.filter((p) => p.document_id === documentId && p.status === "filed");
}

export function alreadyScanned(scans: VirtualScan[], documentId: string, date: string): VirtualScan | undefined {
  return scans.find((p) => p.document_id === documentId && p.date_received === date && p.status === "filed");
}

export function measuredWords(p: Pick<VirtualScan, "pages" | "text_chars">): string {
  const pages = p.pages == null ? "pages unknown" : `${p.pages} ${p.pages === 1 ? "page" : "pages"}`;
  const chars = p.text_chars == null ? "characters unknown" : `${p.text_chars.toLocaleString("en-GB")} characters`;
  return `${pages}, ${chars}`;
}

export function scanBlockedReason(view: Pick<VirtualScannerView, "can_scan" | "refusal">, doc: CommonDocument, date: string, today: string): string {
  if (!view.can_scan) return view.refusal || "Scanning is not possible for this client.";
  if (!doc.has_file) return "No stock copy yet.";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return "Give the date it came in.";
  if (date > today) return "The date it came in cannot be after today.";
  return "";
}

export const WARN_COPIES = 2;
export const MAX_COPIES = 20;

export function parseCopies(text: string): number {
  const n = Math.floor(Number(text));
  return Number.isFinite(n) ? Math.min(MAX_COPIES, Math.max(1, n)) : 1;
}

export function copiesWarning(copies: number): string {
  return copies > WARN_COPIES ? `${copies} copies is more than usual (usually two, one for the firm and one to serve). Check before you press Scan.` : "";
}
