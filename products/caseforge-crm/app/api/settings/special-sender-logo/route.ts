
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { refuseUnlessDev } from "@/lib/crmRole";
import { hubConfig, hubIdentityHeaders, isStubMode, notConfigured } from "@/lib/hubProxy";
import { STUB_MODELS_ADMIN_COOKIE } from "@/lib/stubModelRoles";
import { stubSenderHasLogo, stubSetSenderLogo } from "@/lib/stubSpecialSenders";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const MAX_BYTES = 512 * 1024;
const SAFE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/svg+xml"]);
const STUB_LOGO_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#b45309"/><path d="M14 44 L32 14 L50 44 Z" fill="#fff"/></svg>';
const SAFE_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
  "Cross-Origin-Resource-Policy": "same-origin",
  "Cache-Control": "private, max-age=300",
};

const stubAdmin = (request: NextRequest) => request.cookies.get(STUB_MODELS_ADMIN_COOKIE)?.value !== "0";
const fail = (message: string, status: number): Response => Response.json({ error: message }, { status });

function senderId(request: NextRequest): string | null {
  const id = request.nextUrl.searchParams.get("id") ?? "";
  return /^[A-Za-z0-9_]{1,40}$/.test(id) ? id : null;
}

async function hubFetch(request: NextRequest, remoteUser: string | null, id: string, init: RequestInit): Promise<Response> {
  const config = hubConfig();
  if (!config) return notConfigured();
  try {
    return await fetch(new URL(`/client-viewer/settings/special-senders/${id}/logo`, config.hubUrl), {
      ...init,
      headers: { Authorization: `Bearer ${config.token}`, ...(await hubIdentityHeaders(request, remoteUser)), ...(init.headers as Record<string, string> | undefined) },
      cache: "no-store",
    });
  } catch {
    return fail("upstream request failed", 502);
  }
}

async function detail(upstream: Response): Promise<string> {
  try {
    const body = await upstream.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {

  }
  return "upstream request failed";
}

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const id = senderId(request);
  if (!id) return fail("no such special sender", 404);
  if (isStubMode()) {
    return stubSenderHasLogo(id) ? new Response(STUB_LOGO_SVG, { headers: { "Content-Type": "image/svg+xml", ...SAFE_HEADERS } }) : fail("No logo", 404);
  }
  const upstream = await hubFetch(request, remoteUser, id, {});
  if (!upstream.ok) {
    await upstream.body?.cancel().catch(() => undefined);
    return fail("No logo", upstream.status === 404 ? 404 : 502);
  }
  const type = (upstream.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase();
  if (!SAFE_TYPES.has(type)) return fail("upstream returned an unexpected file", 502);
  return new Response(await upstream.arrayBuffer(), { headers: { "Content-Type": type, ...SAFE_HEADERS } });
}

export async function POST(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request, { json: false });
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const id = senderId(request);
  if (!id) return fail("no such special sender", 404);
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > MAX_BYTES) return fail("The logo is larger than 512 KB.", 413);
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (bytes.length === 0) return fail("The file is empty.", 400);
  if (bytes.length > MAX_BYTES) return fail("The logo is larger than 512 KB.", 413);
  if (isStubMode()) {
    const done = stubSetSenderLogo(id, true, stubAdmin(request));
    return done.ok ? Response.json({ ok: true }) : fail(done.message, done.status);
  }
  const upstream = await hubFetch(request, remoteUser, id, { method: "POST", body: bytes, headers: { "Content-Type": "application/octet-stream" } });
  if (!upstream.ok) return fail(await detail(upstream), upstream.status);
  return Response.json({ ok: true });
}

export async function DELETE(request: NextRequest): Promise<Response> {
  const notDev = await refuseUnlessDev(request);
  if (notDev) return notDev;
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const id = senderId(request);
  if (!id) return fail("no such special sender", 404);
  if (isStubMode()) {
    const done = stubSetSenderLogo(id, false, stubAdmin(request));
    return done.ok ? Response.json({ ok: true }) : fail(done.message, done.status);
  }
  const upstream = await hubFetch(request, remoteUser, id, { method: "DELETE" });
  if (!upstream.ok) return fail(await detail(upstream), upstream.status);
  return Response.json({ ok: true });
}
