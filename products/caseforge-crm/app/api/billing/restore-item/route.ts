
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubRestoreBillingItem } from "@/lib/stub";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  let payload: { item_id?: unknown };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const itemId = typeof payload.item_id === "string" ? payload.item_id.trim() : "";
  if (!itemId) return Response.json({ error: "item_id is required" }, { status: 400 });

  if (isStubMode()) {
    const result = stubRestoreBillingItem(itemId, remoteUser ?? "");
    return "item_id" in result ? Response.json(result) : Response.json(result, { status: 422 });
  }
  return hubPostJson(request, "/client-viewer/billing/restore-item", { item_id: itemId }, remoteUser);
}
