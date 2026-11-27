
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubRemoveTitle } from "@/lib/stubVirtualScanner";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });
  const titleId = asText(payload.title_id);
  const by = editorFor(remoteUser);
  if (!titleId) return Response.json({ error: "title_id is required" }, { status: 400 });
  if (isStubMode()) return Response.json(stubRemoveTitle(titleId));
  return hubPostJson(request, "/client-viewer/virtual-scanner/titles/remove", { title_id: titleId, by }, remoteUser);
}
