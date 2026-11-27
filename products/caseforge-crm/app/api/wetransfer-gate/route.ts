
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubWetransferGate } from "@/lib/stubMilestones";
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
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });

  if (isStubMode()) return Response.json(stubWetransferGate(matterId));
  return hubPostJson(request, "/client-viewer/wetransfer-gate", { matter_id: matterId }, remoteUser);
}
