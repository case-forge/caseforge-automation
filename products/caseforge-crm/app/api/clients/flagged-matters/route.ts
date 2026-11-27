
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubFlaggedMatters } from "@/lib/stub";
import { stubUserFor } from "@/lib/stubUser";
import type { FlaggedMattersResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const flags = request.nextUrl.searchParams.get("flags") ?? "persistent_caller,persistent_caller_respondent";

  if (isStubMode()) {
    return Response.json(stubFlaggedMatters(flags.split(","), stubUserFor(request, remoteUser)) satisfies FlaggedMattersResponse, { status: 200 });
  }

  return hubGetJson(request, "/client-viewer/flagged-matters", { flags }, remoteUser);
}
