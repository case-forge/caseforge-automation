
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { refuseUnlessDev } from "@/lib/crmRole";
import { hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubAppSettings, stubSetOperation } from "@/lib/stubAppSettings";
import { STUB_MODELS_ADMIN_COOKIE } from "@/lib/stubModelRoles";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function PUT(request: NextRequest, context: { params: Promise<{ key: string }> }): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const { key } = await context.params;
  const body = await readJsonObject(request);
  if (!body || typeof body.held !== "boolean") {
    return Response.json({ error: 'send {"held": true or false}' }, { status: 400 });
  }
  if (isStubMode()) {
    const admin = request.cookies.get(STUB_MODELS_ADMIN_COOKIE)?.value !== "0";
    const done = stubSetOperation(key, body.held, admin);
    if (!done.ok) return Response.json({ error: done.message }, { status: done.status });
    return Response.json(stubAppSettings(true));
  }
  return hubPostJson(request, `/client-viewer/settings/operations/${encodeURIComponent(key)}`, { held: body.held }, remoteUser, {}, "PUT");
}
