
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });

  if (isStubMode()) return Response.json({ working: null, drafts: [] });
  return hubGetJson(request, "/client-viewer/attendance-notes/backup", { matter_id: matterId }, remoteUser);
}

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });
  const matterId = typeof payload.matter_id === "string" ? payload.matter_id.trim() : "";
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });

  if (isStubMode()) return Response.json({ working: null, drafts: [] });
  return hubPostJson(
    request,
    "/client-viewer/attendance-notes/backup",
    { matter_id: matterId, working: payload.working ?? null, drafts: Array.isArray(payload.drafts) ? payload.drafts : [] },
    remoteUser,
  );
}
