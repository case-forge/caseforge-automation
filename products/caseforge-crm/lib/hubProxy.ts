
import { reportBackendFailure } from "@/lib/backendFailure";
import { execFile } from "node:child_process";
import { timeHub } from "@/lib/apiTiming";

const CF_ACCESS_JWT_HEADER = "Cf-Access-Jwt-Assertion";
export const TAILNET_IDENTITY_HEADER = "X-CaseForge-Tailnet-Identity";

export interface TailnetIdentity {
  login: string;
  node: string;
  ip: string;
}

const WHOIS_TTL_MS = 5 * 60 * 1000;
const WHOIS_TIMEOUT_MS = 2000;
const whoisCache = new Map<string, { at: number; value: Omit<TailnetIdentity, "ip"> | null }>();

export function tailnetIp(value: string | null | undefined): string {
  let text = (value ?? "").trim().toLowerCase();
  if (!text || text.includes(",")) return "";
  if (text.startsWith("::ffff:")) text = text.slice(7);
  const v4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(text);
  if (v4) {
    const [a, b, c, d] = v4.slice(1).map(Number);
    if ([a, b, c, d].some((n) => n > 255)) return "";
    return a === 100 && b >= 64 && b <= 127 ? `${a}.${b}.${c}.${d}` : "";
  }
  return /^fd7a:115c:a1e0:[0-9a-f:]*$/.test(text) ? text : "";
}

const clean = (value: unknown): string => String(value ?? "").trim().replace(/[^A-Za-z0-9@._+-]/g, "_").slice(0, 120);

export function parseWhois(payload: unknown): Omit<TailnetIdentity, "ip"> | null {
  if (!payload || typeof payload !== "object") return null;
  const node = (payload as { Node?: Record<string, unknown> }).Node ?? {};
  const profile = (payload as { UserProfile?: Record<string, unknown> }).UserProfile ?? {};
  const tags = Array.isArray(node.Tags) ? node.Tags : [];
  const name = String(node.ComputedName ?? node.Name ?? "").replace(/\.$/, "");
  return { login: tags.length ? "" : clean(profile.LoginName), node: clean(name.split(".")[0]) };
}

function tailscaleWhois(ip: string): Promise<Omit<TailnetIdentity, "ip"> | null> {
  return new Promise((resolve) => {
    execFile("tailscale", ["whois", "--json", ip], { timeout: WHOIS_TIMEOUT_MS }, (err, stdout) => {
      if (err) return resolve(null);
      try {
        resolve(parseWhois(JSON.parse(stdout)));
      } catch {
        resolve(null);
      }
    });
  });
}

export async function tailnetIdentityHeader(
  request: Request,
  remoteUser: string | null,
  whois: (ip: string) => Promise<Omit<TailnetIdentity, "ip"> | null> = tailscaleWhois,
): Promise<Record<string, string>> {
  if (remoteUser) return {};
  const ip = tailnetIp(request.headers.get("x-forwarded-for"));
  if (!ip) return {};
  const cached = whoisCache.get(ip);
  let found: Omit<TailnetIdentity, "ip"> | null;
  if (cached && Date.now() - cached.at < WHOIS_TTL_MS) {
    found = cached.value;
  } else {
    found = await whois(ip).catch(() => null);
    whoisCache.set(ip, { at: Date.now(), value: found });
  }
  const identity: TailnetIdentity = { login: found?.login ?? "", node: found?.node ?? "", ip };
  return { [TAILNET_IDENTITY_HEADER]: JSON.stringify(identity) };
}

export function clearTailnetWhoisCache(): void {
  whoisCache.clear();
}

export const CLIENT_IP_HEADER = "X-CaseForge-Client-Ip";

export function clientIp(request: Request): string {
  const cf = (request.headers.get("cf-connecting-ip") || "").trim();
  if (/^[0-9a-fA-F:.]{3,45}$/.test(cf) && /[.:]/.test(cf)) return cf;
  return tailnetIp(request.headers.get("x-forwarded-for"));
}

export async function hubIdentityHeaders(request: Request, remoteUser: string | null): Promise<Record<string, string>> {
  const ip = clientIp(request);
  return {
    ...CRM_CLIENT_HEADER,
    ...(ip ? { [CLIENT_IP_HEADER]: ip } : {}),
    ...(remoteUser ? { "Remote-User": remoteUser } : {}),
    ...accessJwtHeader(request, remoteUser),
    ...(await tailnetIdentityHeader(request, remoteUser)),
  };
}

export interface HubConfig {
  hubUrl: string;
  token: string;
}

export const HUB_URL_ENV = "CASEFORGE_HUB_API_URL";
export const HUB_TOKEN_ENV = "CASEFORGE_CHAT_API_TOKEN";
export const HUB_STUB_ENV = "CASEFORGE_HUB_API_STUB";

export function hubConfig(): HubConfig | null {
  const hubUrl = process.env[HUB_URL_ENV];
  const token = process.env[HUB_TOKEN_ENV];
  return hubUrl && token ? { hubUrl, token } : null;
}

export function isStubMode(): boolean {
  return process.env[HUB_STUB_ENV] === "1";
}

function failure(path: string, body: unknown, status: number): Response {
  reportBackendFailure(path, status);
  return Response.json(body, { status });
}

export function notConfigured(): Response {
  return Response.json({ error: "CASEFORGE_HUB_API_URL/CASEFORGE_CHAT_API_TOKEN not configured on the server" }, { status: 503 });
}

export function accessJwtHeader(request: Request, remoteUser: string | null): Record<string, string> {
  const assertion = remoteUser ? request.headers.get(CF_ACCESS_JWT_HEADER) : null;
  return assertion ? { [CF_ACCESS_JWT_HEADER]: assertion } : {};
}

export const CRM_CLIENT_HEADER = { "X-CaseForge-Client": "client-viewer" } as const;

async function headersFor(
  request: Request,
  config: HubConfig,
  remoteUser: string | null,
  json: boolean,
): Promise<Record<string, string>> {
  return {
    Authorization: `Bearer ${config.token}`,
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(await hubIdentityHeaders(request, remoteUser)),
  };
}

export function detailMessage(body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const reasons = detail
      .map((d: { msg?: unknown }) => (typeof d?.msg === "string" ? d.msg : ""))
      .filter(Boolean);
    if (reasons.length > 0) return reasons.join("; ");
  }
  return "upstream request failed";
}

async function upstreamDetail(upstream: Response): Promise<string> {
  try {
    return detailMessage(await upstream.json());
  } catch {
    return "upstream request failed";
  }
}

function withParams(path: string, hubUrl: string, params: Record<string, string>): URL {
  const url = new URL(path, hubUrl);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return url;
}

export function hubGetJson(
  request: Request,
  path: string,
  params: Record<string, string>,
  remoteUser: string | null,
): Promise<Response> {
  return timeHub(request, () => hubGetJsonInner(request, path, params, remoteUser));
}

async function hubGetJsonInner(
  request: Request,
  path: string,
  params: Record<string, string>,
  remoteUser: string | null,
): Promise<Response> {
  const config = hubConfig();
  if (!config) return notConfigured();

  let upstream: Response;
  try {
    upstream = await fetch(withParams(path, config.hubUrl, params), {
      headers: await headersFor(request, config, remoteUser, false),
      signal: request.signal,
      cache: "no-store",
    });
  } catch {
    return failure(path, { error: "upstream request failed" }, 502);
  }
  if (!upstream.ok) {
    await upstream.body?.cancel().catch(() => undefined);
    return failure(path, { error: "upstream request failed" }, upstream.status);
  }
  try {
    return Response.json(await upstream.json(), { status: 200 });
  } catch {
    return failure(path, { error: "upstream returned a malformed response" }, 502);
  }
}

export function hubPostJson(
  request: Request,
  path: string,
  body: unknown,
  remoteUser: string | null,
  extraHeaders: Record<string, string> = {},
  method: "POST" | "PUT" | "PATCH" | "DELETE" = "POST",
): Promise<Response> {
  return timeHub(request, () => hubPostJsonInner(request, path, body, remoteUser, extraHeaders, method));
}

async function hubPostJsonInner(
  request: Request,
  path: string,
  body: unknown,
  remoteUser: string | null,
  extraHeaders: Record<string, string>,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
): Promise<Response> {
  const config = hubConfig();
  if (!config) return notConfigured();

  let upstream: Response;
  try {
    upstream = await fetch(new URL(path, config.hubUrl), {
      method,
      headers: { ...(await headersFor(request, config, remoteUser, true)), ...extraHeaders },
      body: method === "DELETE" ? undefined : JSON.stringify(body),
      signal: request.signal,
      cache: "no-store",
    });
  } catch {
    return failure(path, { error: "upstream request failed" }, 502);
  }
  if (!upstream.ok) {
    return failure(path, { error: await upstreamDetail(upstream) }, upstream.status);
  }
  try {
    return Response.json(await upstream.json(), { status: 200 });
  } catch {
    return failure(path, { error: "upstream returned a malformed response" }, 502);
  }
}

export function fileResponse(
  body: BodyInit | null,
  opts: { contentType: string | null; disposition: string | null; fallbackFilename: string },
): Response {
  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": opts.contentType || "text/calendar; charset=utf-8",
      "Content-Disposition": opts.disposition || `attachment; filename="${opts.fallbackFilename}"`,
      "Cache-Control": "no-store",
    },
  });
}

export function hubGetFile(
  request: Request,
  path: string,
  params: Record<string, string>,
  remoteUser: string | null,
  fallbackFilename: string,
): Promise<Response> {
  return timeHub(request, () => hubGetFileInner(request, path, params, remoteUser, fallbackFilename));
}

async function hubGetFileInner(
  request: Request,
  path: string,
  params: Record<string, string>,
  remoteUser: string | null,
  fallbackFilename: string,
): Promise<Response> {
  const config = hubConfig();
  if (!config) return notConfigured();

  let upstream: Response;
  try {
    upstream = await fetch(withParams(path, config.hubUrl, params), {
      headers: await headersFor(request, config, remoteUser, false),
      signal: request.signal,
      cache: "no-store",
    });
  } catch {
    return failure(path, { error: "upstream request failed" }, 502);
  }
  if (!upstream.ok) {
    await upstream.body?.cancel().catch(() => undefined);
    return failure(path, { error: "upstream request failed" }, upstream.status);
  }
  return fileResponse(upstream.body, {
    contentType: upstream.headers.get("content-type"),
    disposition: upstream.headers.get("content-disposition"),
    fallbackFilename,
  });
}

export async function readJsonObject(request: Request): Promise<Record<string, unknown> | null> {
  try {
    const parsed = await request.json();
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

export function asText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function asPositiveInt(value: unknown): number | null {
  const n = typeof value === "number" ? value : typeof value === "string" && /^\d+$/.test(value.trim()) ? Number(value) : NaN;
  return Number.isInteger(n) && n > 0 ? n : null;
}
