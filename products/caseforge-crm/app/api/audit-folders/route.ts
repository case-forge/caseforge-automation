
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { FOLDER_DAYS } from "@/lib/auditFolders";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubAuditFolders } from "@/lib/stubAuditFolders";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const search = request.nextUrl.searchParams;
  const folder = (search.get("folder") ?? "").slice(0, 200);
  const rawDays = search.get("days") ?? "";
  const days = /^\d{1,3}$/.test(rawDays) ? Math.min(Math.max(Number(rawDays), 1), FOLDER_DAYS) : FOLDER_DAYS;
  if (isStubMode()) return Response.json(stubAuditFolders(folder, days));
  const params: Record<string, string> = { days: String(days) };
  if (folder.trim()) params.folder = folder;
  return hubGetJson(request, "/client-viewer/audit-folders", params, remoteUser);
}
