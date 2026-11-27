
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubFlagCounts } from "@/lib/stub";
import { stubUserFor } from "@/lib/stubUser";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  if (isStubMode()) return Response.json({ counts: stubFlagCounts(["flagged", "starred"], stubUserFor(request, remoteUser)) }, { status: 200 });

  return hubGetJson(request, "/client-viewer/flag-counts", { flags: "flagged,starred" }, remoteUser);
}
