
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubSetFlag } from "@/lib/stubAuditFolders";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
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
  const client = String(payload.client ?? "").trim().slice(0, 200);
  const path = String(payload.path ?? "").trim().slice(0, 500);
  if (!client || !path) return Response.json({ error: "client and path are required" }, { status: 400 });
  if (typeof payload.flagged !== "boolean") return Response.json({ error: "flagged must be true or false" }, { status: 400 });
  const type = payload.type === "folder" ? "folder" : "file";

  if (isStubMode()) return Response.json(stubSetFlag(client, path, payload.flagged));
  return hubPostJson(request, "/client-viewer/audit-folders/flag", { client, path, type, flagged: payload.flagged }, remoteUser);
}
