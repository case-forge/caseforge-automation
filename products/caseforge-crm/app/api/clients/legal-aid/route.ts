
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubLegalAid } from "@/lib/stubLegalAid";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (isStubMode()) return Response.json(stubLegalAid(matterId));
  return hubGetJson(request, "/client-viewer/legal-aid", { matter_id: matterId }, remoteUser);
}
