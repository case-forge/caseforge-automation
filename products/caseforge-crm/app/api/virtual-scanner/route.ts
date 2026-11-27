
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubVirtualScanner } from "@/lib/stubVirtualScanner";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!/^\d+$/.test(matterId)) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (isStubMode()) return Response.json(stubVirtualScanner(matterId));
  return hubGetJson(request, "/client-viewer/virtual-scanner", { matter_id: matterId }, remoteUser);
}
