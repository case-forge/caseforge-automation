
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubIdentityHeaders } from "@/lib/hubProxy";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const QUESTION_MAX_CHARS = 4000;
const ANSWER_MAX_CHARS = 20000;

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) {
    return rejection;
  }

  let body: { question?: unknown; answer?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Request body must be JSON" }, { status: 400 });
  }
  const question = typeof body.question === "string" ? body.question.trim() : "";
  if (!question || question.length > QUESTION_MAX_CHARS) {
    return Response.json({ error: "question is required" }, { status: 422 });
  }
  const answer = typeof body.answer === "string" ? body.answer.slice(0, ANSWER_MAX_CHARS) : "";

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    return Response.json({ title: question.split(/\s+/).slice(0, 5).join(" ") }, { status: 200 });
  }

  const hubUrl = process.env.CASEFORGE_HUB_API_URL;
  const token = process.env.CASEFORGE_CHAT_API_TOKEN;
  if (!hubUrl || !token) {
    return Response.json({ title: null }, { status: 200 });
  }

  try {
    const upstream = await fetch(new URL("/client-viewer/vergil-title", hubUrl), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(await hubIdentityHeaders(request, remoteUser)),
        "Content-Type": "application/json",
        ...(remoteUser ? { "Remote-User": remoteUser } : {}),
      },
      body: JSON.stringify({ question, answer }),
      signal: request.signal,
      cache: "no-store",
    });
    if (!upstream.ok) {
      await upstream.body?.cancel().catch(() => undefined);
      return Response.json({ title: null }, { status: 200 });
    }
    const data = (await upstream.json()) as { title?: unknown };
    return Response.json({ title: typeof data.title === "string" ? data.title : null }, { status: 200 });
  } catch {
    return Response.json({ title: null }, { status: 200 });
  }
}
