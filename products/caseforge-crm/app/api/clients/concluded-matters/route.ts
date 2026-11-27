
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubConcludedMatters } from "@/lib/stub";

export const dynamic = "force-dynamic";

function intParam(request: NextRequest, name: string, fallback: number, min: number, max: number): number {
  const parsed = Number.parseInt(request.nextUrl.searchParams.get(name) ?? "", 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const limit = intParam(request, "limit", 50, 1, 200);
  const offset = intParam(request, "offset", 0, 0, 1_000_000);

  if (isStubMode()) return Response.json(stubConcludedMatters(offset, limit));
  return hubGetJson(request, "/client-viewer/concluded-matters", { limit: String(limit), offset: String(offset) }, remoteUser);
}
