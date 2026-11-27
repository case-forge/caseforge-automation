
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubCompleteTodo, stubDeleteTodo, stubUpdateTodo } from "@/lib/stubTodos";
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

  payload = { ...payload, by: editorFor(remoteUser) };
  if (!String(payload.todo_id ?? "").trim()) return Response.json({ error: "todo_id is required" }, { status: 400 });

  if (isStubMode()) {
    const result = stubDeleteTodo(String(payload.todo_id));
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/todos/delete", payload, remoteUser);
}
