
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { asPositiveInt, hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubHearingHistory } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const hearingId = asPositiveInt(request.nextUrl.searchParams.get("hearing_id"));
  if (hearingId === null) return Response.json({ error: "hearing_id is required" }, { status: 400 });

  if (isStubMode()) return Response.json(stubHearingHistory(hearingId), { status: 200 });

  return hubGetJson(request, "/client-viewer/hearings/history", { hearing_id: String(hearingId) }, remoteUser);
}
