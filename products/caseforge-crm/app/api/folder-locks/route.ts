
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { refuseUnlessDev } from "@/lib/crmRole";
import { editorFor } from "@/lib/editor";
import { hubGetJson, hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubFolderLocks, stubSetFolderLock } from "@/lib/stubFolderLocks";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  if (isStubMode()) return Response.json(stubFolderLocks());
  return hubGetJson(request, "/client-viewer/folder-locks", {}, remoteUser);
}

export async function POST(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  let payload: Record<string, unknown>;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const folder = String(payload.folder ?? "").trim();
  const by = editorFor(remoteUser);
  if (!folder) return Response.json({ error: "folder is required" }, { status: 400 });
  if (typeof payload.locked !== "boolean") return Response.json({ error: "locked must be true or false" }, { status: 400 });

  if (isStubMode()) {
    const result = stubSetFolderLock(folder, payload.locked, by);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/folder-locks", { folder, locked: payload.locked, by }, remoteUser);
}
