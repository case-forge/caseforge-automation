
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { pickHearingFields } from "@/lib/hearings";
import type { HearingEdits } from "@/lib/hearings";
import { asPositiveInt, asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubResolveHearingReview } from "@/lib/stub";
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
  const action = asText(payload.action);
  if (action !== "confirm" && action !== "dismiss") {
    return Response.json({ error: "action must be confirm or dismiss" }, { status: 400 });
  }
  const editedBy = editorFor(remoteUser);

  let edits: Record<string, unknown> | undefined;
  if (payload.edits !== undefined && payload.edits !== null) {
    const picked = pickHearingFields(payload.edits);
    if (picked.unknown.length) return Response.json({ error: `unknown field: ${picked.unknown.join(", ")}` }, { status: 400 });
    if (Object.keys(picked.fields).length) edits = picked.fields;
  }

  if (isStubMode()) {
    try {
      return Response.json(
        { hearing: stubResolveHearingReview(hearingId, action, edits as HearingEdits | undefined, editedBy) },
        { status: 200 },
      );
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : "stub error" }, { status: 422 });
    }
  }

  return hubPostJson(
    request,
    "/client-viewer/hearings/review-resolve",
    { hearing_id: hearingId, action, ...(edits ? { edits } : {}), edited_by: editedBy },
    remoteUser,
  );
}
