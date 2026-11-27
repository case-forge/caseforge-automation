
import { createRemoteJWKSet, jwtVerify } from "jose";
import { timeIdentity } from "@/lib/apiTiming";

export const CF_ACCESS_JWT_HEADER = "Cf-Access-Jwt-Assertion";
export const CF_ACCESS_EMAIL_HEADER = "Cf-Access-Authenticated-User-Email";

const TUNNEL_MARKER_HEADERS = ["Cf-Connecting-Ip", "Cf-Ray"] as const;

export function accessConfigProblem(env: NodeJS.ProcessEnv): string | null {
  if (env.NODE_ENV !== "production" || env.NEXT_PHASE === "phase-production-build") return null;
  if (!env.CASEFORGE_HUB_API_URL || env.CASEFORGE_HUB_API_STUB === "1") return null;
  if (env.CASEFORGE_CF_ACCESS_TEAM_DOMAIN && env.CASEFORGE_CF_ACCESS_AUD) return null;
  return "CASEFORGE_CF_ACCESS_TEAM_DOMAIN and CASEFORGE_CF_ACCESS_AUD must both be set when the CRM serves the live hub";
}

export type AccessIdentity =
  | { kind: "absent" }

  | { kind: "identified"; email: string; exp?: number }
  | { kind: "rejected"; reason: string };

let cachedJWKS: ReturnType<typeof createRemoteJWKSet> | undefined;
let cachedTeamDomain: string | undefined;

function getJWKS(teamDomain: string): ReturnType<typeof createRemoteJWKSet> {
  if (!cachedJWKS || cachedTeamDomain !== teamDomain) {
    cachedJWKS = createRemoteJWKSet(new URL(`https://${teamDomain}/cdn-cgi/access/certs`), {

      timeoutDuration: 5000,
    });
    cachedTeamDomain = teamDomain;
  }
  return cachedJWKS;
}

export const ACCESS_TEAM_DOMAIN_ENV = "CASEFORGE_CF_ACCESS_TEAM_DOMAIN";
export const ACCESS_AUD_ENV = "CASEFORGE_CF_ACCESS_AUD";

export async function resolveAccessIdentity(headers: Headers): Promise<AccessIdentity> {
  const teamDomain = process.env[ACCESS_TEAM_DOMAIN_ENV];
  const aud = process.env[ACCESS_AUD_ENV];
  const jwt = headers.get(CF_ACCESS_JWT_HEADER);
  const emailHeader = headers.get(CF_ACCESS_EMAIL_HEADER);

  if (!teamDomain || !aud) {
    if (teamDomain === "" || aud === "") {

      console.warn(
        "[accessIdentity] CASEFORGE_CF_ACCESS_TEAM_DOMAIN/CASEFORGE_CF_ACCESS_AUD present but empty - Access identity is disabled as if unset; check the deployment env",
      );
    }

    return { kind: "absent" };
  }

  if (!jwt) {
    if (emailHeader) {

      console.warn(
        "[accessIdentity] rejected: Cf-Access-Authenticated-User-Email present without a Cf-Access-Jwt-Assertion",
      );
      return { kind: "rejected", reason: "email header present without a JWT assertion" };
    }
    if (TUNNEL_MARKER_HEADERS.some((name) => headers.get(name))) {
      console.warn("[accessIdentity] rejected: request came through the tunnel without a Cf-Access-Jwt-Assertion");
      return { kind: "rejected", reason: "tunnel request without an Access assertion" };
    }
    return { kind: "absent" };
  }

  try {
    const { payload } = await jwtVerify(jwt, getJWKS(teamDomain), {
      issuer: `https://${teamDomain}`,
      audience: aud,
      algorithms: ["RS256"],
    });
    const email = typeof payload.email === "string" ? payload.email : "";
    if (!email) {
      console.warn("[accessIdentity] rejected: validated JWT carried no usable email claim");
      return { kind: "rejected", reason: "validated JWT missing email claim" };
    }
    const exp = typeof payload.exp === "number" ? payload.exp : undefined;
    return { kind: "identified", email, exp };
  } catch (err) {

    const reason = err instanceof Error ? err.message : "unknown JWT verification error";
    console.warn(`[accessIdentity] rejected: JWT verification failed (${reason})`);
    return { kind: "rejected", reason: "JWT verification failed" };
  }
}

export interface IdentityOutcome {

  remoteUser: string | null;

  rejection: Response | null;
}

export function resolveIdentityForRoute(headers: Headers): Promise<IdentityOutcome> {
  return timeIdentity(headers, () => resolveIdentityOutcome(headers));
}

async function resolveIdentityOutcome(headers: Headers): Promise<IdentityOutcome> {
  const identity = await resolveAccessIdentity(headers);
  if (identity.kind === "rejected") {
    return {
      remoteUser: null,
      rejection: Response.json({ error: "identity verification failed" }, { status: 403 }),
    };
  }
  return {
    remoteUser: identity.kind === "identified" ? identity.email : null,
    rejection: null,
  };
}
