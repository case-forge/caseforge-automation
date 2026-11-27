
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import type { HearingStatus } from "@/lib/hearings";
import { asPositiveInt, asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubSetHearingStatus } from "@/lib/stub";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const STATUSES: readonly string[] = ["scheduled", "vacated", "cancelled"];

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });

  const hearingId = asPositiveInt(payload.hearing_id);
  if (hearingId === null) return Response.json({ error: "hearing_id is required" }, { status: 400 });
  const status = asText(payload.status);
  if (!STATUSES.includes(status)) {
    return Response.json({ error: "status must be scheduled, vacated or cancelled" }, { status: 400 });
  }
  const editedBy = editorFor(remoteUser);
  const note = asText(payload.note);

  if (isStubMode()) {
    try {
      return Response.json({ hearing: stubSetHearingStatus(hearingId, status as HearingStatus, editedBy) }, { status: 200 });
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : "stub error" }, { status: 422 });
    }
  }

  return hubPostJson(
    request,
    "/client-viewer/hearings/status",
    { hearing_id: hearingId, status, edited_by: editedBy, ...(note ? { note } : {}) },
    remoteUser,
  );
}
