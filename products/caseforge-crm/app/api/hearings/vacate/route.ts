
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asPositiveInt, asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { pickHearingFields } from "@/lib/hearings";
import { stubVacateHearing } from "@/lib/stub";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const KINDS: readonly string[] = ["moved", "no_longer_acting", "court_vacated", "other"];

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
  if (!KINDS.includes(kind)) return Response.json({ error: "kind must be moved, no_longer_acting, court_vacated or other" }, { status: 400 });
  const editedBy = editorFor(remoteUser);
  const reason = asText(payload.reason);

  let replacement: Record<string, unknown> | undefined;
  if (payload.replacement !== undefined && payload.replacement !== null) {
    const { fields, unknown } = pickHearingFields(payload.replacement);
    if (unknown.length) return Response.json({ error: `unknown field: ${unknown.join(", ")}` }, { status: 400 });
    replacement = fields;
  }
  if (kind === "moved" && !replacement?.hearing_date) return Response.json({ error: "a moved hearing needs its new date" }, { status: 400 });
  if (kind !== "moved" && replacement) return Response.json({ error: "only a moved hearing has a replacement" }, { status: 400 });

  if (isStubMode()) {
    try {
      const out = stubVacateHearing(hearingId, kind, reason, replacement as { hearing_date?: string; hearing_time?: string } | undefined, editedBy);
      return Response.json(out, { status: 200 });
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : "stub error" }, { status: 422 });
    }
  }

  return hubPostJson(
    request,
    "/client-viewer/hearings/vacate",
    { hearing_id: hearingId, kind, edited_by: editedBy, ...(reason ? { reason } : {}), ...(replacement ? { replacement } : {}) },
    remoteUser,
  );
}
