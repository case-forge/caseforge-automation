
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubResumePendingNewClient } from "@/lib/stubPendingNewClients";
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
    const made = stubResumePendingNewClient(pendingId);
    if (!made) return Response.json({ error: "That new client is not on the waiting list. Nothing was made." }, { status: 422 });
    return Response.json(made);
  }
  return hubPostJson(request, "/client-viewer/new-client/pending/resume", { pending_id: pendingId, by }, remoteUser);
}
