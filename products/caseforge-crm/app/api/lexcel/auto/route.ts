
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
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
  const matterId = String(payload.matter_id ?? "").trim();
  const by = editorFor(remoteUser);
  const resume = payload.resume === true;
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });

  if (isStubMode()) {
    return Response.json({ ok: true, message: resume ? "The automatic client care letter is back on." : "Cancelled: Case flow will not make the letter by itself. Make now still makes it." });
  }
  return hubPostJson(request, "/client-viewer/lexcel/auto", { matter_id: matterId, by, resume }, remoteUser);
}
