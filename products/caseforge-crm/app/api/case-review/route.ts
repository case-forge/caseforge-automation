
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubCaseReview } from "@/lib/stubCaseReview";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  const reviewDate = (request.nextUrl.searchParams.get("review_date") ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (isStubMode()) {
    const result = stubCaseReview(matterId, reviewDate);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubGetJson(request, "/client-viewer/case-review", { matter_id: matterId, ...(reviewDate ? { review_date: reviewDate } : {}) }, remoteUser);
}
