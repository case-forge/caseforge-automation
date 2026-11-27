
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import type { AuditKind } from "@/lib/auditTrail";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubAuditTrail } from "@/lib/stubAuditTrail";

export const dynamic = "force-dynamic";

const KINDS = new Set(["all", "person", "agent", "automation"]);

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const search = request.nextUrl.searchParams;
  const kind = (KINDS.has(search.get("kind") ?? "") ? search.get("kind") : "all") as AuditKind;
  const q = (search.get("q") ?? "").slice(0, 120);
  if (isStubMode()) return Response.json(stubAuditTrail(kind, q));
  const params: Record<string, string> = { kind };
  for (const key of ["days", "limit", "offset"]) {
    const value = search.get(key);
    if (value && /^\d{1,6}$/.test(value)) params[key] = value;
  }
  if (q.trim()) params.q = q;
  return hubGetJson(request, "/client-viewer/audit-trail", params, remoteUser);
}
