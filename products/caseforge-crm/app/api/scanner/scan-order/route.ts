
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubScanOrder } from "@/lib/stubVirtualScanner";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });
  const matterId = asText(payload.matter_id);
  const folder = asText(payload.folder);
  const name = asText(payload.name);
  const confirm = payload.confirm === true;
  const by = editorFor(remoteUser);
  if (!/^\d+$/.test(matterId) || !folder || !name) return Response.json({ error: "Pick an order filed in the client's Court-Orders folder." }, { status: 400 });
  if (isStubMode()) return Response.json(stubScanOrder(matterId, folder, name, confirm));
  return hubPostJson(request, "/client-viewer/scanner/scan-order", { matter_id: matterId, folder, name, confirm, by }, remoteUser);
}
