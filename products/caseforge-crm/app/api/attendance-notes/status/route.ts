
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubAttendanceNoteStatus } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const draftId = (request.nextUrl.searchParams.get("draft_id") ?? "").trim();
  if (!draftId) return Response.json({ error: "draft_id is required" }, { status: 400 });

  if (isStubMode()) {
    const status = stubAttendanceNoteStatus(draftId);
    return status ? Response.json(status) : Response.json({ error: "no such note" }, { status: 404 });
  }
  return hubGetJson(request, "/client-viewer/attendance-notes/status", { draft_id: draftId }, remoteUser);
}
