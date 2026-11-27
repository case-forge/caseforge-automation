
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { recipientKind } from "@/lib/pipelineDisplay";
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
  const kind = recipientKind(String(payload.kind ?? ""));
  const name = String(payload.name ?? "").trim().slice(0, 120);
  const email = String(payload.email ?? "").trim().slice(0, 200);
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (!kind || !name || !email) return Response.json({ error: "say who they are (law firm, hospital, school or other), their name and their email" }, { status: 400 });

  if (isStubMode()) return Response.json(stubNote(matterId, "serve_other", by, `Recipient added by ${by}: ${name} (${kind}, ${email})`));
  return hubPostJson(request, "/client-viewer/pipeline/service-recipient", { matter_id: matterId, by, kind, name, email }, remoteUser);
}
