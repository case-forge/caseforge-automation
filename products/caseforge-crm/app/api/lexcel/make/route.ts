
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubMakeLexcel } from "@/lib/stubLexcel";
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
  const kind = String(payload.kind ?? "").trim();
  const by = editorFor(remoteUser);
  const variant = String(payload.variant ?? "").trim();
  if (!matterId || !kind) return Response.json({ error: "matter_id and kind are required" }, { status: 400 });

  if (isStubMode()) {
    const result = stubMakeLexcel(matterId, kind, by, variant);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/lexcel/make", { matter_id: matterId, kind, by, variant: variant || null }, remoteUser);
}
