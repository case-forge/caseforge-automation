
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubGetJson, hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubCreateTodo, stubListTodos, stubSummary } from "@/lib/stubTodos";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const VIEWS = ["my_day", "important", "planned", "tasks", "completed", "all", "auto_court", "auto_bundle", "auto_signing", "auto_statements", "auto_drafts"];

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const sp = request.nextUrl.searchParams;
  const view = sp.get("view") ?? "all";
  if (!VIEWS.includes(view)) return Response.json({ error: "unknown view" }, { status: 400 });
  const matterRaw = sp.get("matter_id");
  const matterId = matterRaw && /^\d+$/.test(matterRaw) ? Number(matterRaw) : null;
  const includeDone = sp.get("include_done") === "true";

  if (isStubMode()) {
    return Response.json({ items: stubListTodos({ view, matterId, includeDone }), summary: stubSummary() });
  }
  const params: Record<string, string> = { view };
  if (matterId != null) params.matter_id = String(matterId);
  if (includeDone) params.include_done = "true";
  return hubGetJson(request, "/client-viewer/todos", params, remoteUser);
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

  payload = { ...payload, created_by: editorFor(remoteUser) };
  if (!String(payload.title ?? "").trim()) return Response.json({ error: "a task needs a title" }, { status: 400 });

  if (isStubMode()) {
    const result = stubCreateTodo(payload);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/todos", payload, remoteUser);
}
