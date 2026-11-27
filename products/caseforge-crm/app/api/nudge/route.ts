
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const DOCS = ["client_docs", "witness_statement"];

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
  const matterId = String(payload?.matter_id ?? "").trim();
  const doc = String(payload?.doc ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (!DOCS.includes(doc)) return Response.json({ error: "doc must be client_docs or witness_statement" }, { status: 400 });

  if (isStubMode()) return Response.json({ ok: true, matter_id: matterId, doc, rule_id: "stub-rule", draft_id: "stub-draft" });
  return hubPostJson(request, "/client-viewer/nudge", { matter_id: matterId, doc }, remoteUser);
}
