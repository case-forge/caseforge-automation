
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubRun } from "@/lib/stubPipeline";
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
  const step = String(payload.step ?? "").trim();
  const by = editorFor(remoteUser);
  if (!matterId || !step) return Response.json({ error: "matter_id and step are required" }, { status: 400 });

  if (isStubMode()) {
    const result = stubRun(matterId, step, by, String(payload.variant ?? ""));
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/pipeline/run", { matter_id: matterId, step, by, variant: payload.variant ?? null }, remoteUser);
}
