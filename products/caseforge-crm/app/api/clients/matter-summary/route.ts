
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { SUMMARY_PARTS, type SummaryPart } from "@/lib/matterSummary";
import { stubBillOfCosts, stubFlagKinds, stubListFlags, stubPersonMatters, stubSosStatus } from "@/lib/stub";
import { stubFlagReasons } from "@/lib/stubFlagReasons";
import { stubUserFor } from "@/lib/stubUser";

export const dynamic = "force-dynamic";

function stubPart(part: SummaryPart, matterId: string, user: string): unknown {
  switch (part) {
    case "flags":
      return { matter_id: matterId, flags: stubListFlags(matterId, user), reasons: stubFlagReasons(matterId), ...stubFlagKinds(matterId, user) };
    case "person_matters":
      return stubPersonMatters(matterId);
    case "sos_status":
      return stubSosStatus(matterId);
    case "bill_of_costs":
      return stubBillOfCosts(matterId);
  }
}

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  const asked = (request.nextUrl.searchParams.get("parts") ?? SUMMARY_PARTS.join(","))
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  const parts = [...new Set(asked)];
  if (!parts.length || parts.some((part) => !(SUMMARY_PARTS as readonly string[]).includes(part))) {
    return Response.json({ error: `parts must name one or more of: ${SUMMARY_PARTS.join(", ")}` }, { status: 400 });
  }

  if (isStubMode()) {
    const body: Record<string, unknown> = { matter_id: matterId, errors: [] };
    for (const part of parts as SummaryPart[]) body[part] = stubPart(part, matterId, stubUserFor(request, remoteUser));
    return Response.json(body, { status: 200 });
  }

  return hubGetJson(request, "/client-viewer/matter-summary", { matter_id: matterId, parts: parts.join(",") }, remoteUser);
}
