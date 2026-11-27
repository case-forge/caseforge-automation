
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { refuseUnlessDev } from "@/lib/crmRole";
import { hubGetJson, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { STUB_MODELS_ADMIN_COOKIE } from "@/lib/stubModelRoles";
import { stubEmailClassifier, stubSaveEmailClassifier } from "@/lib/stubEmailClassifier";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const HUB_PATH = "/client-viewer/settings/email-classifier";

function entryMap(value: unknown): Record<string, string[]> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const out: Record<string, string[]> = {};
  for (const [name, entries] of Object.entries(value)) {
    if (!Array.isArray(entries) || !entries.every((e) => typeof e === "string")) return null;
    out[name] = entries as string[];
  }
  return out;
}

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json(stubEmailClassifier());
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
  const add = entryMap(body?.add ?? {});
  const remove = entryMap(body?.remove ?? {});
  if (!body || !add || !remove) return Response.json({ error: "malformed request body" }, { status: 400 });
  if (isStubMode()) {
    const isAdmin = request.cookies.get(STUB_MODELS_ADMIN_COOKIE)?.value !== "0";
    const done = stubSaveEmailClassifier(add, remove, isAdmin);
    return Response.json(done.ok ? done.view : { error: done.message }, { status: done.ok ? 200 : done.status });
  }
  return hubPostJson(request, HUB_PATH, { add, remove }, remoteUser, {}, "PUT");
}
