
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { refuseUnlessDev } from "@/lib/crmRole";
import { hubGetJson, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { validModelId, validRole } from "@/lib/modelRoles";
import { STUB_MODELS_ADMIN_COOKIE, stubModelRoles, stubResetRole, stubSwapRole } from "@/lib/stubModelRoles";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const HUB_PATH = "/client-viewer/settings/models";

export async function GET(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json(stubModelRoles(request.cookies.get(STUB_MODELS_ADMIN_COOKIE)?.value !== "0"));
  return hubGetJson(request, HUB_PATH, {}, remoteUser);
}

export async function PUT(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const body = await readJsonObject(request);
  if (!body) return Response.json({ error: "malformed request body" }, { status: 400 });
  const { role, model, expected_old: expectedOld } = body;
  if (!validRole(role) || !validModelId(model)) return Response.json({ error: "choose a role and one of the listed models" }, { status: 400 });
  const expected = typeof expectedOld === "string" && validModelId(expectedOld) ? expectedOld : "";
  if (isStubMode()) {
    const done = stubSwapRole(role, model, expected, request.cookies.get(STUB_MODELS_ADMIN_COOKIE)?.value !== "0");
    return Response.json(done.ok ? done.change : { error: done.message }, { status: done.ok ? 200 : done.status });
  }
  return hubPostJson(request, `${HUB_PATH}/${role}`, { model, expected_old: expected }, remoteUser, {}, "PUT");
}

export async function DELETE(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const role = request.nextUrl.searchParams.get("role");
  if (!validRole(role)) return Response.json({ error: "choose a role" }, { status: 400 });
  if (isStubMode()) {
    const done = stubResetRole(role, request.cookies.get(STUB_MODELS_ADMIN_COOKIE)?.value !== "0");
    return Response.json(done.ok ? done.change : { error: done.message }, { status: done.ok ? 200 : done.status });
  }
  return hubPostJson(request, `${HUB_PATH}/${role}`, {}, remoteUser, {}, "DELETE");
}
