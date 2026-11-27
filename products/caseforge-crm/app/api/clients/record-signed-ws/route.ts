
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
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
  const matterId = String(payload?.matter_id ?? "").trim();
  const itemId = String(payload?.item_id ?? "").trim();
  if (!/^\d+$/.test(matterId) || !itemId) return Response.json({ error: "matter_id and item_id are required" }, { status: 400 });

  if (isStubMode()) return Response.json({ recorded: true, name: "WS.Demo.Person.pdf", signed: itemId === "STUB-WS-1" });
  return hubPostJson(request, "/client-viewer/record-signed-ws", { matter_id: matterId, item_id: itemId }, remoteUser);
}
