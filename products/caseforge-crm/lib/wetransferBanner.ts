
import type { StatusBoardItem } from "./matterMilestones";

export type PendingClient = { matterId: string; name: string };

export function pendingWetransfers(items: readonly Pick<StatusBoardItem, "matter_id" | "client_name" | "wetransfer_pending">[], given: ReadonlySet<string> = new Set()): PendingClient[] {
  const seen = new Map<string, PendingClient>();
  for (const i of items) {
    const id = String(i.matter_id ?? "").trim();
    if (i.wetransfer_pending !== true || !id || given.has(id) || seen.has(id)) continue;
    seen.set(id, { matterId: id, name: i.client_name });
  }
  return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name, "en-GB", { sensitivity: "base" }));
}

export function acceptPlan(pending: readonly PendingClient[], given: ReadonlySet<string>, inFlight: ReadonlySet<string>): string[] {
  return [...new Set(pending.map((p) => p.matterId))].filter((id) => !given.has(id) && !inFlight.has(id));
}

export function allTicked(pending: readonly PendingClient[]): Set<string> {
  return new Set(pending.map((p) => p.matterId));
}

export function toggleTick(ticked: ReadonlySet<string>, matterId: string): Set<string> {
  const next = new Set(ticked);
  if (next.has(matterId)) next.delete(matterId);
  else next.add(matterId);
  return next;
}

export function tickedToSend(pending: readonly PendingClient[], ticked: ReadonlySet<string>): PendingClient[] {
  return pending.filter((p) => ticked.has(p.matterId));
}

export function namesInWords(names: readonly string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export async function acceptAll(
  ids: readonly string[],
  post: (matterId: string) => Promise<boolean>,
  given: Set<string>,
  inFlight: Set<string>,
): Promise<{ ok: string[]; failed: string[] }> {
  const ok: string[] = [];
  const failed: string[] = [];
  for (const id of ids) {
    if (given.has(id) || inFlight.has(id)) continue;
    inFlight.add(id);
    let done = false;
    try {
      done = await post(id);
    } catch {
      done = false;
    } finally {
      inFlight.delete(id);
    }
    if (done) {
      given.add(id);
      ok.push(id);
    } else failed.push(id);
  }
  return { ok, failed };
}

export const wetransferGiven = new Set<string>();
export const wetransferInFlight = new Set<string>();

export async function postWetransferGate(matterId: string): Promise<boolean> {
  const res = await fetch("/api/wetransfer-gate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId }),
  });
  return res.ok;
}
