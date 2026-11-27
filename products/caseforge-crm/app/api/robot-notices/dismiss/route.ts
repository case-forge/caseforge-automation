
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubDismissRobotNotice } from "@/lib/stubRobot";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  let payload: { notice_id?: string; by?: string };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const noticeId = (payload.notice_id ?? "").trim();
  if (!noticeId) return Response.json({ error: "notice_id is required" }, { status: 400 });
  const by = editorFor(remoteUser);
  if (isStubMode()) return Response.json(stubDismissRobotNotice(noticeId));
  return hubPostJson(request, "/client-viewer/robot-notices/dismiss", { notice_id: noticeId, by }, remoteUser);
}
