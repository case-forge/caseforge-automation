import { refuseCrossSiteWrite } from "@/lib/writeGuard";
import { envelopeUrl, filterEnvelope, MAX_ENVELOPE_BYTES, parseDsn } from "@/lib/glitchtipTunnel";

export async function POST(request: Request): Promise<Response> {

  const crossSite = refuseCrossSiteWrite(request, { json: false });
  if (crossSite) return crossSite;
  const dsn = parseDsn(process.env.GLITCHTIP_DSN);
  if (!dsn) return new Response(null, { status: 204 });
  const length = Number(request.headers.get("content-length") ?? "0");
  if (length > MAX_ENVELOPE_BYTES) return Response.json({ error: "too large" }, { status: 413 });
  const filtered = filterEnvelope(await request.text(), dsn);
  if (!filtered.ok) return Response.json({ error: filtered.reason }, { status: filtered.status });
  try {
    const upstream = await fetch(envelopeUrl(dsn), {
      method: "POST",
      headers: { "Content-Type": "application/x-sentry-envelope" },
      body: filtered.body,
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });
    await upstream.body?.cancel().catch(() => undefined);
    return new Response(null, { status: upstream.ok ? 200 : 502 });
  } catch {
    return new Response(null, { status: 502 });
  }
}
