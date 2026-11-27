import type { ErrorEvent, EventHint } from "@sentry/nextjs";

const SENSITIVE_QUERY_PARAMS = ["q"];

function scrubUrl(url: string | undefined): string | undefined {
  if (!url) return url;
  try {
    const parsed = new URL(url, "http://localhost");
    let changed = false;
    for (const key of SENSITIVE_QUERY_PARAMS) {
      if (parsed.searchParams.has(key)) {
        parsed.searchParams.set(key, "[redacted]");
        changed = true;
      }
    }
    if (!changed) return url;

    return url.startsWith("http") ? parsed.toString() : parsed.pathname + parsed.search;
  } catch {
    return url;
  }
}

export function scrubEvent(event: ErrorEvent, _hint: EventHint): ErrorEvent {
  if (event.request?.url) {
    event.request.url = scrubUrl(event.request.url);
  }
  if (event.request?.query_string && typeof event.request.query_string === "string") {
    event.request.query_string = scrubUrl("?" + event.request.query_string)?.replace(/^\?/, "");
  }
  for (const breadcrumb of event.breadcrumbs ?? []) {
    if (breadcrumb.data?.url) {
      breadcrumb.data.url = scrubUrl(String(breadcrumb.data.url));
    }
  }
  return event;
}
