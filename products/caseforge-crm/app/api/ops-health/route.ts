
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { STUB_OPS_HEALTH_COOKIE, stubOpsHealth } from "@/lib/stubOpsHealth";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) {
    const body = stubOpsHealth(request.cookies.get(STUB_OPS_HEALTH_COOKIE)?.value);
    return body ? Response.json(body) : Response.json({ error: "upstream request failed" }, { status: 403 });
  }
  return hubGetJson(request, "/client-viewer/ops-health", {}, remoteUser);
}
