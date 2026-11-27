
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubIdentityHeaders } from "@/lib/hubProxy";
import { stubVergilAskStream } from "@/lib/stub";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const MAX_QUESTION_CHARS = 20000;

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { remoteUser, rejection } = await resolveIdentityForRoute(request.headers);
  if (rejection) {
    return rejection;
  }

  let payload: { question?: string; session_id?: string; matter_id?: string };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const question = (payload.question ?? "").trim();
  if (!question) {
    return Response.json({ error: "question is required" }, { status: 400 });
  }
  if (question.length > MAX_QUESTION_CHARS) {
    return Response.json({ error: "Question is too long (max 20,000 characters). Paste a shorter extract." }, { status: 400 });
  }
  const matterId = (payload.matter_id ?? "").trim();
  if (!matterId) {
    return Response.json({ error: "matter_id is required" }, { status: 400 });
  }

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    return new Response(stubVergilAskStream(question), {
      status: 200,
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
    });
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
    upstream = await fetch(new URL("/vergil/ask", hubUrl), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        ...(await hubIdentityHeaders(request, remoteUser)),
      },
      body: JSON.stringify({
        question,
        session_id: payload.session_id ?? "",
        matter_id: matterId,
      }),
      signal: request.signal,
      cache: "no-store",
    });
  } catch {
    return Response.json({ error: "upstream request failed" }, { status: 502 });
  }

  if (!upstream.ok || !upstream.body) {
    await upstream.body?.cancel().catch(() => undefined);
    return Response.json({ error: "upstream request failed" }, { status: upstream.status || 502 });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
}
