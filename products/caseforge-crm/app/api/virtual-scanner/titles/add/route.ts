
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubAddTitle } from "@/lib/stubVirtualScanner";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });
  const title = asText(payload.title);
  const by = editorFor(remoteUser);
  if (!title) return Response.json({ error: "Type the document's title." }, { status: 400 });
  if (isStubMode()) {
    const result = stubAddTitle(title, by);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/virtual-scanner/titles/add", { title, by }, remoteUser);
}
