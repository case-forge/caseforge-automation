import type { ClientMatch, FrequentCallersResponse, ConcludedMattersResponse } from "./types";

export async function loadFlagList(flags: string): Promise<ClientMatch[]> {
  try {
    const res = await fetch(`/api/clients/flagged-matters?flags=${encodeURIComponent(flags)}`);
    const body = res.ok ? await res.json() : { results: [] };
    const reasons: Record<string, string> = body.flag_reasons_by_matter ?? {};
    const results: ClientMatch[] = body.results ?? [];

    return results.map((match) => {
      const reason = reasons[String(match.matter_id)];
      return reason ? { ...match, extra: { ...match.extra, flag_reason: reason } } : match;
    });
  } catch {
    return [];
  }
}

export async function loadFrequentCallers(): Promise<ClientMatch[]> {
  try {
    const res = await fetch("/api/clients/frequent-callers");
    const body: Partial<FrequentCallersResponse> = res.ok ? await res.json() : {};
    return body.results ?? [];
  } catch {
    return [];
  }
}

export const CONCLUDED_PAGE = 50;

export async function loadConcludedPage(offset: number): Promise<{ results: ClientMatch[]; total: number; nextOffset: number | null }> {
  const res = await fetch(`/api/clients/concluded-matters?limit=${CONCLUDED_PAGE}&offset=${offset}`);
  if (!res.ok) throw new Error("Could not load the concluded clients.");
  const body = (await res.json()) as ConcludedMattersResponse;
  return { results: body.results ?? [], total: body.total ?? 0, nextOffset: body.next_offset ?? null };
}

export function appendUnique(current: ClientMatch[], page: ClientMatch[]): ClientMatch[] {
  const seen = new Set(current.map((m) => String(m.matter_id)));
  return [...current, ...page.filter((m) => !seen.has(String(m.matter_id)))];
}
