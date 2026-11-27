
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { AMEND_HUB_PATHS, checkAmendRequest, hubBodyFor } from "@/lib/amendRound";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubAmendApprove, stubAmendDiscard, stubAmendPrepare } from "@/lib/stubPipeline";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  let payload: Record<string, unknown>;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return Response.json({ error: "malformed request body" }, { status: 400 });

  const checked = checkAmendRequest({ ...payload, by: editorFor(remoteUser) });
  if ("error" in checked) return Response.json({ error: checked.error }, { status: 400 });
  const body = checked.body;

  if (isStubMode()) {
    const out =
      body.action === "prepare"
        ? stubAmendPrepare(body.matter_id, body.by, body.email_text)
        : body.action === "approve"
          ? stubAmendApprove(body.matter_id, body.by, body.round, body.answers, body.keep_original, body.edits)
          : stubAmendDiscard(body.matter_id, body.by, body.round);
    return "error" in out ? Response.json(out, { status: 422 }) : Response.json(out);
  }
  return hubPostJson(request, AMEND_HUB_PATHS[body.action], hubBodyFor(body), remoteUser);
}
