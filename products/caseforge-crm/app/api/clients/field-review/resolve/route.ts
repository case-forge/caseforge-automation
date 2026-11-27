
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubIdentityHeaders } from "@/lib/hubProxy";
import type { FieldReviewFlag } from "@/lib/types";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) {
    return rejection;
  }

  let payload: { review_id?: string; resolved_by?: string };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const reviewId = (payload.review_id ?? "").trim();
  const resolvedBy = editorFor(remoteUser);
  if (!reviewId) {
    return Response.json({ error: "review_id is required" }, { status: 400 });
  }

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    const now = new Date().toISOString();
    return Response.json(
      {
        review_id: reviewId,
        matter_id: "",
        client_name: "",
        field_name: "",
        field_label: "",
        value_snapshot: "",
        note: "",
        flagged_by: "",
        flagged_at: now,
        resolved_by: resolvedBy,
        resolved_at: now,
      } satisfies FieldReviewFlag,
      { status: 200 },
    );
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
    upstream = await fetch(new URL("/client-viewer/field-review/resolve", hubUrl), {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, ...(await hubIdentityHeaders(request, remoteUser)), "Content-Type": "application/json" },
      body: JSON.stringify({ review_id: reviewId, resolved_by: resolvedBy }),
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
    } catch {

    }
    return Response.json({ error: message }, { status: upstream.status });
  }

  let body: FieldReviewFlag;
  try {
    body = await upstream.json();
  } catch {
    return Response.json({ error: "upstream returned a malformed response" }, { status: 502 });
  }

  return Response.json(body, { status: 200 });
}
