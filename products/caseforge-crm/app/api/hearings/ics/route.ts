
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { parseRange } from "@/lib/hearings";
import { fileResponse, hubGetFile, isStubMode } from "@/lib/hubProxy";
import { stubHearingsIcs } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const range = parseRange(request.nextUrl.searchParams);
  if (!range.ok) return Response.json({ error: range.error }, { status: 400 });
  const filename = `hearings-${range.from}-to-${range.to}.ics`;

  if (isStubMode()) {
    return fileResponse(stubHearingsIcs(range.from, range.to), {
      contentType: "text/calendar; charset=utf-8",
      disposition: null,
      fallbackFilename: filename,
    });
  }

  return hubGetFile(request, "/client-viewer/hearings/ics", { from: range.from, to: range.to }, remoteUser, filename);
}
