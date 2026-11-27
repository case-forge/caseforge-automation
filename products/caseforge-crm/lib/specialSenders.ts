
import { useEffect, useState } from "react";
import { parseSpecialSenders } from "./specialSenderRules";
import type { SenderMark, SpecialSender } from "./specialSenderRules";

export * from "./specialSenderRules";

const URL = "/api/settings/special-senders";
const LOGO_URL = "/api/settings/special-sender-logo";

async function failure(res: Response, fallback: string): Promise<Error> {
  const body = (await res.json().catch(() => ({}))) as { error?: unknown; detail?: unknown };
  return new Error(typeof body.error === "string" ? body.error : typeof body.detail === "string" ? body.detail : fallback);
}

export async function fetchSpecialSenders(): Promise<SpecialSender[]> {
  const res = await fetch(URL, { cache: "no-store" });
  if (!res.ok) throw await failure(res, "The special senders could not be loaded.");
  return parseSpecialSenders(await res.json());
}

export type SpecialSenderEdit = { id?: string; name: string; domains: string[]; new_clients: boolean; mark: SenderMark | null };

export async function saveSpecialSenders(senders: SpecialSenderEdit[]): Promise<SpecialSender[]> {
  const res = await fetch(URL, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ senders }) });
  if (!res.ok) throw await failure(res, "The special senders were not saved.");
  const saved = parseSpecialSenders(await res.json());
  cache = saved;
  listeners.forEach((listener) => listener(saved));
  return saved;
}

export async function uploadSenderLogo(id: string, file: File): Promise<void> {
  const res = await fetch(`${LOGO_URL}?id=${encodeURIComponent(id)}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
  if (!res.ok) throw await failure(res, "The logo was not saved.");
}

export async function removeSenderLogo(id: string): Promise<void> {
  const res = await fetch(`${LOGO_URL}?id=${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!res.ok) throw await failure(res, "The logo was not removed.");
}

let cache: SpecialSender[] | null = null;
let inFlight: Promise<SpecialSender[]> | null = null;
const listeners = new Set<(senders: SpecialSender[]) => void>();

export async function refreshSpecialSenders(): Promise<SpecialSender[]> {
  const list = await fetchSpecialSenders();
  cache = list;
  listeners.forEach((listener) => listener(list));
  return list;
}

export function resetSpecialSendersCache(): void {
  cache = null;
  inFlight = null;
}

export function useSpecialSenders(): SpecialSender[] {
  const [senders, setSenders] = useState<SpecialSender[]>(cache ?? []);
  useEffect(() => {
    listeners.add(setSenders);
    if (cache) {
      setSenders(cache);
    } else {
      inFlight ??= fetchSpecialSenders().then(
        (list) => {
          cache = list;
          return list;
        },
        () => {
          inFlight = null;
          return [];
        },
      );
      void inFlight.then((list) => setSenders(list));
    }
    return () => {
      listeners.delete(setSenders);
    };
  }, []);
  return senders;
}
