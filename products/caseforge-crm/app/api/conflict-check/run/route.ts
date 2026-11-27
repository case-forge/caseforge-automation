
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubRunConflictCheck } from "@/lib/stubConflict";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });
  const matterId = asText(payload.matter_id);
  const by = editorFor(remoteUser);
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });

  if (isStubMode()) {
    const result = stubRunConflictCheck(matterId, by);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/conflict-check/run", { matter_id: matterId, by }, remoteUser);
}
