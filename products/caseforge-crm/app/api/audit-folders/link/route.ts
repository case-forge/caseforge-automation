
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";

export const dynamic = "force-dynamic";

function words(text: string, status: number): Response {
  return new Response(text, { status, headers: { "content-type": "text/plain; charset=utf-8" } });
}

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const search = request.nextUrl.searchParams;
  const client = (search.get("client") ?? "").trim().slice(0, 200);
  const path = (search.get("path") ?? "").trim().slice(0, 500);
  if (!client || !path) return words("A client and a path are needed.", 400);
  if (isStubMode()) return words("SharePoint links are not available in the demo.", 404);
  const res = await hubGetJson(request, "/client-viewer/audit-folders/link", { client, path }, remoteUser);
  if (res.status === 404) return words("That item is not in the file index yet. Try again after the next refresh.", 404);
  if (!res.ok) return words("The SharePoint link could not be made just now.", 502);
  const body = (await res.json().catch(() => null)) as { url?: unknown } | null;
  const url = typeof body?.url === "string" ? body.url : "";
  if (!/^https:\/\/[a-z0-9.-]+\.sharepoint\.com\//i.test(url)) return words("The SharePoint link could not be made just now.", 502);
  return Response.redirect(url, 302);
}
