
const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function refuseCrossSiteWrite(request: Request): Response | null {
  if (!WRITE_METHODS.has(request.method.toUpperCase())) return null;
  const site = (request.headers.get("sec-fetch-site") ?? "").trim().toLowerCase();
  if (site === "" || site === "same-origin" || site === "none") return null;
  return Response.json({ error: "Cross-site request refused." }, { status: 403 });
}
