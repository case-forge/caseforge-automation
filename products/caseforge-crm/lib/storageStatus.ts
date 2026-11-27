
import { bytesLabel } from "./systemStatus";

export interface StorageRow {
  key: string;
  group: string;
  name: string;
  bytes: number | null;
  total_bytes: number | null;
  state: "ok" | "unknown";
  note: string;
}

export interface StorageStatusResponse {
  available: boolean;
  note: string;
  generated_at: string;
  age_minutes: number | null;
  stale: boolean;
  target_backup_bytes: number;
  rows: StorageRow[];
}

export async function loadStorageStatus(fetcher: typeof fetch = fetch): Promise<StorageStatusResponse | null> {
  try {
    const res = await fetcher("/api/storage-status", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as StorageStatusResponse;
  } catch {
    return null;
  }
}

export const REFRESH_MS = 60_000;

export interface PieSlice {
  key: string;
  label: string;
  bytes: number;
  fraction: number;

  colour: string;
}

const PIE_COLOURS: Record<string, string> = {
  personal_live: "var(--accent)",
  sharepoint_live: "var(--success)",
  sharepoint_recycle: "var(--muted)",
  personal_recycle: "var(--star-yellow)",
};

export function pieSlices(rows: StorageRow[]): PieSlice[] {
  const order = ["personal_live", "sharepoint_live", "sharepoint_recycle", "personal_recycle"];
  const picked = order
    .map((key) => rows.find((r) => r.key === key))
    .filter((r): r is StorageRow => !!r && r.bytes !== null && r.bytes > 0);
  const total = picked.reduce((n, r) => n + (r.bytes ?? 0), 0);
  if (total <= 0) return [];
  return picked.map((r) => ({
    key: r.key,
    label: r.name,
    bytes: r.bytes ?? 0,
    fraction: (r.bytes ?? 0) / total,
    colour: PIE_COLOURS[r.key] ?? "var(--muted)",
  }));
}

export function sizeLabel(row: Pick<StorageRow, "bytes">): string {
  return row.bytes === null ? "not measured" : bytesLabel(row.bytes);
}

export interface StorageGroup {
  id: string;
  title: string;
  blurb: string;
  rows: StorageRow[];
}

const GROUPS: { id: string; title: string; blurb: string }[] = [
  { id: "backup", title: "Backups", blurb: "The nightly backups kept in OneDrive. Older ones are removed automatically." },
  { id: "company_data_folders", title: "Inside the client files site", blurb: "The top-level folders of the shared client files." },
  { id: "personal_folders", title: "Personal OneDrive folders", blurb: "The firm mailbox account's own storage." },
  { id: "sharepoint_folders", title: "Client files site, top level", blurb: "" },
  { id: "server", title: "Production box", blurb: "The server that runs the firm's software." },
  { id: "azure", title: "Azure storage accounts", blurb: "Small accounts for the audit digests, mail relay and send gate." },
  { id: "github", title: "GitHub", blurb: "The code repository." },
];

export function storageGroups(rows: StorageRow[]): StorageGroup[] {
  return GROUPS.map((g) => ({ ...g, rows: rows.filter((r) => r.group === g.id) })).filter((g) => g.rows.length > 0);
}

export function backupFraction(rows: StorageRow[]): number | null {
  const r = rows.find((x) => x.key === "backup_folder");
  if (!r || r.bytes === null || !r.total_bytes) return null;
  return r.bytes / r.total_bytes;
}

export function updatedLabel(iso: string): string {
  const when = new Date(iso);
  if (!iso || Number.isNaN(when.getTime())) return "Not updated yet";
  return `Updated ${when.toLocaleTimeString("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit" })}`;
}

export function shareLabel(fraction: number): string {
  const pct = fraction * 100;
  return pct > 0 && pct < 1 ? "under 1%" : `${Math.round(pct)}%`;
}
