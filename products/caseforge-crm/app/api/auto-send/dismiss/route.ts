
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubDismissAutoSend } from "@/lib/stubAutoSend";
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
  const id = String(payload?.id ?? "").trim();
  if (!id) return Response.json({ error: "id is required" }, { status: 400 });

  if (isStubMode()) return Response.json(stubDismissAutoSend(id));
  return hubPostJson(request, "/client-viewer/auto-send/dismiss", { id }, remoteUser);
}
