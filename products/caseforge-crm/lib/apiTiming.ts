
interface Timing {
  start: number;
  identityMs: number;
  hubMs: number;
}

const timings = new WeakMap<Headers, Timing>();

export const ROUTE_HEADER = "x-caseforge-api-route";

const now = (): number => performance.now();
const ms = (value: number): number => Math.round(value * 10) / 10;

function timingFor(headers: Headers): Timing {
  let timing = timings.get(headers);
  if (!timing) {
    timing = { start: now(), identityMs: 0, hubMs: 0 };
    timings.set(headers, timing);
  }
  return timing;
}

export function routePattern(pathname: string): string {
  const path = pathname.split("?")[0].slice(0, 200);
  return path
    .split("/")
    .map((segment) => (/\d/.test(segment) ? ":id" : segment))
    .join("/");
}

function routeOf(headers: Headers, request?: Request): string {
  if (request) {
    try {
      return routePattern(new URL(request.url).pathname);
    } catch {

    }
  }
  return routePattern(headers.get(ROUTE_HEADER) ?? "unknown");
}

interface Durations {
  identityMs: number;
  hubMs: number;
  totalMs: number;
}

export function serverTimingValue(timing: Durations): string {
  return `identity;dur=${ms(timing.identityMs)}, hub;dur=${ms(timing.hubMs)}, total;dur=${ms(timing.totalMs)}`;
}

export function logLine(route: string, status: number, timing: Durations): string {
  return `[api-timing] route=${route} status=${status} total_ms=${ms(timing.totalMs)} identity_ms=${ms(timing.identityMs)} hub_ms=${ms(timing.hubMs)}`;
}

export function finishTiming(headers: Headers, response: Response, request?: Request): Response {
  const timing = timingFor(headers);
  const detail = { identityMs: timing.identityMs, hubMs: timing.hubMs, totalMs: now() - timing.start };
  try {
    response.headers.set("Server-Timing", serverTimingValue(detail));
  } catch {

  }
  console.info(logLine(routeOf(headers, request), response.status, detail));
  return response;
}

export async function timeIdentity<T extends { rejection: Response | null }>(headers: Headers, run: () => Promise<T>): Promise<T> {
  const timing = timingFor(headers);
  const began = now();
  const outcome = await run();
  timing.identityMs += now() - began;
  if (outcome.rejection) finishTiming(headers, outcome.rejection);
  return outcome;
}

export async function timeHub(request: Request, run: () => Promise<Response>): Promise<Response> {
  const timing = timingFor(request.headers);
  const began = now();
  const response = await run();
  timing.hubMs += now() - began;
  return finishTiming(request.headers, response, request);
}
