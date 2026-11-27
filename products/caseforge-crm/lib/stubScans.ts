
import type { ClientScan, ConfirmResult, ScanCandidates } from "./scanResolver";
import type { ScanRow, ScansTable } from "./scansTypes";

const CLIENT_A = { matter_id: "9001", client_name: "Test Person", closed: false };
const CLIENT_B = { matter_id: "9003", client_name: "Stub Person", closed: false };

export function stubCandidates(itemId: string): ScanCandidates {
  const base = { id: itemId, text_read: true, label: "An estimate from the file name and the document's text, not checked. Nothing is filed until you confirm." };
  switch (itemId) {
    case "stub-scan-2":
      return { ...base, name: "NOH for 24.09.26 - TESTPERSON.pdf", kind: "notice_of_hearing", candidates: [
        { ...CLIENT_A, confidence: 90, words: "High", ambiguous: false, reasons: ["Surname Testperson is in the file name", "Client's full name is in the text", "Date 24.09.26 is a hearing date on this matter"] },
      ] };
    case "stub-scan-3":
    case "stub-scan-4":
      return { ...base, name: "Order 04.09.26 - STUBPERSON.pdf", kind: "order", candidates: [
        { ...CLIENT_B, confidence: 20, words: "Low", ambiguous: true, reasons: ["Surname Stubperson is in the file name", "Close to Test Person (within 0 points), so confidence is lowered by 15"] },
        { ...CLIENT_A, confidence: 20, words: "Low", ambiguous: true, reasons: ["Surname Stubperson is in the file name", "Close to Stub Person (within 0 points)"] },
      ] };
    case "stub-scan-6":
      return { ...base, name: "Order 02.10.26 - STUBPERSON.pdf", kind: "order", candidates: [
        { ...CLIENT_B, confidence: 75, words: "Medium", ambiguous: false, reasons: ["Surname Stubperson is in the file name", "Case number ZZ26C00012 in the text matches this matter"] },
      ] };
    default:
      return { ...base, name: "", text_read: false, kind: "other", candidates: [] };
  }
}

export function stubClientScans(matterId: string): ClientScan[] {
  return ["stub-scan-2", "stub-scan-6"]
    .map((id) => ({ ...stubCandidates(id), scan_date: "2026-09-24", date_source: "filename", web_url: "" }))
    .filter((s) => s.candidates.some((c) => c.matter_id === matterId));
}

const filedStub = new Set<string>();

export function stubConfirm(itemId: string, matterId: string, copies: number, kind: string, confirm: boolean): ConfirmResult {
  const already = filedStub.has(itemId);
  filedStub.add(itemId);
  const order = kind === "order";
  const emailed = order && matterId === "9003" && !confirm;
  return {
    message: already ? "Already filed for this client. Nothing was moved." : `Filed in Court-Orders (${copies} ${copies === 1 ? "copy" : "copies"}). Not billed.`,
    already,
    copies,
    case_flow: order
      ? emailed
        ? { ok: false, needs_confirm: true, message: "The court's reply by email is already filed. Record this as well only if it is a different order." }
        : { ok: true, needs_confirm: false, message: "Case flow was told." }
      : null,
  };
}

const FOLDER = "Company_Data/Scanned Docs";

function row(id: string, name: string, part: Partial<ScanRow>): ScanRow {
  return {
    id,
    name,
    scan_date: "",
    date_source: "unknown",
    uploaded_utc: "2026-10-08T09:15:00Z",
    modified_utc: "2026-10-08T09:15:00Z",
    pages: null,
    possible_client: "",
    folder: FOLDER,
    web_url: "",
    size_bytes: 120_000,
    same_contents_as: [],
    ...part,
  };
}

export function stubScans(): ScansTable {
  const rows: ScanRow[] = [

    row("stub-scan-1", "Police disclosure.pdf", { scan_date: "2026-10-08", date_source: "uploaded" }),

    row("stub-scan-2", "NOH for 24.09.26 - TESTPERSON.pdf", { scan_date: "2026-09-24", date_source: "filename", possible_client: "TESTPERSON", pages: 2, uploaded_utc: "2026-10-01T11:00:00Z" }),

    row("stub-scan-3", "Order 04.09.26 - STUBPERSON.pdf", { scan_date: "2026-09-04", date_source: "filename", possible_client: "STUBPERSON", same_contents_as: ["Order 04.09.26 - STUBPERSON (1).pdf"] }),
    row("stub-scan-4", "Order 04.09.26 - STUBPERSON (1).pdf", { scan_date: "2026-09-04", date_source: "filename", same_contents_as: ["Order 04.09.26 - STUBPERSON.pdf"] }),
    row("stub-scan-5", "Bank letter.pdf", { scan_date: "2026-08-30", date_source: "modified", uploaded_utc: "", modified_utc: "2026-08-30T08:00:00Z" }),
  ];
  return {
    folder: FOLDER,
    readable: true,
    total: rows.length,
    folders_not_listed: 1,
    read_utc: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    rows,
  };
}
