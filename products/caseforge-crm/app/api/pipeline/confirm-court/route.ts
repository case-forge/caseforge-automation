
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubNote } from "@/lib/stubPipeline";
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
  const court = String(payload.court ?? "").trim().slice(0, 200);
  const email = String(payload.email ?? "").trim().slice(0, 200);
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (!court && !email) return Response.json({ error: "choose the court, or type its email" }, { status: 400 });

  if (isStubMode()) return Response.json(stubNote(matterId, "court_email", by, `Court confirmed by ${by}: ${court || email}`));
  return hubPostJson(request, "/client-viewer/pipeline/confirm-court", { matter_id: matterId, by, court, email }, remoteUser);
}
