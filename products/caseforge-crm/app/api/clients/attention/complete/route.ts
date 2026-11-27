
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubCompleteAttention } from "@/lib/stub";
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
  const taskId = String(payload.task_id ?? "").trim();
  const by = editorFor(remoteUser);
  if (!taskId) return Response.json({ error: "task_id is required" }, { status: 400 });

  if (isStubMode()) return Response.json(stubCompleteAttention(taskId));
  return hubPostJson(request, "/client-viewer/attention/complete", { task_id: taskId, by }, remoteUser);
}
