
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubSetAutomatic } from "@/lib/stubTodos";
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
  const hidden = Array.isArray(payload.hidden) ? payload.hidden.map(String).slice(0, 20) : [];
  const body = { show: payload.show !== false, hidden };
  if (isStubMode()) return Response.json({ summary: stubSetAutomatic(body.show, body.hidden) });
  return hubPostJson(request, "/client-viewer/todos/automatic", body, remoteUser);
}
