
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { MAX_RANGE_DAYS, addDays, dayCount, londonToday } from "@/lib/billingChart";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubDailyTotals } from "@/lib/stubBillingChart";

export const dynamic = "force-dynamic";

const ISO = /^\d{4}-\d{2}-\d{2}$/;

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  const params = request.nextUrl.searchParams;
  const end = params.get("end") ?? londonToday();
  const start = params.get("start") ?? addDays(end, -29);
  if (!ISO.test(start) || !ISO.test(end) || Number.isNaN(Date.parse(start)) || Number.isNaN(Date.parse(end))) {
    return Response.json({ error: "start and end must be dates (YYYY-MM-DD)" }, { status: 400 });
  }
  if (end < start) return Response.json({ error: "the start date must not be after the end date" }, { status: 400 });
  if (dayCount(start, end) > MAX_RANGE_DAYS) return Response.json({ error: `choose at most ${MAX_RANGE_DAYS} days` }, { status: 400 });

  if (isStubMode()) return Response.json(stubDailyTotals(start, end));
  return hubGetJson(request, "/client-viewer/billing/daily-totals", { start, end }, remoteUser);
}
