
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubIdentityHeaders } from "@/lib/hubProxy";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const VALID_VERDICTS = new Set(["up", "down"]);
const COMMENT_MAX_CHARS = 2000;

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) {
    return rejection;
  }

  let body: { id?: unknown; verdict?: unknown; comment?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Request body must be JSON" }, { status: 400 });
  }

  const verdict = typeof body.verdict === "string" ? body.verdict : "";
  if (!VALID_VERDICTS.has(verdict)) {
    return Response.json({ error: 'verdict must be "up" or "down"' }, { status: 422 });
  }
  const id = typeof body.id === "string" ? body.id.trim() : "";
  if (!id) {
    return Response.json({ error: "id is required" }, { status: 422 });
  }
  const comment = typeof body.comment === "string" ? body.comment : "";
  if (comment.length > COMMENT_MAX_CHARS) {
    return Response.json({ error: "comment too long" }, { status: 422 });
  }

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    return Response.json({ ok: true }, { status: 200 });
  }

  const hubUrl = process.env.CASEFORGE_HUB_API_URL;
  const token = process.env.CASEFORGE_CHAT_API_TOKEN;
  if (!hubUrl || !token) {
    return Response.json(
      { error: "CASEFORGE_HUB_API_URL/CASEFORGE_CHAT_API_TOKEN not configured on the server" },
      { status: 503 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(new URL("/retrieval/feedback", hubUrl), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(await hubIdentityHeaders(request, remoteUser)),
        "Content-Type": "application/json",
        ...(remoteUser ? { "Remote-User": remoteUser } : {}),
      },
      body: JSON.stringify({ id, verdict, comment }),
      signal: request.signal,
      cache: "no-store",
    });
  } catch {
    return Response.json({ error: "upstream request failed" }, { status: 502 });
  }

  if (!upstream.ok) {
    await upstream.body?.cancel().catch(() => undefined);
    return Response.json({ error: "upstream request failed" }, { status: upstream.status });
  }
  await upstream.body?.cancel().catch(() => undefined);
  return Response.json({ ok: true }, { status: 200 });
}
