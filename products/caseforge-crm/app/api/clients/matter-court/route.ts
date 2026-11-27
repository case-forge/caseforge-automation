
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!/^\d+$/.test(matterId)) return Response.json({ error: "matter_id must be a matter number" }, { status: 400 });
  if (isStubMode()) {
    return Response.json({ matter_id: matterId, court: "", source: "" });
  }
  return hubGetJson(request, "/client-viewer/matter-court", { matter_id: matterId }, remoteUser);
}
