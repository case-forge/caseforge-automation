
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { refuseUnlessDev } from "@/lib/crmRole";
import { hubGetJson, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubAppSettings, stubSave } from "@/lib/stubAppSettings";
import { STUB_MODELS_ADMIN_COOKIE } from "@/lib/stubModelRoles";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const HUB_PATH = "/client-viewer/settings";
const MAX_BODY_VALUES = 100;

const stubAdmin = (request: NextRequest) => request.cookies.get(STUB_MODELS_ADMIN_COOKIE)?.value !== "0";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json(stubAppSettings(stubAdmin(request)));
  return hubGetJson(request, HUB_PATH, {}, remoteUser);
}

export async function PATCH(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const body = await readJsonObject(request);
  const values = body?.values;
  if (!values || typeof values !== "object" || Array.isArray(values) || Object.keys(values).length === 0 || Object.keys(values).length > MAX_BODY_VALUES) {
    return Response.json({ error: "send the settings to change" }, { status: 400 });
  }
  if (isStubMode()) {
    const done = stubSave(values as Record<string, unknown>, stubAdmin(request));
    if (!done.ok) return Response.json({ error: done.message }, { status: done.status });
    return Response.json(stubAppSettings(true));
  }
  return hubPostJson(request, HUB_PATH, { values }, remoteUser, {}, "PATCH");
}
