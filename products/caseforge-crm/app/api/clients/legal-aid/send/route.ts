
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubSendLegalAid } from "@/lib/stubLegalAid";
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
  const matterId = String(payload.matter_id ?? "").trim();
  const by = editorFor(remoteUser);
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  const addressChecked = payload.address_checked === true;

  if (isStubMode()) return Response.json(stubSendLegalAid(matterId, by));
  return hubPostJson(request, "/client-viewer/legal-aid/send", { matter_id: matterId, by, address_checked: addressChecked }, remoteUser);
}
