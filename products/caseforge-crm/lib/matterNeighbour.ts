
import type { ClientMatch } from "./types";

export type NeighbourDir = "prev" | "next";

export const ARROW_LABELS: Record<NeighbourDir, { title: string; end: string }> = {
  prev: { title: "Previous number", end: "No lower number" },
  next: { title: "Next number", end: "No higher number" },
};

export function neighbourIn(ids: readonly string[], current: string, dir: NeighbourDir): string | null {
  const n = Number(current);
  const numbers = ids.filter((id) => /^\d+$/.test(id)).map(Number);
  const side = numbers.filter((id) => (dir === "prev" ? id < n : id > n));
  if (!side.length) return null;
  return String(dir === "prev" ? Math.max(...side) : Math.min(...side));
}

export function keyDirection(event: { key: string; altKey?: boolean; ctrlKey?: boolean; metaKey?: boolean; target?: EventTarget | null }): NeighbourDir | null {
  if (event.altKey || event.ctrlKey || event.metaKey) return null;
  if (event.key !== "[" && event.key !== "]") return null;
  if (isTypingTarget(event.target ?? null)) return null;
  return event.key === "[" ? "prev" : "next";
}

function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as { tagName?: string; isContentEditable?: boolean } | null;
  if (!el || typeof el.tagName !== "string") return false;
  return el.isContentEditable === true || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName.toUpperCase());
}

export type NeighbourResult = { kind: "found"; match: ClientMatch } | { kind: "end" } | { kind: "error"; message: string };

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export async function fetchNeighbour(matterId: string, dir: NeighbourDir, fetcher: FetchLike = fetch): Promise<NeighbourResult> {
  try {
    const res = await fetcher(`/api/clients/matter-neighbour?matter_id=${encodeURIComponent(matterId)}&dir=${dir}`, { cache: "no-store" });
    const body = (await res.json().catch(() => ({}))) as { matter_id?: string | null; error?: string };
    if (!res.ok) return { kind: "error", message: body.error || "Could not find the next number" };
    const next = typeof body.matter_id === "string" && body.matter_id ? body.matter_id : null;
    if (!next) return { kind: "end" };
    const rowsRes = await fetcher(`/api/clients/person-matters?matter_id=${encodeURIComponent(next)}`, { cache: "no-store" });
    const rows = (await rowsRes.json().catch(() => ({}))) as { matters?: ClientMatch[] };
    const match = rowsRes.ok ? rows.matters?.find((row) => String(row.matter_id) === next) : undefined;
    return match ? { kind: "found", match } : { kind: "error", message: `Could not open matter ${next}` };
  } catch {
    return { kind: "error", message: "Could not find the next number" };
  }
}

export async function fetchMatterByNumber(number: string, fetcher: FetchLike = fetch): Promise<NeighbourResult> {
  const id = number.trim();
  if (!/^\d+$/.test(id)) return { kind: "error", message: "Type a client number" };
  try {
    const res = await fetcher(`/api/clients/person-matters?matter_id=${encodeURIComponent(id)}`, { cache: "no-store" });
    const body = (await res.json().catch(() => ({}))) as { matters?: ClientMatch[] };
    const match = res.ok ? body.matters?.find((row) => String(row.matter_id) === id) : undefined;
    return match ? { kind: "found", match } : { kind: "error", message: `No client numbered ${id}` };
  } catch {
    return { kind: "error", message: "Could not look that number up" };
  }
}
