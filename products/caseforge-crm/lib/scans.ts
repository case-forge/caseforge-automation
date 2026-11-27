
import type { ScanDateSource, ScanRow, ScansTable } from "./scansTypes";

export type { ScanDateSource, ScanRow, ScansTable } from "./scansTypes";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function scanDateLabel(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return "No date";
  const month = MONTHS[Number(m[2]) - 1];
  return month ? `${Number(m[3])} ${month} ${m[1]}` : "No date";
}

export function dateSourceLabel(source: ScanDateSource): string {
  switch (source) {
    case "filename":
      return "From the file name";
    case "uploaded":
      return "Upload date (no date in the file name)";
    case "modified":
      return "Last changed date (no date in the file name)";
    default:
      return "No date in the file name or on the file";
  }
}

export function clientGuessLabel(surname: string): string {
  const name = surname.trim();
  return name ? `Possibly ${name}` : "No guess";
}

export function pagesLabel(pages: number | null): string {
  return typeof pages === "number" && pages > 0 ? String(pages) : "Not known";
}

export function sameContentsNote(names: readonly string[]): string {
  if (names.length === 0) return "";
  return `Possible duplicate: same contents as ${names.join(", ")}. Both are listed.`;
}

export function sortScans(rows: readonly ScanRow[]): ScanRow[] {
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      if (a.row.scan_date !== b.row.scan_date) return a.row.scan_date < b.row.scan_date ? 1 : -1;
      if (a.row.uploaded_utc !== b.row.uploaded_utc) return a.row.uploaded_utc < b.row.uploaded_utc ? 1 : -1;
      return a.index - b.index;
    })
    .map(({ row }) => row);
}

export function scansSummary(table: ScansTable): string {
  if (!table.readable) return "Folder not read";
  const scans = `${table.total} ${table.total === 1 ? "scan" : "scans"} waiting`;
  if (table.folders_not_listed <= 0) return scans;
  return `${scans}, ${table.folders_not_listed} ${table.folders_not_listed === 1 ? "sub-folder" : "sub-folders"} not opened`;
}

export function readAtLabel(readUtc: string): string {
  const when = new Date(readUtc);
  if (!readUtc || Number.isNaN(when.getTime())) return "";
  return when.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });
}

function isTable(body: unknown): body is ScansTable {
  const t = body as ScansTable | null;
  return !!t && typeof t === "object" && Array.isArray(t.rows) && typeof t.readable === "boolean";
}

export async function fetchScans(): Promise<ScansTable> {
  let res: Response;
  try {
    res = await fetch("/api/scans", { cache: "no-store" });
  } catch {
    throw new Error("Could not load the scans. Check the connection and press Refresh.");
  }

  if (!(res.headers.get("content-type") ?? "").includes("application/json")) {
    throw new Error("Your session has expired. Please reload the page.");
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok || !isTable(body)) throw new Error("Could not load the scans. Press Refresh to try again.");
  return { ...body, rows: sortScans(body.rows) };
}
