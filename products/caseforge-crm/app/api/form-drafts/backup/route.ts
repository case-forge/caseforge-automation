
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const EMPTY = { saved_at: null, data: null };

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const matterId = (request.nextUrl.searchParams.get("matter_id") ?? "").trim();
  const formId = (request.nextUrl.searchParams.get("form_id") ?? "").trim();
  if (!matterId || !formId) return Response.json({ error: "matter_id and form_id are required" }, { status: 400 });

  if (isStubMode()) return Response.json(EMPTY);
  return hubGetJson(request, "/client-viewer/form-drafts/backup", { matter_id: matterId, form_id: formId }, remoteUser);
}

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });
  const matterId = typeof payload.matter_id === "string" ? payload.matter_id.trim() : "";
  const formId = typeof payload.form_id === "string" ? payload.form_id.trim() : "";
  if (!matterId || !formId) return Response.json({ error: "matter_id and form_id are required" }, { status: 400 });

  if (isStubMode()) return Response.json(EMPTY);
  return hubPostJson(
    request,
    "/client-viewer/form-drafts/backup",
    {
      matter_id: matterId,
      form_id: formId,
      saved_at: typeof payload.saved_at === "number" ? payload.saved_at : null,
      data: payload.data ?? null,
    },
    remoteUser,
  );
}
