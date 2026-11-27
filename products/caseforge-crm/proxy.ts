import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { ROUTE_HEADER, routePattern } from "@/lib/apiTiming";
import { refuseCrossSiteWrite } from "@/lib/sameOrigin";

export function proxy(request: NextRequest): Response {
  const refused = refuseCrossSiteWrite(request);
  if (refused) return refused;

  const headers = new Headers(request.headers);
  headers.set(ROUTE_HEADER, routePattern(request.nextUrl.pathname));
  return NextResponse.next({ request: { headers } });
}

export const config = { matcher: "/api/:path*" };
