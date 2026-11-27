
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (matterId && !/^\d+$/.test(matterId)) return Response.json({ error: "matter_id must be a matter number" }, { status: 400 });
  if (isStubMode()) {
    return Response.json({ courts: ["Demo Portal Court", "Second Demo Court", "Third Demo Court"], court: matterId === "9001" ? "Demo Portal Court" : "" });
  }
  return hubGetJson(request, "/client-viewer/portal-courts", matterId ? { matter_id: matterId } : {}, remoteUser);
}
