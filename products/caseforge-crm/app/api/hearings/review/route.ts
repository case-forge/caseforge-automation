
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubReviewHearings } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  if (isStubMode()) return Response.json(stubReviewHearings(), { status: 200 });

  return hubGetJson(request, "/client-viewer/hearings/review", {}, remoteUser);
}
