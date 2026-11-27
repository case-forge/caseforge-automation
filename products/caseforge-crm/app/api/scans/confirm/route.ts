
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubConfirm } from "@/lib/stubScans";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });
  const itemId = asText(payload.item_id);
  const matterId = asText(payload.matter_id);
  const copies = Number(payload.copies);
  const by = editorFor(remoteUser);
  const kind = asText(payload.kind);
  const confirm = payload.confirm === true;
  if (!itemId || !/^\d+$/.test(matterId)) return Response.json({ error: "Pick the scan and the client." }, { status: 400 });
  if (!Number.isInteger(copies) || copies < 1 || copies > 20) return Response.json({ error: "Copies must be a whole number from 1 to 20." }, { status: 400 });
  if (isStubMode()) return Response.json(stubConfirm(itemId, matterId, copies, kind, confirm));
  return hubPostJson(request, "/client-viewer/scans/confirm", { item_id: itemId, matter_id: matterId, copies, by, kind, confirm }, remoteUser);
}
