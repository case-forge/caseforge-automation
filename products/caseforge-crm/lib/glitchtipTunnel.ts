import type { ErrorEvent } from "@sentry/nextjs";
import { scrubEvent } from "@/lib/sentryScrub";

export const MAX_ENVELOPE_BYTES = 200 * 1024;

export interface Dsn {
  origin: string;
  projectId: string;
  key: string;
}

export function parseDsn(dsn: string | undefined | null): Dsn | null {
  if (!dsn) return null;
  try {
    const url = new URL(dsn);
    const projectId = url.pathname.replace(/^\/+|\/+$/g, "").split("/").pop() ?? "";
    return url.username && /^\d+$/.test(projectId) ? { origin: url.origin, projectId, key: url.username } : null;
  } catch {
    return null;
  }
}

export function envelopeUrl(dsn: Dsn): string {
  return `${dsn.origin}/api/${dsn.projectId}/envelope/?sentry_key=${encodeURIComponent(dsn.key)}`;
}

export type Filtered = { ok: true; body: string } | { ok: false; status: number; reason: string };

export function filterEnvelope(raw: string, allowed: Dsn): Filtered {
  if (raw.length > MAX_ENVELOPE_BYTES) return { ok: false, status: 413, reason: "too large" };
  const lines = raw.split("\n");
  let header: { dsn?: unknown };
  try {
    header = JSON.parse(lines[0] ?? "");
  } catch {
    return { ok: false, status: 400, reason: "not an envelope" };
  }
  const named = parseDsn(typeof header.dsn === "string" ? header.dsn : "");
  if (!named || named.projectId !== allowed.projectId || named.key !== allowed.key) {
    return { ok: false, status: 403, reason: "not this project" };
  }
  const out = [lines[0]];
  let items = 0;
  for (let i = 1; i < lines.length; i += 2) {
    const itemHeader = lines[i];
    if (!itemHeader) continue;
    let parsed: { type?: unknown; length?: unknown };
    try {
      parsed = JSON.parse(itemHeader);
    } catch {
      return { ok: false, status: 400, reason: "bad item" };
    }
    if (parsed.type !== "event") return { ok: false, status: 400, reason: "only error events are forwarded" };
    let event: ErrorEvent;
    try {
      event = JSON.parse(lines[i + 1] ?? "");
    } catch {
      return { ok: false, status: 400, reason: "bad event" };
    }

    out.push(JSON.stringify({ ...parsed, length: undefined }), JSON.stringify(scrubEvent(event, {})));
    items += 1;
  }
  if (items === 0) return { ok: false, status: 400, reason: "no events" };
  return { ok: true, body: out.join("\n") + "\n" };
}
