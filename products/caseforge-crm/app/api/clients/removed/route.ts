
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { isStubFixedId, isStubMadeId, stubDeleteMadeClient } from "@/lib/stubClients";
import { stubRemoved } from "@/lib/stubRemoved";
import { hubGetJson, hubPostJson, isStubMode } from "@/lib/hubProxy";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json({ items: stubRemoved(), undo_days: 30, purge_days: 30 });
  return hubGetJson(request, "/client-viewer/removed-clients", {}, remoteUser);
}

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
  const text = (key: string) => String(payload[key] ?? "").trim();
  const action = text("action");
  const matterId = text("matter_id");
  const by = editorFor(remoteUser);
  if (!/^\d+$/.test(matterId)) return Response.json({ error: "matter_id must be a matter number" }, { status: 400 });

  if (action === "remove") {
    const typedName = text("typed_name");
    const reason = text("reason");
    if (!typedName) return Response.json({ error: "Type the client's name to confirm." }, { status: 400 });
    if (reason.length < 3) return Response.json({ error: "Say why the client is being removed." }, { status: 400 });
    if (isStubMode()) {

      if (isStubFixedId(matterId)) {
        return Response.json({ error: "The three fixed stub clients cannot be removed." }, { status: 403 });
      }
      if (isStubMadeId(matterId)) stubDeleteMadeClient(matterId);
      return Response.json({ matter_id: matterId, done: ["stub"], not_done: [] });
    }
    return hubPostJson(
      request,
      "/client-viewer/clients/remove",
      { matter_id: matterId, typed_name: typedName, reason, by },
      remoteUser,
    );
  }
  if (action === "undo-merge") {
    if (isStubMode()) return Response.json({ matter_id: matterId, unmerged: true });
    return hubPostJson(request, "/client-viewer/clients/undo-merge", { matter_id: matterId, by }, remoteUser);
  }
  if (action === "undo") {
    if (isStubMode()) return Response.json({ matter_id: matterId, restored: true, cannot_restore: [] });
    return hubPostJson(request, "/client-viewer/clients/undo-remove", { matter_id: matterId, by }, remoteUser);
  }
  return Response.json({ error: "action must be remove, undo or undo-merge" }, { status: 400 });
}
