
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetFile, isStubMode } from "@/lib/hubProxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const params = request.nextUrl.searchParams;
  const matterId = (params.get("matter_id") ?? "").trim();
  const form = (params.get("form") ?? "").trim();
  const reviewDate = (params.get("review_date") ?? "").trim();
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });
  if (form !== "review" && form !== "summary") return Response.json({ error: "say which form: review or summary" }, { status: 400 });

  if (isStubMode()) {
    return Response.json({ error: "The Word form is made by the hub: stub mode has no download." }, { status: 501 });
  }
  const fallback = `${form === "review" ? "File-Review" : "File-Summary-Sheet"}.docx`;
  return hubGetFile(request, "/client-viewer/case-review/export.docx", { matter_id: matterId, form, ...(reviewDate ? { review_date: reviewDate } : {}) }, remoteUser, fallback);
}
