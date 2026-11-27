
export const REPORT_WINDOW_MS = 60_000;
const MAX_ROUTES = 500;

const lastReport = new Map<string, { at: number; suppressed: number }>();
let sentry: Promise<typeof import("@sentry/nextjs")> | undefined;

export function routeName(path: string): string {
  const pathname = String(path).split("?")[0]?.split("#")[0] ?? "";
  return pathname.replace(/\/\d+(?=\/|$)/g, "/:id") || "/";
}

export function reportBackendFailure(path: string, status: number, now: number = Date.now()): void {
  if (status < 500 || !process.env.GLITCHTIP_DSN) return;
  const route = routeName(path);
  const last = lastReport.get(route);
  if (last && now - last.at < REPORT_WINDOW_MS) {
    last.suppressed += 1;
    return;
  }
  if (!last && lastReport.size >= MAX_ROUTES) lastReport.clear();
  lastReport.set(route, { at: now, suppressed: 0 });
  const tags: Record<string, string> = { route, status: String(status) };
  if (last?.suppressed) tags.suppressed = String(last.suppressed);
  sentry ??= import("@sentry/nextjs");
  void sentry
    .then((Sentry) => Sentry.captureMessage(`Backend failure ${status} on ${route}`, { level: "error", tags }))
    .catch(() => undefined);
}
