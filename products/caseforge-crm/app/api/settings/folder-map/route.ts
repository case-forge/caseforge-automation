
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { refuseUnlessDev } from "@/lib/crmRole";
import { hubGetJson, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const HUB_PATH = "/client-viewer/settings/folder-map";
const STUB_ENTRIES = [
  "Attendance-Notes",
  "Court-Orders",
  "Lexcel-Docs",
  "Client's-Docs",
  "Correspondence-with-Client",
  "Correspondence-with-Court",
  "Preliminary-Docs",
].map((name, i) => ({ name, per_order: i < 2 }));

function stubView() {
  const folders = ["Attendance-Notes-(NMO)-EXAMPLE", "Court-Orders-(NMO)-EXAMPLE", ...STUB_ENTRIES.slice(2).map((e) => `${e.name}-EXAMPLE`)];
  return {
    can_edit: false,
    entries: STUB_ENTRIES,
    default: STUB_ENTRIES,
    is_default: true,
    changed_by: "",
    changed_at: "",
    max_entries: 60,
    max_name: 60,
    order_codes: ["NMO", "OO", "CAO", "PSO", "SIO"],
    preview: { surname: "EXAMPLE", orders: ["NMO"], folders, without_orders: folders.slice(2), warnings: [] },
    note: "Changes apply to clients opened after you save. Existing client folders are never moved, renamed or removed.",
  };
}

const demoRefusal = () => Response.json({ error: "The folder map cannot be changed in the demo." }, { status: 403 });

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json(stubView());
  return hubGetJson(request, HUB_PATH, {}, remoteUser);
}

export async function POST(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const body = await readJsonObject(request);
  if (!body || !Array.isArray(body.entries)) return Response.json({ error: "send the folders to check" }, { status: 400 });
  if (isStubMode()) return Response.json(stubView().preview);
  return hubPostJson(request, `${HUB_PATH}/preview`, { entries: body.entries }, remoteUser);
}

export async function PUT(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const body = await readJsonObject(request);
  if (!body || !Array.isArray(body.entries)) return Response.json({ error: "send the folders to save" }, { status: 400 });
  if (isStubMode()) return demoRefusal();
  return hubPostJson(request, HUB_PATH, { entries: body.entries }, remoteUser, {}, "PUT");
}

export async function DELETE(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return demoRefusal();
  return hubPostJson(request, HUB_PATH, {}, remoteUser, {}, "DELETE");
}
