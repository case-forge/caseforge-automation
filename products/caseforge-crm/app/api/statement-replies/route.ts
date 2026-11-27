
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubGetJson, hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubSetReply, stubStatementReplies } from "@/lib/stubStatementReplies";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const state = (request.nextUrl.searchParams.get("state") ?? "").trim();
  if (state && state !== "approved" && state !== "amend") return Response.json({ error: "unknown state" }, { status: 400 });
  if (isStubMode()) {
    const all = stubStatementReplies();
    return Response.json(state ? { ...all, items: all.items.filter((i) => i.state === state) } : all);
  }
  return hubGetJson(request, "/client-viewer/statement-replies", state ? { state } : {}, remoteUser);
}

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
  const matterId = String(payload.matter_id ?? "").trim();
  const state = String(payload.state ?? "").trim();
  const note = String(payload.note ?? "");
  const by = editorFor(remoteUser);
  if (!matterId) return Response.json({ error: "matter_id is required" }, { status: 400 });

  if (isStubMode()) {
    const result = stubSetReply(matterId, state, note, by);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/statement-replies", { matter_id: matterId, state, note, by }, remoteUser);
}
