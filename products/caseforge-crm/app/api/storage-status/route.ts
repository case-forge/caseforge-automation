
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { refuseUnlessDev } from "@/lib/crmRole";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubStorageStatus } from "@/lib/stubStorageStatus";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json(stubStorageStatus());
  return hubGetJson(request, "/client-viewer/storage-status", {}, remoteUser);
}
