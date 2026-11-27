
export const SUMMARY_PARTS = ["flags", "person_matters", "sos_status", "bill_of_costs"] as const;
export type SummaryPart = (typeof SUMMARY_PARTS)[number];

type Fetch = (url: string) => Promise<Response>;

interface Waiting {
  part: SummaryPart;
  url: string;
  resolve: (reply: Promise<Response>) => void;
}

const waiting = new Map<string, Waiting[]>();

export function summaryUrl(matterId: string, parts: readonly SummaryPart[]): string {
  return `/api/clients/matter-summary?matter_id=${encodeURIComponent(matterId)}&parts=${parts.join(",")}`;
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

export function partReply(body: unknown, part: SummaryPart): Response | null {
  if (!body || typeof body !== "object") return null;
  const record = body as Record<string, unknown>;
  const value = record[part];
  if (value !== null && value !== undefined) return json(value, 200);
  if (Array.isArray(record.errors) && record.errors.includes(part)) return json({ error: "upstream request failed" }, 502);
  return null;
}

async function flush(matterId: string, fetchImpl: Fetch): Promise<void> {
  const queue = waiting.get(matterId) ?? [];
  waiting.delete(matterId);
  const parts = [...new Set(queue.map((w) => w.part))];
  if (parts.length < 2) {
    for (const w of queue) w.resolve(fetchImpl(w.url));
    return;
  }
  let body: unknown = null;
  try {
    const reply = await fetchImpl(summaryUrl(matterId, parts));
    if (reply.ok) body = await reply.json();
  } catch {
    body = null;
  }
  for (const w of queue) {
    const reply = partReply(body, w.part);
    w.resolve(reply ? Promise.resolve(reply) : fetchImpl(w.url));
  }
}

export function summaryFetcher(matterId: string, part: SummaryPart, fetchImpl: Fetch = (u) => fetch(u)): Fetch {
  return (url) =>
    new Promise<Response>((resolve) => {
      let queue = waiting.get(matterId);
      if (!queue) {
        queue = [];
        waiting.set(matterId, queue);

        setTimeout(() => void flush(matterId, fetchImpl), 0);
      }
      queue.push({ part, url, resolve });
    });
}
