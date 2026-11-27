
const SAME_SITE = new Set(["same-origin", "none"]);

export interface WriteGuardOptions {

  json?: boolean;
}

export function refuseCrossSiteWrite(request: Request, options: WriteGuardOptions = {}): Response | null {
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite !== null) {
    if (!SAME_SITE.has(fetchSite.toLowerCase())) return Response.json({ error: "cross-site request refused" }, { status: 403 });
  } else {
    const origin = request.headers.get("origin");
    const host = request.headers.get("host");
    if (origin !== null) {
      let originHost = "";
      try {
        originHost = new URL(origin).host;
      } catch {

      }
      if (!host || originHost !== host) return Response.json({ error: "cross-site request refused" }, { status: 403 });
    }
  }
  if (options.json !== false && request.method !== "DELETE") {
    const type = (request.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase();
    if (type !== "application/json") return Response.json({ error: "content type must be application/json" }, { status: 415 });
  }
  return null;
}
