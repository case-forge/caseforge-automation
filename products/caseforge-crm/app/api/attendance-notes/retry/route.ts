
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubRetryAttendanceNote } from "@/lib/stub";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  let payload: { draft_id?: string };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const draftId = (payload.draft_id ?? "").trim();
  if (!draftId) return Response.json({ error: "draft_id is required" }, { status: 400 });

  if (isStubMode()) return Response.json(stubRetryAttendanceNote(draftId));
  return hubPostJson(request, "/client-viewer/attendance-notes/retry", { draft_id: draftId }, remoteUser);
}
