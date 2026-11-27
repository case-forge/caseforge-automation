
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubIdentityHeaders } from "@/lib/hubProxy";
import { stubFieldReviewQueue } from "@/lib/stub";
import type { FieldReviewQueueResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { remoteUser, rejection } = await resolveIdentityForRoute(request.headers);
  if (rejection) {
    return rejection;
  }

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    return Response.json(stubFieldReviewQueue() satisfies FieldReviewQueueResponse, { status: 200 });
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
    upstream = await fetch(new URL("/client-viewer/field-review-queue", hubUrl), {
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

  let body: FieldReviewQueueResponse;
  try {
    body = await upstream.json();
  } catch {
    return Response.json({ error: "upstream returned a malformed response" }, { status: 502 });
  }

  return Response.json(body, { status: 200 });
}
