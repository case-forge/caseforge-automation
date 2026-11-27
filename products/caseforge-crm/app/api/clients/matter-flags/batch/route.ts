
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubListFlags } from "@/lib/stub";
import { stubUserFor } from "@/lib/stubUser";

export const dynamic = "force-dynamic";

const MAX_IDS = 200;

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const ids = (request.nextUrl.searchParams.get("matter_ids") ?? "")
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean);
  if (ids.length === 0) return Response.json({ error: "matter_ids is required" }, { status: 400 });
  if (ids.length > MAX_IDS) return Response.json({ error: `at most ${MAX_IDS} matter_ids` }, { status: 400 });

  if (isStubMode()) {
    return Response.json({ flags_by_matter: Object.fromEntries(ids.map((id) => [id, stubListFlags(id, stubUserFor(request, remoteUser))])) }, { status: 200 });
  }

  return hubGetJson(request, "/client-viewer/matter-flags/batch", { matter_ids: ids.join(",") }, remoteUser);
}
