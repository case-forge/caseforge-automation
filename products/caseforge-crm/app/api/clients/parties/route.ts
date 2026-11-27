
import { stubMadeParties } from "@/lib/stubClients";
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubIdentityHeaders } from "@/lib/hubProxy";
import type { MatterParty, MatterPartiesResponse } from "@/lib/types";
import { PARTY_FIELD_NAMES } from "@/lib/types";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) {
    return rejection;
  }

  const matterId = request.nextUrl.searchParams.get("matter_id") ?? "";
  if (!matterId.trim()) {
    return Response.json({ error: "matter_id is required" }, { status: 400 });
  }

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    return Response.json({ matter_id: matterId, parties: stubMadeParties(matterId) ?? [] } satisfies MatterPartiesResponse, { status: 200 });
  }

  const hubUrl = process.env.CASEFORGE_HUB_API_URL;
  const token = process.env.CASEFORGE_CHAT_API_TOKEN;
  if (!hubUrl || !token) {
    return Response.json(
      { error: "CASEFORGE_HUB_API_URL/CASEFORGE_CHAT_API_TOKEN not configured on the server" },
      { status: 503 },
    );
  }

  const upstreamUrl = new URL("/client-viewer/parties", hubUrl);
  upstreamUrl.searchParams.set("matter_id", matterId);

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
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

  let body: MatterPartiesResponse;
  try {
    body = await upstream.json();
  } catch {
    return Response.json({ error: "upstream returned a malformed response" }, { status: 502 });
  }

  return Response.json(body, { status: 200 });
}

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) {
    return rejection;
  }

  let payload: Record<string, string | undefined>;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const matterId = (payload.matter_id ?? "").trim();
  const editedBy = editorFor(remoteUser);
  if (!matterId) {
    return Response.json({ error: "matter_id is required" }, { status: 400 });
  }

  const body: Record<string, string> = { matter_id: matterId, edited_by: editedBy, note: (payload.note ?? "").trim() };
  for (const name of PARTY_FIELD_NAMES) body[name] = (payload[name] ?? "").trim();

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    return Response.json({ party_id: "stub-1", ...body }, { status: 201 });
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
    upstream = await fetch(new URL("/client-viewer/parties", hubUrl), {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, ...(await hubIdentityHeaders(request, remoteUser)), "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: request.signal,
      cache: "no-store",
    });
  } catch {
    return Response.json({ error: "upstream request failed" }, { status: 502 });
  }

  if (!upstream.ok) {
    let message = "upstream request failed";
    try {
      const errBody = await upstream.json();
      if (typeof errBody?.detail === "string") message = errBody.detail;
      else if (Array.isArray(errBody?.detail)) {
        const reasons = errBody.detail.map((d: { msg?: unknown }) => (typeof d?.msg === "string" ? d.msg : "")).filter(Boolean);
        if (reasons.length > 0) message = reasons.join("; ");
      }
    } catch {

    }
    return Response.json({ error: message }, { status: upstream.status });
  }

  let responseBody: MatterParty;
  try {
    responseBody = await upstream.json();
  } catch {
    return Response.json({ error: "upstream returned a malformed response" }, { status: 502 });
  }

  return Response.json(responseBody, { status: 201 });
}
