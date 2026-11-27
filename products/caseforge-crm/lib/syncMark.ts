
export interface BoardSync {
  level: number;
  symbol: string;
  meaning: string;
  start_at: string;
  start_number: number | null;
  attention: boolean;
  scanned_utc: string;

  regressed?: string[];

  stale?: boolean;
}

export interface SyncMark {

  text: string;

  level: number | null;
  title: string;
  attention: boolean;
  scanned: boolean;

  regressed: string[];

  stale: boolean;
}

export const STALE_TEXT = "scan out of date";

export function syncMark(sync: BoardSync | null | undefined): SyncMark | null {
  if (sync === undefined) return null;
  if (sync === null) return { text: "not scanned", level: null, title: "The sync scan has not looked at this matter yet", attention: false, scanned: false, regressed: [], stale: false };
  const from = sync.start_number !== null && sync.start_number !== undefined ? `from step ${sync.start_number}` : "";
  const regressed = Array.isArray(sync.regressed) ? sync.regressed.filter((r): r is string => typeof r === "string" && r.trim() !== "") : [];
  return { text: from, level: typeof sync.level === "number" ? sync.level : 0, title: sync.meaning, attention: !!sync.attention, scanned: true, regressed, stale: sync.stale === true };
}
