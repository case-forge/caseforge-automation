
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubMatterMarkers } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (isStubMode()) {

    const intro = stubMatterMarkers(matterId).intro;
    return Response.json({ matter_id: matterId, url: intro?.status === "received" ? (intro.url ?? "") : "" });
  }
  return hubGetJson(request, "/client-viewer/intro-link", { matter_id: matterId }, remoteUser);
}
