
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubMatterNeighbour } from "@/lib/stubMatterNeighbour";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  const dir = request.nextUrl.searchParams.get("dir") ?? "";
  if (!/^\d+$/.test(matterId)) return Response.json({ error: "matter_id must be a matter number" }, { status: 400 });
  if (dir !== "prev" && dir !== "next") return Response.json({ error: "dir must be prev or next" }, { status: 400 });

  if (isStubMode()) return Response.json({ matter_id: stubMatterNeighbour(matterId, dir) });
  return hubGetJson(request, "/client-viewer/matter-neighbour", { matter_id: matterId, dir }, remoteUser);
}
