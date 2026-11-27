
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { detailMessage, hubIdentityHeaders } from "@/lib/hubProxy";
import { stubListEdits, stubRecordEdit } from "@/lib/stub";
import type { ClientEdit } from "@/lib/types";
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
    return Response.json(stubListEdits(matterId), { status: 200 });
  }

  const hubUrl = process.env.CASEFORGE_HUB_API_URL;
  const token = process.env.CASEFORGE_CHAT_API_TOKEN;
  if (!hubUrl || !token) {
    return Response.json(
      { error: "CASEFORGE_HUB_API_URL/CASEFORGE_CHAT_API_TOKEN not configured on the server" },
      { status: 503 },
    );
  }

  const upstreamUrl = new URL("/client-viewer/client-edits", hubUrl);
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

  let body: ClientEdit[];
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

  let payload: { matter_id?: string; field_name?: string; new_value?: string; note?: string };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const matterId = (payload.matter_id ?? "").trim();
  const fieldName = (payload.field_name ?? "").trim();
  const newValue = (payload.new_value ?? "").trim();
  const editorName = editorFor(remoteUser);

  if (!matterId || !fieldName || typeof payload.new_value !== "string") {
    return Response.json(
      { error: "matter_id, field_name and new_value are all required" },
      { status: 400 },
    );
  }

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    try {
      const row = stubRecordEdit({
        matterId,
        fieldName,
        newValue,
        note: (payload.note ?? "").trim(),
        editedBy: editorName,
      });
      return Response.json(row, { status: 201 });
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : "stub error" }, { status: 422 });
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

  let upstream: Response;
  try {
    upstream = await fetch(new URL("/client-viewer/client-edits", hubUrl), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(await hubIdentityHeaders(request, remoteUser)),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        matter_id: matterId,
        field_name: fieldName,
        new_value: newValue,
        note: (payload.note ?? "").trim(),
        edited_by: editorName,
      }),
      signal: request.signal,
      cache: "no-store",
    });
  } catch {
    return Response.json({ error: "upstream request failed" }, { status: 502 });
  }

  if (!upstream.ok) {
    let message = "upstream request failed";
    try {
      message = detailMessage(await upstream.json());
    } catch {

    }
    return Response.json({ error: message }, { status: upstream.status });
  }

  let body: ClientEdit;
  try {
    body = await upstream.json();
  } catch {
    return Response.json({ error: "upstream returned a malformed response" }, { status: 502 });
  }

  return Response.json(body, { status: 201 });
}
