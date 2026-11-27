
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { accessConfigProblem } = await import("@/lib/accessIdentity");
    const problem = accessConfigProblem(process.env);
    if (problem) throw new Error(problem);
  }
  const dsn = process.env.GLITCHTIP_DSN;
  if (!dsn) return;
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const Sentry = await import("@sentry/nextjs");
    const { scrubEvent } = await import("@/lib/sentryScrub");
    Sentry.init({
      dsn,
      tracesSampleRate: 0,
      sendDefaultPii: false,
      beforeSend: scrubEvent,
    });
  }
}

export async function onRequestError(...args: unknown[]): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs" || !process.env.GLITCHTIP_DSN) return;
  const Sentry = await import("@sentry/nextjs");
  (Sentry.captureRequestError as (...a: unknown[]) => void)(...args);
}
