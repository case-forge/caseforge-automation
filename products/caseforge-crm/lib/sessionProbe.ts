
export const PROBE_INIT = { redirect: "manual" } as const;

export type SessionProbe = "ok" | "access-expired" | "unreachable";

export interface ProbeFacts {

  type?: string;
  status?: number;
  contentType?: string;

  bodyHint?: string;

  threw?: boolean;
}

export function looksLikeAccessHtml(body: string | undefined): boolean {
  if (!body) return false;
  return /cloudflareaccess\.com|cf-access|Cloudflare Access/i.test(body);
}

export function classifySessionProbe(facts: ProbeFacts): SessionProbe {
  if (facts.threw) return "unreachable";
  if (facts.type === "opaqueredirect") return "access-expired";
  const status = facts.status ?? 0;
  if (status >= 500) return "unreachable";
  if ((facts.contentType ?? "").includes("application/json")) return "ok";

  if ((status === 200 || status === 401 || status === 403) && looksLikeAccessHtml(facts.bodyHint)) return "access-expired";
  return "unreachable";
}

export async function classifyResponse(res: Response): Promise<SessionProbe> {
  const contentType = res.headers.get("content-type") ?? "";
  let bodyHint: string | undefined;
  if (res.type !== "opaqueredirect" && !contentType.includes("application/json")) {
    try {
      bodyHint = (await res.clone().text()).slice(0, 4000);
    } catch {
      bodyHint = undefined;
    }
  }
  return classifySessionProbe({ type: res.type, status: res.status, contentType, bodyHint });
}

export const SHOW_AFTER_FAILURES = 2;
export const GIVE_UP_AFTER_MS = 5 * 60_000;

export type ReconnectNote = "none" | "reconnecting" | "still-unreachable";

export interface ReconnectState {
  failures: number;

  since: number | null;
  note: ReconnectNote;
}

export const RECONNECT_START: ReconnectState = { failures: 0, since: null, note: "none" };

export type ReconnectEvent = { type: "success" } | { type: "failure"; now: number };

export function reconnectReducer(state: ReconnectState, event: ReconnectEvent): ReconnectState {
  if (event.type === "success") return RECONNECT_START;
  const failures = state.failures + 1;
  const since = state.since ?? event.now;
  let note: ReconnectNote = "none";
  if (failures >= SHOW_AFTER_FAILURES) note = event.now - since >= GIVE_UP_AFTER_MS ? "still-unreachable" : "reconnecting";
  return { failures, since, note };
}

export const RECONNECTING_TEXT = "Reconnecting...";
export const STILL_UNREACHABLE_TEXT = "Still cannot reach the server. Check your connection, then reload.";

export function retryDelayMs(failures: number): number {
  return Math.min(15_000, 5_000 * Math.max(1, failures));
}
