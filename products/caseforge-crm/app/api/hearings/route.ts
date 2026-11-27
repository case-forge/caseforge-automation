
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { pickHearingFields, parseRange } from "@/lib/hearings";
import type { HearingEdits } from "@/lib/hearings";
import { asText, hubGetJson, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubCreateHearing, stubListHearings } from "@/lib/stub";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const range = parseRange(request.nextUrl.searchParams);
  if (!range.ok) return Response.json({ error: range.error }, { status: 400 });

  if (isStubMode()) {
    return Response.json(stubListHearings(range.from, range.to, range.matterId || undefined), { status: 200 });
  }

  const params: Record<string, string> = { from: range.from, to: range.to };
  if (range.matterId) params.matter_id = range.matterId;
  return hubGetJson(request, "/client-viewer/hearings", params, remoteUser);
}

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });

  const editedBy = editorFor(remoteUser);
  const { edited_by: _editedBy, ...rest } = payload;
  void _editedBy;
  const { fields, unknown } = pickHearingFields(rest);
  if (unknown.length) return Response.json({ error: `unknown field: ${unknown.join(", ")}` }, { status: 400 });
  if (!asText(fields.case_ref) || !asText(fields.hearing_date)) {
    return Response.json({ error: "case_ref and hearing_date are required" }, { status: 400 });
  }

  if (isStubMode()) {
    try {
      return Response.json({ hearing: stubCreateHearing(fields as HearingEdits, editedBy) }, { status: 200 });
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : "stub error" }, { status: 422 });
    }
  }

  return hubPostJson(request, "/client-viewer/hearings", { ...fields, edited_by: editedBy }, remoteUser);
}
