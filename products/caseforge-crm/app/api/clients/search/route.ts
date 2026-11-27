
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubIdentityHeaders } from "@/lib/hubProxy";
import { stubSearch } from "@/lib/stub";
import type { ClientSearchResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { remoteUser, rejection } = await resolveIdentityForRoute(request.headers);
  if (rejection) {
    return rejection;
  }

  const q = request.nextUrl.searchParams.get("q") ?? "";
  if (q.trim().length < 2) {
    return Response.json({ error: "q must be at least 2 characters" }, { status: 400 });
  }
  const limit = request.nextUrl.searchParams.get("limit") ?? "20";
  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    try {
      return Response.json(stubSearch(q), { status: 200 });
    } catch {
      return Response.json({ error: "stub error path" }, { status: 502 });
    }
  }

  const hubUrl = process.env.CASEFORGE_HUB_API_URL;
  const token = process.env.CASEFORGE_CHAT_API_TOKEN;
  if (!hubUrl || !token) {

    return Response.json(
      { error: "CASEFORGE_HUB_API_URL/CASEFORGE_CHAT_API_TOKEN not configured on the server" },
      { status: 503 },
    );
  }

  const upstreamUrl = new URL("/clients/search", hubUrl);
  upstreamUrl.searchParams.set("q", q);
  upstreamUrl.searchParams.set("limit", limit);

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      headers: {
        Authorization: `Bearer ${token}`,
        ...(await hubIdentityHeaders(request, remoteUser)),
      },
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

  let body: ClientSearchResponse;
  try {
    body = await upstream.json();
  } catch {
    return Response.json({ error: "upstream returned a malformed response" }, { status: 502 });
  }

  return Response.json(body, { status: 200 });
}
