
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubSaveCaseReview } from "@/lib/stubCaseReview";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });
  const matterId = asText(payload.matter_id);
  const reviewDate = asText(payload.review_date);
  const by = editorFor(remoteUser);
  const answers = payload.answers && typeof payload.answers === "object" && !Array.isArray(payload.answers) ? payload.answers : null;
  if (!matterId || !reviewDate || !answers) return Response.json({ error: "matter_id, review_date and answers are required" }, { status: 400 });

  if (isStubMode()) {
    const result = stubSaveCaseReview(matterId, reviewDate, answers, by);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/case-review/save", { matter_id: matterId, review_date: reviewDate, by, answers }, remoteUser);
}
