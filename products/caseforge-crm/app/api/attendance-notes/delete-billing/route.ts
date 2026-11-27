
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubDeleteAttendanceNoteBilling } from "@/lib/stub";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  let payload: { draft_id?: unknown };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const draftId = typeof payload.draft_id === "string" ? payload.draft_id.trim() : "";
  if (!draftId) return Response.json({ error: "draft_id is required" }, { status: 400 });

  if (isStubMode()) {
    const result = stubDeleteAttendanceNoteBilling(draftId, remoteUser ?? "");

    return "state" in result ? Response.json(result) : Response.json(result, { status: 422 });
  }
  return hubPostJson(request, "/client-viewer/attendance-notes/delete-billing", { draft_id: draftId }, remoteUser);
}
