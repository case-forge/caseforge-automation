
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubSetNotificationState } from "@/lib/stubNotifications";
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
  const nid = String(payload.nid ?? "").trim().slice(0, 200);
  const state = String(payload.state ?? "").trim();
  const by = editorFor(remoteUser);
  if (!nid) return Response.json({ error: "nid is required" }, { status: 400 });
  if (state !== "dismissed" && state !== "hidden" && state !== "active") {
    return Response.json({ error: "state must be one of dismissed, hidden, active" }, { status: 400 });
  }

  if (isStubMode()) {
    const result = stubSetNotificationState(nid, state, by);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/notifications/state", { nid, state, by }, remoteUser);
}
