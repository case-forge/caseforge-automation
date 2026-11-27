
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubRecentAttendanceNotes } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });

  if (isStubMode()) return Response.json({ items: stubRecentAttendanceNotes(matterId) });
  return hubGetJson(request, "/client-viewer/attendance-notes/recent", { matter_id: matterId, hours: "48" }, remoteUser);
}
