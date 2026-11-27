
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetFile, isStubMode } from "@/lib/hubProxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });

  if (isStubMode()) {
    return new Response("\ufeffSTUB PERSON,Date\r\n", {
      status: 200,
      headers: { "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="Bill-of-Costs-STUB.csv"' },
    });
  }
  return hubGetFile(request, "/client-viewer/billing/export.csv", { matter_id: matterId }, remoteUser, "Bill-of-Costs.csv");
}
