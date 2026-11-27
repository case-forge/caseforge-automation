
const DEFAULT_ORIGIN = "http://127.0.0.1:8791";

export const CONNECT_TIMEOUT_MS = 2000;

const READ_PATHS = new Set(["", "index.html", "app.js", "embed.css", "styles.css", "api/state", "api/version"]);
const POST_PATHS = new Set(["api/action"]);
const SESSION_COOKIE = /(?:^|;\s*)(demo_game_sid=[a-f0-9]{32})(?:;|$)/;
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "trailers",
  "transfer-encoding",
  "upgrade",

  "content-encoding",
  "content-length",
  "set-cookie",
]);

export function demoMode(): boolean {
  return process.env.CASEFORGE_HUB_API_STUB === "1" || process.env.NEXT_PUBLIC_CASEFORGE_DEMO === "1";
}

export function gameOrigin(): string | null {
  const raw = (process.env.CASEFORGE_DEMO_GAME_ORIGIN || DEFAULT_ORIGIN).trim().replace(/\/+$/, "");
  try {
    const u = new URL(raw);
    return u.protocol === "http:" || u.protocol === "https:" ? u.origin : null;
  } catch {
    return null;
  }
}

function plain(status: number, message: string, extra: Record<string, string> = {}): Response {
  return new Response(message + "\n", {
    status,
    headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store", ...extra },
  });
}

export async function proxyGame(request: Request, parts: string[] | undefined): Promise<Response> {
  if (!demoMode()) return plain(404, "Not found");
  const method = request.method.toUpperCase();
  const path = (parts ?? []).join("/");
  if ((parts ?? []).some((p) => p === "" || p === "." || p === ".." || p.includes("/") || p.includes("\\"))) {
    return plain(404, "Not found");
  }
  const allowed = method === "POST" ? POST_PATHS : method === "GET" || method === "HEAD" ? READ_PATHS : null;
  if (!allowed) return plain(405, "Method not allowed", { allow: "GET, HEAD, POST" });
  if (!allowed.has(path)) return plain(404, "Not found");

  const url = new URL(request.url);
  if (path === "" && !url.pathname.endsWith("/")) {
    return new Response(null, { status: 308, headers: { location: "/training/" + url.search, "cache-control": "no-store" } });
  }

  const origin = gameOrigin();
  if (!origin) return plain(502, "The training game's address (CASEFORGE_DEMO_GAME_ORIGIN) is not a valid http(s) address.");

  const headers = new Headers();
  for (const name of ["content-type", "accept"]) {
    const v = request.headers.get(name);
    if (v) headers.set(name, v);
  }
  const sid = SESSION_COOKIE.exec(request.headers.get("cookie") || "");
  if (sid) headers.set("cookie", sid[1]);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CONNECT_TIMEOUT_MS);
  let upstream: Response;
  try {
    const init: RequestInit & { duplex?: "half" } = { method, headers, redirect: "manual", cache: "no-store", signal: controller.signal };
    if (method === "POST") {
      init.body = request.body;
      init.duplex = "half";
    }
    upstream = await fetch(`${origin}/${path}${url.search}`, init);
  } catch {
    return plain(502, "The training game's server is not answering. Start it with `npm run demo`, or check CASEFORGE_DEMO_GAME_ORIGIN.");
  } finally {
    clearTimeout(timer);
  }

  const out = new Headers();
  upstream.headers.forEach((value, name) => {
    if (!HOP_BY_HOP.has(name.toLowerCase())) out.set(name, value);
  });
  for (const cookie of upstream.headers.getSetCookie()) {

    if (/^demo_game_sid=/.test(cookie)) out.append("set-cookie", cookie);
  }
  out.set("cache-control", "no-store");
  return new Response(method === "HEAD" ? null : upstream.body, { status: upstream.status, headers: out });
}
