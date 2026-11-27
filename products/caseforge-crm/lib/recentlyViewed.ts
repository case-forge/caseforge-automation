
import type { ClientMatch } from "./types";

const STORAGE_KEY = "caseforge-client-viewer:recently-viewed";
const MAX_ENTRIES = 20;

export const RECENTLY_VIEWED_CHANGED = "caseforge-client-viewer:recently-viewed-changed";

function announceChange(): void {
  if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") window.dispatchEvent(new Event(RECENTLY_VIEWED_CHANGED));
}

export interface RecentlyViewedEntry {
  match: ClientMatch;
  viewedAt: string;
}

export function loadRecentlyViewed(): RecentlyViewedEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function recordRecentlyViewed(match: ClientMatch): void {
  if (typeof window === "undefined") return;
  const matterId = match.matter_id != null ? String(match.matter_id) : "";
  if (!matterId) return;
  try {
    const current = loadRecentlyViewed().filter(
      (entry) => String(entry.match.matter_id ?? "") !== matterId,
    );
    const next = [{ match, viewedAt: new Date().toISOString() }, ...current].slice(0, MAX_ENTRIES);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {

  }
  announceChange();
}

export function withoutMatters(entries: RecentlyViewedEntry[], hidden: string[]): RecentlyViewedEntry[] {
  const gone = new Set(hidden.map(String));
  return entries.filter((entry) => !gone.has(String(entry.match.matter_id ?? "")));
}

export function forgetRecentlyViewed(hidden: string[]): void {
  if (typeof window === "undefined" || hidden.length === 0) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(withoutMatters(loadRecentlyViewed(), hidden)));
  } catch {

  }
  announceChange();
}

export function clearRecentlyViewed(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {

  }
  announceChange();
}

export function recentSelection(all: ClientMatch[], clicked: ClientMatch): { matches: ClientMatch[]; index: number } {
  const id = (m: ClientMatch) => (m.matter_id != null ? String(m.matter_id) : "");
  const clickedId = id(clicked);
  const matches = all.filter((m, i) => !id(m) || all.findIndex((o) => id(o) === id(m)) === i);
  const index = clickedId ? matches.findIndex((m) => id(m) === clickedId) : matches.indexOf(clicked);
  if (index >= 0) return { matches, index };
  return { matches: [clicked, ...matches], index: 0 };
}
