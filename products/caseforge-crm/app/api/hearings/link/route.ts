
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asPositiveInt, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubLinkHearing } from "@/lib/stub";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });

  const hearingId = asPositiveInt(payload.hearing_id);
  if (hearingId === null) return Response.json({ error: "hearing_id is required" }, { status: 400 });

  const matterId = asPositiveInt(payload.matter_id);
  if (matterId === null) return Response.json({ error: "matter_id must be a number" }, { status: 400 });
  const editedBy = editorFor(remoteUser);

  if (isStubMode()) {
    try {
      return Response.json(stubLinkHearing(hearingId, matterId, editedBy), { status: 200 });
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : "stub error" }, { status: 422 });
    }
  }

  return hubPostJson(request, "/client-viewer/hearings/link", { hearing_id: hearingId, matter_id: matterId, edited_by: editedBy }, remoteUser);
}
