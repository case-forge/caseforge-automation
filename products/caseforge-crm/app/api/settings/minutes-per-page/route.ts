
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { refuseUnlessDev } from "@/lib/crmRole";
import { editorFor } from "@/lib/editor";
import { hubGetJson, hubPostJson, isStubMode } from "@/lib/hubProxy";
import { validMinutesPerPage } from "@/lib/minutesPerPage";
import { DEFAULT_MINUTES_PER_PAGE } from "@/lib/types";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const HUB_PATH = "/client-viewer/settings/minutes-per-page";

let stubValue = DEFAULT_MINUTES_PER_PAGE;

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json({ minutes_per_page: stubValue });
  return hubGetJson(request, HUB_PATH, {}, remoteUser);
}

export async function PUT(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  let payload: { minutes_per_page?: unknown };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const value = payload.minutes_per_page;
  if (!validMinutesPerPage(value)) {
    return Response.json({ error: "minutes per page must be a whole number, 1 to 60" }, { status: 400 });
  }
  if (isStubMode()) {
    stubValue = value;
    return Response.json({ minutes_per_page: stubValue });
  }

  return hubPostJson(request, HUB_PATH, { minutes_per_page: value, by: editorFor(remoteUser) }, remoteUser, {}, "PUT");
}
