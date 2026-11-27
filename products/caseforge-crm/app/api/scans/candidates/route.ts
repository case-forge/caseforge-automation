
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubCandidates } from "@/lib/stubScans";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const itemId = (request.nextUrl.searchParams.get("item_id") ?? "").trim();
  if (!itemId) return Response.json({ error: "item_id is required" }, { status: 400 });
  if (isStubMode()) return Response.json(stubCandidates(itemId));
  return hubGetJson(request, "/client-viewer/scans/candidates", { item_id: itemId }, remoteUser);
}
