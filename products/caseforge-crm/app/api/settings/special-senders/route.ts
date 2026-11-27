
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { refuseUnlessDev } from "@/lib/crmRole";
import { hubGetJson, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { STUB_MODELS_ADMIN_COOKIE } from "@/lib/stubModelRoles";
import { stubSaveSpecialSenders, stubSpecialSenders } from "@/lib/stubSpecialSenders";
import type { StubEdit } from "@/lib/stubSpecialSenders";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const HUB_PATH = "/client-viewer/settings/special-senders";

function edits(value: unknown): StubEdit[] | null {
  if (!Array.isArray(value)) return null;
  const out: StubEdit[] = [];
  for (const item of value) {
    if (typeof item !== "object" || item === null) return null;
    const o = item as Record<string, unknown>;
    if (typeof o.name !== "string" || !Array.isArray(o.domains) || !o.domains.every((d) => typeof d === "string")) return null;
    const mark = o.mark && typeof o.mark === "object" ? (o.mark as StubEdit["mark"]) : null;
    out.push({ ...(typeof o.id === "string" && o.id ? { id: o.id } : {}), name: o.name, domains: o.domains as string[], new_clients: o.new_clients === true, mark });
  }
  return out;
}

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json(stubSpecialSenders());
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
  const senders = edits(body?.senders ?? []);
  if (!body || !senders) return Response.json({ error: "malformed request body" }, { status: 400 });
  if (isStubMode()) {
    const isAdmin = request.cookies.get(STUB_MODELS_ADMIN_COOKIE)?.value !== "0";
    const done = stubSaveSpecialSenders(senders, isAdmin);
    return Response.json(done.ok ? done.view : { error: done.message }, { status: done.ok ? 200 : done.status });
  }
  return hubPostJson(request, HUB_PATH, { senders }, remoteUser, {}, "PUT");
}
