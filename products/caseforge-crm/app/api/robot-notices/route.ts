
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubAddRobotNotice, stubRobotNotices } from "@/lib/stubRobot";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json(stubRobotNotices());
  return hubGetJson(request, "/client-viewer/robot-notices", {}, remoteUser);
}

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (!isStubMode()) return Response.json({ error: "not available" }, { status: 404 });
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const text = (key: string) => String(body[key] ?? "").slice(0, 400);
  if (!text("title")) return Response.json({ error: "title required" }, { status: 400 });
  return Response.json(
    stubAddRobotNotice({ kind: text("kind") || "case_moved", title: text("title"), detail: text("detail"), matter_id: text("matter_id"), client_name: text("client_name") }),
  );
}
