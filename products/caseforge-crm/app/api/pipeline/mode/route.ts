
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubSetMode } from "@/lib/stubPipeline";
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
  const mode = String(payload.mode ?? "");
  const by = editorFor(remoteUser);
  if (mode !== "manual" && mode !== "auto") return Response.json({ error: "mode must be manual or auto" }, { status: 400 });

  if (isStubMode()) {
    const result = stubSetMode(mode);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/pipeline/mode", { mode, by, matter_id: payload.matter_id ?? null }, remoteUser);
}
