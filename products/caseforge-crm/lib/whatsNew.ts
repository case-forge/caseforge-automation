
export type WhatsNewItem = { sha: string; date: string; note: string };
export type WhatsNewData = { head: string; items: WhatsNewItem[] };

export const FIRST_VISIT_LIMIT = 5;

const KEY_PREFIX = "caseforge-client-viewer:whats-new-seen";

export function storageKey(editorName: string): string {
  const name = editorName.trim().toLowerCase();
  return name ? `${KEY_PREFIX}:${name}` : KEY_PREFIX;
}

export function loadSeen(editorName: string): string {
  try {
    return window.localStorage.getItem(storageKey(editorName)) ?? "";
  } catch {
    return "";
  }
}

export function storeSeen(editorName: string, sha: string): void {
  try {
    window.localStorage.setItem(storageKey(editorName), sha);
  } catch {

  }
}

export function unseen(items: WhatsNewItem[], seenSha: string): WhatsNewItem[] {
  const at = seenSha ? items.findIndex((item) => item.sha === seenSha) : -1;
  return at < 0 ? items.slice(0, FIRST_VISIT_LIMIT) : items.slice(0, at);
}

export function noteDate(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : when.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export async function fetchWhatsNew(): Promise<WhatsNewData> {
  const res = await fetch("/api/whats-new", { cache: "no-store" });
  if (!res.ok) return { head: "", items: [] };
  const body = (await res.json().catch(() => ({}))) as Partial<WhatsNewData>;
  return { head: String(body.head ?? ""), items: Array.isArray(body.items) ? body.items : [] };
}
