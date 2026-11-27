
import type { CommonDocument, LastOrder, ScanOrderResult, VirtualScan, VirtualScannerView, VirtualScanResult } from "./virtualScannerTypes";
import { DEMO_FIRM } from "./stubFirm";

const SURNAME: Record<string, string> = { "9001": "TESTPERSON", "9002": "STUBPERSON", "9003": "STUBPERSON" };
const NMO_CAO = "9002";

let scanSeq = 0;
const EMPTY = "9003";
const MEASURED: Record<string, { pages: number; text_chars: number | null }> = {
  "stub-fjypb": { pages: 2, text_chars: 3725 },
  "stub-pn": { pages: 4, text_chars: 9428 },
};

const STOCK: CommonDocument[] = [
  { document_id: "stub-pn", title: "Family Court Privacy Notice", file_name: "Family Court Privacy Notice.pdf", has_file: true, also_named: ["PN_Family_1020.pdf"], web_url: "", added_by: "" },
  { document_id: "stub-fjypb", title: "FJYPB Top Tips for Parents", file_name: "FJYPB Top Tips for Parents.pdf", has_file: true, also_named: [], web_url: "", added_by: "" },
];
const titles: CommonDocument[] = [
  { document_id: "t:stub-private-law", title: "Private law letter", file_name: "", has_file: false, also_named: [], web_url: "", added_by: "Stub admin" },
];
const scans = new Map<string, VirtualScan[]>();
const taken = new Map<string, Set<string>>();
const bills = new Map<string, string>();

function today(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Europe/London" });
}

function ukDate(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(2, 4)}`;
}

function takenIn(matterId: string): Set<string> {
  let s = taken.get(matterId);
  if (!s) {
    s = new Set(matterId === "9001" ? [`Family Court Privacy Notice ${ukDate(today())} - TESTPERSON.pdf`] : []);
    taken.set(matterId, s);
  }
  return s;
}

function catalogue(matterId: string): CommonDocument[] {
  if (matterId === EMPTY) return [];
  return [...STOCK, ...titles].sort((a, b) => a.title.localeCompare(b.title));
}

const AUG_ORDER: LastOrder = { name: "Order 04.08.26 - TESTPERSON.pdf", kind: "order", date: "2026-08-04", date_source: "filename", hearing_date: "", folder: "Court-Orders-TESTPERSON", web_url: "" };
const NMO_NOTICE: LastOrder = { name: "NOH for 10.09.26 - STUBPERSON.pdf", kind: "notice_of_hearing", date: "2026-08-20", date_source: "uploaded", hearing_date: "2026-09-10", folder: "Court-Orders-STUBPERSON", web_url: "" };
const OCT_ORDER: LastOrder = { name: "Order 01.10.26 - STUBPERSON.pdf", kind: "order", date: "2026-10-01", date_source: "filename", hearing_date: "", folder: "Court-Orders-STUBPERSON", web_url: "" };

const recordedOrders = new Set<string>();

function withRecorded(matterId: string, orders: LastOrder[]): LastOrder[] {
  return orders.map((o) => ({ ...o, recorded: recordedOrders.has(`${matterId}:${o.name}`) }));
}

function stubHints(matterId: string): Pick<VirtualScannerView, "last_order" | "orders" | "email_reply_filed" | "orders_expected" | "scan_hints" | "hint_errors"> {
  if (matterId === "9001") {
    return {
      last_order: AUG_ORDER,
      orders: withRecorded(matterId, [AUG_ORDER]),
      email_reply_filed: false,
      orders_expected: [{ hearing_date: "2026-09-10", line: "Hearing 10 Sep 2026: no order filed yet" }],
      scan_hints: [{
        name: "Order 10.09.26 - TESTPERSON.pdf",
        web_url: "",
        hearing_date: "2026-09-10",
        surname_matches: true,
        line: "Probably this client, likely the order from the hearing on 10 Sep 2026",
        label: "A guess from the file name's date and surname, not checked. Nothing is filed from it.",
      }],
      hint_errors: [],
    };
  }
  if (matterId === "9002") {
    return { last_order: NMO_NOTICE, orders: withRecorded(matterId, [NMO_NOTICE]), email_reply_filed: false, orders_expected: [], scan_hints: [], hint_errors: [] };
  }
  if (matterId === "9003") {
    return { last_order: OCT_ORDER, orders: withRecorded(matterId, [OCT_ORDER]), email_reply_filed: true, orders_expected: [], scan_hints: [], hint_errors: [] };
  }
  return { last_order: null, orders: [], email_reply_filed: false, orders_expected: [], scan_hints: [], hint_errors: [] };
}

export function stubScanOrder(matterId: string, folder: string, name: string, confirm: boolean): ScanOrderResult {
  const order = stubHints(matterId).orders.find((o) => o.folder === folder && o.name === name);
  if (!order) return { ok: false, needs_confirm: false, message: "That file is not in the client's Court-Orders folder. File the scan there first." };
  if (order.recorded) return { ok: false, needs_confirm: false, message: `${name} is already recorded as the court's order. Nothing was changed.` };
  if (stubHints(matterId).email_reply_filed && !confirm) {
    return { ok: false, needs_confirm: true, message: `The court's reply by email is already filed (2026-09-30). Record ${name} as well only if it is a different order.` };
  }
  recordedOrders.add(`${matterId}:${name}`);
  return { ok: true, needs_confirm: false, message: `Scanned order recorded: ${name} in ${folder}. It counts as the court's reply; the steps after it read it from there. Nothing was sent.` };
}

export function stubVirtualScanner(matterId: string): VirtualScannerView {
  const refusal = "";
  return {
    matter_id: matterId,
    today: today(),
    can_scan: !refusal,
    refusal,
    court_orders_folder: refusal ? "" : `Court-Orders-${SURNAME[matterId] ?? "STUB"}`,
    folder: DEMO_FIRM.folders.common_scans,
    documents: catalogue(matterId),
    other_files: matterId === EMPTY ? [] : ["Our Child's Plan word version.docx"],
    folder_error: "",
    scans: [...(scans.get(matterId) ?? [])].sort((a, b) => b.pressed_utc.localeCompare(a.pressed_utc)),
    ...stubHints(matterId),
  };
}

export function stubScan(matterId: string, documentId: string, date: string, by: string, copies = 1): VirtualScanResult | { error: string } {
  const view = stubVirtualScanner(matterId);
  if (!view.can_scan) return { error: view.refusal };
  const doc = view.documents.find((d) => d.document_id === documentId);
  if (!doc) return { error: "That document is not in the Common Scanned Docs folder any more." };
  if (!doc.has_file) return { error: "There is no stock copy of this document yet, so there is nothing to scan." };
  if (date > today()) return { error: "The date it came in cannot be after today." };
  const list = scans.get(matterId) ?? [];
  const earlier = list.find((p) => p.document_id === documentId && p.date_received === date && p.status === "filed");
  if (earlier) return { ...earlier, already: true, message: `Already scanned for ${ukDate(date)}: ${earlier.file_name}. Nothing was filed or billed again.` };
  const surname = SURNAME[matterId] ?? "STUB";
  const names = takenIn(matterId);
  let n = 1;
  const nameFor = (k: number) => `${doc.title} ${ukDate(date)}${k > 1 ? ` (${k})` : ""} - ${surname}.pdf`;
  while (names.has(nameFor(n))) n += 1;
  const name = nameFor(n);
  names.add(name);
  const key = `${matterId}:${documentId}:${date}`;
  const reused = bills.has(key);
  const billingId = bills.get(key) ?? `stub-bill-${bills.size + 1}`;
  bills.set(key, billingId);
  const sizes = MEASURED[documentId] ?? { pages: 1, text_chars: null };
  const note = reused
    ? "Put the earlier charge for this document and date back on the bill."
    : `Rate TBC: the character limit is not set yet. ${sizes.pages} page(s), ${sizes.text_chars?.toLocaleString("en-GB") ?? "unknown"} characters.`;
  const row: VirtualScan = {
    scan_id: `stub-scan-${matterId}-${++scanSeq}`,
    matter_id: matterId,
    document_id: documentId,
    document_title: doc.title,
    date_received: date,
    pressed_by: by,
    pressed_utc: new Date().toISOString(),
    filed_path: `Stub/${view.court_orders_folder}/${name}`,
    filed_url: "",
    file_name: name,
    billing_item_id: billingId,
    billing_note: note,
    pages: sizes.pages,
    text_chars: sizes.text_chars,
    status: "filed",
    undone_by: "",
    undone_utc: "",
    moved_to: "",
    copies,
  };
  scans.set(matterId, [...list, row]);
  return { ...row, already: false, message: `Filed ${name} in ${view.court_orders_folder}. ${note}` };
}

export function stubUndo(scanId: string, by: string): (VirtualScan & { message: string }) | { error: string } {
  for (const [matterId, list] of scans) {
    const row = list.find((p) => p.scan_id === scanId);
    if (!row) continue;
    if (row.status === "undone") return { ...row, message: "Already undone." };
    if (matterId === NMO_CAO) return { error: `This client's folder is now in ${DEMO_FIRM.folders.read_only_book}, which takes no move. Nothing was moved: undo it by hand.` };
    takenIn(matterId).delete(row.file_name);
    const message = `Moved ${row.file_name} into 000 Removed. The charge is off the bill (the Billing tab's Removed list can put it back).`;
    Object.assign(row, { status: "undone", undone_by: by, undone_utc: new Date().toISOString(), moved_to: `Stub/000 Removed/${row.file_name}`, billing_note: message });
    return { ...row, message };
  }
  return { error: "No such scan." };
}

export function stubAddTitle(title: string, by: string): { title_id: string; title: string } | { error: string } {
  const clean = title.trim();
  if (!clean) return { error: "Type the document's title." };
  if ([...STOCK, ...titles].some((d) => d.title.toLowerCase() === clean.toLowerCase())) return { error: `'${clean}' is already on the list.` };
  const id = `stub-title-${titles.length + 1}`;
  titles.push({ document_id: `t:${id}`, title: clean, file_name: "", has_file: false, also_named: [], web_url: "", added_by: by });
  return { title_id: id, title: clean };
}

export function stubRemoveTitle(titleId: string): { removed: boolean } {
  const at = titles.findIndex((d) => d.document_id === titleId || d.document_id === `t:${titleId}`);
  if (at >= 0) titles.splice(at, 1);
  return { removed: at >= 0 };
}

export function stubPdf(): Uint8Array {
  const text = "BT /F1 18 Tf 72 760 Td (Stub stock copy: the hub serves the real PDF) Tj ET";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${text.length} >>\nstream\n${text}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((o, i) => {
    offsets.push(body.length);
    body += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = body.length;
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("")}`;
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return new TextEncoder().encode(body);
}

export function stubPreviewSvg(): string {
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1273" viewBox="0 0 900 1273">' +
    '<rect width="900" height="1273" fill="#ffffff"/>' +
    '<text x="90" y="160" font-family="Helvetica, Arial, sans-serif" font-size="34" fill="#1f2933">Stub stock copy, page 1</text>' +
    '<text x="90" y="215" font-family="Helvetica, Arial, sans-serif" font-size="24" fill="#52606d">The hub serves a picture of the real first page.</text>' +
    "</svg>"
  );
}
