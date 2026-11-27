
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubScans } from "@/lib/stubScans";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json({ known: true, count: stubScans().total, checked_utc: "2026-10-25T12:00:00Z" });
  return hubGetJson(request, "/client-viewer/scans/count", {}, remoteUser);
}
