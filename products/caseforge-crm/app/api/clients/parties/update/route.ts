
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubIdentityHeaders } from "@/lib/hubProxy";
import { PARTY_FIELD_NAMES } from "@/lib/types";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

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
  const rowId = (payload.party_id ?? "").trim();
  const editedBy = editorFor(remoteUser);
  if (!matterId || !rowId) {
    return Response.json({ error: "matter_id and party_id are both required" }, { status: 400 });
  }

  const body: Record<string, string> = { matter_id: matterId, party_id: rowId, edited_by: editedBy, note: (payload.note ?? "").trim() };
  for (const name of PARTY_FIELD_NAMES) {
    const value = payload[name];
    if (value !== undefined) body[name] = value.trim();
  }

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    return Response.json(body, { status: 200 });
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
    upstream = await fetch(new URL("/client-viewer/parties/update", hubUrl), {
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

  try {
    return Response.json(await upstream.json(), { status: 200 });
  } catch {
    return Response.json({ error: "upstream returned a malformed response" }, { status: 502 });
  }
}
