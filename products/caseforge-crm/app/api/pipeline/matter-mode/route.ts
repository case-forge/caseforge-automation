
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubGetJson, hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubPipeline, stubSetMatterMode } from "@/lib/stubPipeline";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (isStubMode()) {
    const p = stubPipeline(matterId);
    return Response.json({ matter_id: matterId, setting: p.matter_mode, by: p.matter_mode_by, at: p.matter_mode_at, mode: p.mode, effective_mode: p.effective_mode });
  }
  return hubGetJson(request, "/client-viewer/pipeline/matter-mode", { matter_id: matterId }, remoteUser);
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
  const matterId = String(payload.matter_id ?? "").trim();
  const setting = String(payload.setting ?? "");
  const by = editorFor(remoteUser);
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (setting !== "inherit" && setting !== "auto" && setting !== "manual") {
    return Response.json({ error: "the client's setting must be inherit, auto or manual" }, { status: 400 });
  }

  if (isStubMode()) {
    const result = stubSetMatterMode(matterId, setting, by);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/pipeline/matter-mode", { matter_id: matterId, setting, by }, remoteUser);
}
