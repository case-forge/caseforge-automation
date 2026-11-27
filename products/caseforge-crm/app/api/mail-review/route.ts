
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubGetJson, hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubControl, stubControlSave, stubDecide, stubDecideSave } from "@/lib/stubMailReview";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const POOL_OF_VIEW: Record<string, "control" | "review" | undefined> = { control: "control", "review-batch": "review", batch: undefined };
const VIEWS = ["decide", ...Object.keys(POOL_OF_VIEW)];

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const n = request.nextUrl.searchParams.get("n");
  const view = request.nextUrl.searchParams.get("view");
  if (view !== null) {
    if (!VIEWS.includes(view)) return Response.json({ error: "view must be decide, control, review-batch or batch" }, { status: 400 });
    const raw = request.nextUrl.searchParams.get(view === "decide" ? "offset" : "n");
    if (raw !== null && !/^\d+$/.test(raw)) return Response.json({ error: "that must be a number" }, { status: 400 });
    if (isStubMode()) return Response.json(view === "decide" ? stubDecide(Number(raw ?? 0)) : stubControl(raw === null ? null : Number(raw), POOL_OF_VIEW[view]));
    const path = view === "decide" ? "/client-viewer/mail-review/decide" : "/client-viewer/mail-review/control";
    const query: Record<string, string> = raw === null ? {} : { [view === "decide" ? "offset" : "n"]: raw };
    if (POOL_OF_VIEW[view]) query.pool = POOL_OF_VIEW[view]!;
    return hubGetJson(request, path, query, remoteUser);
  }
  if (isStubMode()) return Response.json({ error: "Improve mail classifier is not available in stub mode." }, { status: 404 });
  if (n !== null) {
    if (!/^\d+$/.test(n)) return Response.json({ error: "n must be an item number" }, { status: 400 });
    return hubGetJson(request, "/client-viewer/mail-review/item", { n }, remoteUser);
  }
  return hubGetJson(request, "/client-viewer/mail-review", {}, remoteUser);
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
  const text = (key: string) => String(payload[key] ?? "");
  if (payload.action === "decide") {
    const jobId = text("job_id").trim();
    if (!jobId) return Response.json({ error: "job_id is required" }, { status: 400 });
    if (isStubMode()) return Response.json(stubDecideSave(jobId));
    return hubPostJson(
      request,
      "/client-viewer/mail-review/decide",
      { job_id: jobId, route: text("route"), also: text("also"), logic: text("logic"), other_text: text("other_text") },
      remoteUser,
    );
  }
  if (payload.action === "control") {
    const jobId = text("job_id").trim();
    const verdict = text("verdict");
    if (!jobId) return Response.json({ error: "job_id is required" }, { status: 400 });
    if (!["agree", "disagree"].includes(verdict)) return Response.json({ error: "verdict must be agree or disagree" }, { status: 400 });
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text("date"))) return Response.json({ error: "date must be YYYY-MM-DD" }, { status: 400 });
    if (isStubMode()) return Response.json(stubControlSave(jobId, verdict));
    return hubPostJson(
      request,
      "/client-viewer/mail-review/control",
      { date: text("date"), job_id: jobId, verdict, route: text("route"), also: text("also"), logic: text("logic"), other_text: text("other_text") },
      remoteUser,
    );
  }
  if (payload.action === "control_release") {
    const jobId = text("job_id").trim();
    if (!jobId) return Response.json({ error: "job_id is required" }, { status: 400 });
    if (isStubMode()) return Response.json({ released: true });
    return hubPostJson(request, "/client-viewer/mail-review/control/release", { job_id: jobId }, remoteUser);
  }
  if (payload.action === "extend") {
    const days = Number(payload.days);
    if (days !== 7 && days !== 30) return Response.json({ error: "Extend by 7 or 30 days." }, { status: 400 });
    const by = editorFor(remoteUser);
    return hubPostJson(request, "/client-viewer/mail-review/extend", { days, by }, remoteUser);
  }
  if (payload.action === "answer") {
    const n = Number(payload.n);
    if (!Number.isInteger(n) || n < 1) return Response.json({ error: "n must be an item number" }, { status: 400 });
    return hubPostJson(
      request,
      "/client-viewer/mail-review/answer",
      {
        n,
        route: text("route"),
        also: text("also"),
        no_clean_answer: payload.no_clean_answer === true,
        matter: text("matter"),
        logic: text("logic"),
      },
      remoteUser,
    );
  }
  return Response.json({ error: "action must be decide, control, control_release, answer or extend" }, { status: 400 });
}
