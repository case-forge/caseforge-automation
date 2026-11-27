
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubCancelPendingNewClient } from "@/lib/stubPendingNewClients";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  let payload: { pending_id?: unknown; by?: unknown };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const pendingId = Number(payload.pending_id);
  if (!Number.isInteger(pendingId) || pendingId < 1) return Response.json({ error: "pending_id is required" }, { status: 400 });
  const by = editorFor(remoteUser);

  if (isStubMode()) {
    const list = stubCancelPendingNewClient(pendingId);
    if (!list) return Response.json({ error: "Only a client still waiting for their forms can be cancelled." }, { status: 422 });
    return Response.json(list);
  }
  return hubPostJson(request, "/client-viewer/new-client/pending/cancel", { pending_id: pendingId, by }, remoteUser);
}
