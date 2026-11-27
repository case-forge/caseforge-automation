
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asPositiveInt, asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubRequestFromCourt } from "@/lib/stub";
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
  const kind = asText(payload.kind);
  if (kind !== "vacation" && kind !== "hybrid") return Response.json({ error: "kind must be vacation or hybrid" }, { status: 400 });
  const editedBy = editorFor(remoteUser);
  const reasons = Array.isArray(payload.reasons) ? payload.reasons.map(asText).filter(Boolean) : [];
  if (reasons.length === 0) return Response.json({ error: "choose or write at least one reason" }, { status: 400 });
  const form = asText(payload.form).toUpperCase();
  if (form && form !== "FP2" && form !== "C2") return Response.json({ error: "form must be FP2 or C2" }, { status: 400 });
  const draft = payload.draft !== false;

  if (isStubMode()) {
    try {
      return Response.json(stubRequestFromCourt(hearingId, kind, reasons, form, editedBy), { status: 200 });
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : "stub error" }, { status: 422 });
    }
  }

  return hubPostJson(
    request,
    "/client-viewer/hearings/request",
    { hearing_id: hearingId, kind, reasons, edited_by: editedBy, draft, ...(form ? { form } : {}) },
    remoteUser,
  );
}
