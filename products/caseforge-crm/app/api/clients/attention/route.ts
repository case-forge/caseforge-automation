
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubIdentityHeaders } from "@/lib/hubProxy";
import { stubAttention } from "@/lib/stub";
import type { AttentionResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { remoteUser, rejection } = await resolveIdentityForRoute(request.headers);
  if (rejection) {
    return rejection;
  }

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    return Response.json(stubAttention(), { status: 200 });
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
    const hubRequest = new URL("/client-viewer/attention", hubUrl);
    upstream = await fetch(hubRequest, {
      headers: { Authorization: `Bearer ${token}`, ...(await hubIdentityHeaders(request, remoteUser)) },
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

  let body: AttentionResponse;
  try {
    body = await upstream.json();
  } catch {
    return Response.json({ error: "upstream returned a malformed response" }, { status: 502 });
  }

  return Response.json(body, { status: 200 });
}
