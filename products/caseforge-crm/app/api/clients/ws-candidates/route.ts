
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!/^\d+$/.test(matterId)) return Response.json({ error: "matter_id must be a matter number" }, { status: 400 });
  if (isStubMode()) {
    return Response.json({
      files: [
        { item_id: "STUB-WS-1", name: "WS.Demo.Person.pdf", modified: "2026-07-15T10:00:00Z", signed: true },
        { item_id: "STUB-WS-2", name: "WS.DEMO.draft.pdf", modified: "2026-07-01T10:00:00Z", signed: false },
      ],
    });
  }
  return hubGetJson(request, "/client-viewer/ws-candidates", { matter_id: matterId }, remoteUser);
}
