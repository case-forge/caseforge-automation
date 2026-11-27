
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, hubPostJson, isStubMode } from "@/lib/hubProxy";
import { isManualMilestone } from "@/lib/matterMilestones";
import { stubMatterMilestones, stubSetMilestone } from "@/lib/stubMilestones";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (isStubMode()) return Response.json(stubMatterMilestones(matterId));
  const live = request.nextUrl.searchParams.get("live") === "1" ? "true" : "false";
  return hubGetJson(request, "/client-viewer/matter-milestones", { matter_id: matterId, live }, remoteUser);
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
  const milestone = String(payload.milestone ?? "").trim();
  const at = String(payload.at ?? "").trim().slice(0, 40);
  const clear = payload.clear === true;
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (!isManualMilestone(milestone)) {
    return Response.json({ error: "only legal_aid_done and invoice_paid can be set by hand" }, { status: 400 });
  }
  if (isStubMode()) {
    const result = stubSetMilestone(matterId, milestone, at, clear);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }

  return hubPostJson(request, "/client-viewer/matter-milestones", { matter_id: matterId, milestone, at, clear }, remoteUser);
}
