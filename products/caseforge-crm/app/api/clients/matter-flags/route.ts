
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubIdentityHeaders } from "@/lib/hubProxy";
import { stubFlagKinds, stubListFlags, stubSetFlag } from "@/lib/stub";
import { stubFlagReasons } from "@/lib/stubFlagReasons";
import { stubUserFor } from "@/lib/stubUser";
import type { MatterFlagsResponse } from "@/lib/types";
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
    return Response.json(
      {
        matter_id: matterId,
        flags: stubListFlags(matterId, stubUserFor(request, remoteUser)),
        reasons: stubFlagReasons(matterId),
        ...stubFlagKinds(matterId, stubUserFor(request, remoteUser)),
      },
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

  const upstreamUrl = new URL("/client-viewer/matter-flags", hubUrl);
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

  let body: MatterFlagsResponse;
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

  let payload: {
    matter_id?: string;
    flag_name?: string;
    is_set?: boolean;
    reason?: string;
    only_if_reason?: string;
    scope?: string;
  };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const matterId = (payload.matter_id ?? "").trim();
  const flagName = (payload.flag_name ?? "").trim();
  const setBy = editorFor(remoteUser);
  const reason = typeof payload.reason === "string" ? payload.reason.trim().slice(0, 200) : "";
  const onlyIfReason = typeof payload.only_if_reason === "string" ? payload.only_if_reason.trim().slice(0, 200) : "";
  const scope = payload.scope === "shared" ? "shared" : "personal";
  if (!matterId || !flagName) {
    return Response.json({ error: "matter_id and flag_name are required" }, { status: 400 });
  }
  if (typeof payload.is_set !== "boolean") {
    return Response.json({ error: "is_set must be a boolean" }, { status: 400 });
  }

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    try {
      const flags = stubSetFlag({ matterId, flagName, isSet: payload.is_set, setBy, reason, onlyIfReason, scope, user: stubUserFor(request, remoteUser) });
      return Response.json(
        { matter_id: matterId, flags, reasons: stubFlagReasons(matterId), ...stubFlagKinds(matterId, stubUserFor(request, remoteUser)) },
        { status: 200 },
      );
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
    upstream = await fetch(new URL("/client-viewer/matter-flags", hubUrl), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(await hubIdentityHeaders(request, remoteUser)),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        matter_id: matterId,
        flag_name: flagName,
        is_set: payload.is_set,
        set_by: setBy,
        ...(reason ? { reason } : {}),
        ...(onlyIfReason ? { only_if_reason: onlyIfReason } : {}),
        ...(scope === "shared" ? { scope } : {}),
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
      const errBody = await upstream.json();
      if (typeof errBody?.detail === "string") message = errBody.detail;
    } catch {

    }
    return Response.json({ error: message }, { status: upstream.status });
  }

  let body: MatterFlagsResponse;
  try {
    body = await upstream.json();
  } catch {
    return Response.json({ error: "upstream returned a malformed response" }, { status: 502 });
  }

  return Response.json(body, { status: 200 });
}
