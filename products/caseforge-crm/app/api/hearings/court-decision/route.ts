
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asPositiveInt, asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubCourtDecision } from "@/lib/stub";
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
  if (typeof payload.agreed !== "boolean") return Response.json({ error: "agreed must be true or false" }, { status: 400 });
  const editedBy = editorFor(remoteUser);

  if (isStubMode()) {
    try {
      return Response.json({ hearing: stubCourtDecision(hearingId, payload.agreed, editedBy) }, { status: 200 });
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : "stub error" }, { status: 422 });
    }
  }

  return hubPostJson(
    request,
    "/client-viewer/hearings/court-decision",
    { hearing_id: hearingId, agreed: payload.agreed, edited_by: editedBy },
    remoteUser,
  );
}
