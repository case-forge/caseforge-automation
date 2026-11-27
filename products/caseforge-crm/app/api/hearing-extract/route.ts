
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const MAX_TEXT = 4000;

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  let payload: { text?: unknown; today?: unknown };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const text = typeof payload.text === "string" ? payload.text.trim() : "";
  const today = typeof payload.today === "string" ? payload.today : "";
  if (!text) return Response.json({ error: "text is required" }, { status: 400 });
  if (text.length > MAX_TEXT) return Response.json({ error: "text is too long" }, { status: 400 });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(today)) return Response.json({ error: "today must be YYYY-MM-DD" }, { status: 400 });

  if (isStubMode()) {
    return Response.json({ court: "", hearing_type: "", counsel: "", chambers: "", mode: "", time: null, without_notice: false, notes: "" });
  }
  return hubPostJson(request, "/client-viewer/hearing-extract", { text, today }, remoteUser);
}
