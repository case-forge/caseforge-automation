
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubPipeline } from "@/lib/stubPipeline";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (isStubMode()) return Response.json(stubPipeline(matterId));

  const poll = request.nextUrl.searchParams.get("poll") === "1";

  const fresh = request.nextUrl.searchParams.get("fresh") === "1";
  return hubGetJson(
    request,
    "/client-viewer/pipeline",
    { matter_id: matterId, ...(poll ? { poll: "true" } : {}), ...(fresh ? { fresh: "true" } : {}) },
    remoteUser,
  );
}
