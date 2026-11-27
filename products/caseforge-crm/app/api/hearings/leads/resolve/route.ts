
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asPositiveInt, asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubResolveLead } from "@/lib/stub";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });

  const leadId = asPositiveInt(payload.lead_id);
  if (leadId === null) return Response.json({ error: "lead_id is required" }, { status: 400 });
  const action = asText(payload.action);
  if (action !== "done" && action !== "dismissed") {
    return Response.json({ error: "action must be done or dismissed" }, { status: 400 });
  }
  const editedBy = editorFor(remoteUser);

  if (isStubMode()) {
    try {
      return Response.json(stubResolveLead(leadId, action, editedBy), { status: 200 });
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : "stub error" }, { status: 422 });
    }
  }

  return hubPostJson(request, "/client-viewer/hearings/leads/resolve", { lead_id: leadId, action, edited_by: editedBy }, remoteUser);
}
