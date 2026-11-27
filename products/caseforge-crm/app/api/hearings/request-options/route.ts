
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { asPositiveInt, hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubRequestOptions } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const hearingId = asPositiveInt(request.nextUrl.searchParams.get("hearing_id"));
  if (hearingId === null) return Response.json({ error: "hearing_id is required" }, { status: 400 });

  if (isStubMode()) {
    try {
      return Response.json(stubRequestOptions(hearingId), { status: 200 });
    } catch (err) {
      return Response.json({ error: err instanceof Error ? err.message : "stub error" }, { status: 404 });
    }
  }

  return hubGetJson(request, "/client-viewer/hearings/request-options", { hearing_id: String(hearingId) }, remoteUser);
}
