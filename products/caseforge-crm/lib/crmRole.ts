
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { parseRole, type CrmRole } from "@/lib/crmRoleName";
import { hubConfig, hubIdentityHeaders, isStubMode, tailnetIp } from "@/lib/hubProxy";

export const STUB_ROLE_COOKIE = "caseforge_stub_role";

const CLOUDFLARE_HEADERS = ["cf-ray", "cf-connecting-ip", "cf-access-jwt-assertion", "cf-access-authenticated-user-email", "cf-ipcountry", "cf-visitor"];

export function tailnetOnly(request: Request): boolean {
  if (CLOUDFLARE_HEADERS.some((name) => request.headers.get(name))) return false;
  return Boolean(tailnetIp(request.headers.get("x-forwarded-for")));
}

function cookieValue(request: Request, name: string): string | null {
  for (const part of (request.headers.get("cookie") ?? "").split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return rest.join("=");
  }
  return null;
}

export interface RoleOutcome {
  role: CrmRole;

  rejection: Response | null;
}

export async function resolveCrmRole(request: Request): Promise<RoleOutcome> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return { role: "worker", rejection };
  if (isStubMode()) return { role: parseRole(cookieValue(request, STUB_ROLE_COOKIE) ?? "dev"), rejection: null };
  const config = hubConfig();
  if (!config) return { role: "worker", rejection: null };

  if (!remoteUser && !tailnetOnly(request)) return { role: "worker", rejection: null };
  try {
    const res = await fetch(new URL("/client-viewer/role", config.hubUrl), {
      headers: { Authorization: `Bearer ${config.token}`, ...(await hubIdentityHeaders(request, remoteUser)) },
      signal: request.signal,
      cache: "no-store",
    });
    if (!res.ok) {
      await res.body?.cancel().catch(() => undefined);
      return { role: "worker", rejection: null };
    }
    const body = (await res.json()) as { role?: unknown } | null;
    return { role: parseRole(body?.role), rejection: null };
  } catch {
    return { role: "worker", rejection: null };
  }
}

export async function refuseUnlessDev(request: Request): Promise<Response | null> {
  const { role, rejection } = await resolveCrmRole(request);
  if (rejection) return rejection;
  if (role === "dev") return null;
  return Response.json({ error: "Only a developer can see this" }, { status: 403, headers: { "Cache-Control": "no-store" } });
}
