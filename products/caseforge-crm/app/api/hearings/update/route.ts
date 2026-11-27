
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { pickHearingFields } from "@/lib/hearings";
import type { HearingEdits } from "@/lib/hearings";
import { asPositiveInt, asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubUpdateHearing } from "@/lib/stub";
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
  const editedBy = editorFor(remoteUser);

  const { fields, unknown } = pickHearingFields(payload.edits);
  if (unknown.length) return Response.json({ error: `unknown field: ${unknown.join(", ")}` }, { status: 400 });
  if (Object.keys(fields).length === 0) return Response.json({ error: "edits must name at least one field" }, { status: 400 });
  const note = asText(payload.note);

  if (isStubMode()) {
    try {
      return Response.json({ hearing: stubUpdateHearing(hearingId, fields as HearingEdits, editedBy) }, { status: 200 });
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : "stub error" }, { status: 422 });
    }
  }

  return hubPostJson(
    request,
    "/client-viewer/hearings/update",
    { hearing_id: hearingId, edits: fields, edited_by: editedBy, ...(note ? { note } : {}) },
    remoteUser,
  );
}
