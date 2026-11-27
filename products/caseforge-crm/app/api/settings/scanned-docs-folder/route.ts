
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { refuseUnlessDev } from "@/lib/crmRole";
import { hubGetJson, hubPostJson, isStubMode } from "@/lib/hubProxy";
import { DEFAULT_SCANNED_FOLDER, validScannedFolder } from "@/lib/scannedFolder";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const HUB_PATH = "/client-viewer/settings/scanned-docs-folder";

let stubValue = DEFAULT_SCANNED_FOLDER;

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json({ path: stubValue, default: DEFAULT_SCANNED_FOLDER });
  return hubGetJson(request, HUB_PATH, {}, remoteUser);
}

export async function PUT(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  let payload: { path?: unknown };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const value = payload.path;
  if (!validScannedFolder(value)) {
    return Response.json({ error: "the folder must be a OneDrive path such as Company_Data/Scanned Docs" }, { status: 400 });
  }
  if (isStubMode()) {
    stubValue = value.trim().replace(/^\/+|\/+$/g, "") || DEFAULT_SCANNED_FOLDER;
    return Response.json({ path: stubValue, default: DEFAULT_SCANNED_FOLDER });
  }

  return hubPostJson(request, HUB_PATH, { path: value }, remoteUser, {}, "PUT");
}
