import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { gameOrigin, proxyGame } from "./gameProxy";

const SID = "a".repeat(32);

function req(path: string, init: RequestInit & { duplex?: string } = {}): Request {
  return new Request("http://crm.test" + path, init);
}

function engine(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const f = vi.fn((url: string | URL, init?: RequestInit) => Promise.resolve(handler(String(url), init ?? {})));
  vi.stubGlobal("fetch", f);
  return f;
}

beforeEach(() => {
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
  vi.stubEnv("NEXT_PUBLIC_CASEFORGE_DEMO", "");
  vi.stubEnv("CASEFORGE_DEMO_GAME_ORIGIN", "");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("proxyGame", () => {
  it("is a 404 outside demo mode", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const f = engine(() => new Response("x"));
    expect((await proxyGame(req("/training/"), undefined)).status).toBe(404);
    expect(f).not.toHaveBeenCalled();
  });

  it("forwards only the game's own paths", async () => {
    const f = engine(() => new Response("ok"));
    for (const parts of [["app.js"], ["api", "state"], ["api", "version"], undefined]) {
      expect((await proxyGame(req("/training/" + (parts ?? []).join("/")), parts)).status).toBe(200);
    }
    for (const parts of [["api", "clients"], ["..", "etc"], ["server.mjs"], ["engine", "engine.gen.js"], ["a%2Fb"], ["api/state"]]) {
      expect((await proxyGame(req("/training/x"), parts)).status).toBe(404);
    }
    expect(f).toHaveBeenCalledTimes(4);
  });

  it("allows POST only to api/action, and no other method", async () => {
    engine(() => new Response("{}"));
    expect((await proxyGame(req("/training/api/action", { method: "POST", body: "{}" }), ["api", "action"])).status).toBe(200);
    expect((await proxyGame(req("/training/api/state", { method: "POST", body: "{}" }), ["api", "state"])).status).toBe(404);
    expect((await proxyGame(req("/training/api/action", { method: "DELETE" }), ["api", "action"])).status).toBe(405);
  });

  it("sends the body and content type, and only the game's session cookie", async () => {
    const f = engine(() => new Response("{}", { headers: { "content-type": "application/json" } }));
    await proxyGame(
      req("/training/api/action", {
        method: "POST",
        body: '{"type":"x"}',
        headers: {
          "content-type": "application/json",
          cookie: `crm_session=secret; demo_game_sid=${SID}; other=1`,
          "cf-access-jwt-assertion": "jwt",
          authorization: "Bearer t",
          "x-forwarded-for": "client",
        },
      }),
      ["api", "action"],
    );
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8791/api/action");
    expect(init.method).toBe("POST");
    const h = new Headers(init.headers);
    expect(h.get("cookie")).toBe(`demo_game_sid=${SID}`);
    expect(h.get("content-type")).toBe("application/json");
    for (const n of ["cf-access-jwt-assertion", "authorization", "x-forwarded-for"]) expect(h.has(n)).toBe(false);
    expect(init.body).toBeTruthy();
  });

  it("sends no cookie when there is no game session, and ignores a malformed one", async () => {
    const f = engine(() => new Response("ok"));
    await proxyGame(req("/training/api/state", { headers: { cookie: "demo_game_sid=nothex; crm=1" } }), ["api", "state"]);
    expect(new Headers((f.mock.calls[0][1] as RequestInit).headers).has("cookie")).toBe(false);
  });

  it("passes the game's Set-Cookie back, drops other cookies and hop-by-hop headers, never caches", async () => {
    const up = new Headers({ "content-type": "text/html", connection: "keep-alive", "transfer-encoding": "chunked", "cache-control": "max-age=999" });
    up.append("set-cookie", `demo_game_sid=${SID}; Path=/; HttpOnly; SameSite=Lax`);
    up.append("set-cookie", "tracker=1; Path=/");
    engine(() => new Response("<html>", { headers: up }));
    const res = await proxyGame(req("/training/"), undefined);
    expect(res.headers.getSetCookie()).toEqual([`demo_game_sid=${SID}; Path=/; HttpOnly; SameSite=Lax`]);
    expect(res.headers.get("content-type")).toBe("text/html");
    expect(res.headers.has("connection")).toBe(false);
    expect(res.headers.has("transfer-encoding")).toBe(false);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(await res.text()).toBe("<html>");
  });

  it("keeps the trailing slash: /training moves to /training/", async () => {
    const f = engine(() => new Response("x"));
    const res = await proxyGame(req("/training"), undefined);
    expect(res.status).toBe(308);
    expect(res.headers.get("location")).toBe("/training/");
    expect(f).not.toHaveBeenCalled();
  });

  it("answers 502 with a one-line message when the engine is down", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("fetch failed"))));
    const res = await proxyGame(req("/training/api/state"), ["api", "state"]);
    expect(res.status).toBe(502);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect((await res.text()).trim().split("\n")).toHaveLength(1);
  });

  it("gives up on an engine that never answers within the connect timeout", async () => {
    vi.useFakeTimers();
    try {
      vi.stubGlobal(
        "fetch",
        vi.fn((_u: string, init: RequestInit) => new Promise((_ok, no) => init.signal!.addEventListener("abort", () => no(new Error("aborted"))))),
      );
      const pending = proxyGame(req("/training/api/state"), ["api", "state"]);
      await vi.advanceTimersByTimeAsync(2100);
      expect((await pending).status).toBe(502);
    } finally {
      vi.useRealTimers();
    }
  });

  it("answers 502 for an address that is not http(s)", async () => {
    vi.stubEnv("CASEFORGE_DEMO_GAME_ORIGIN", "file:///etc");
    const f = engine(() => new Response("x"));
    expect((await proxyGame(req("/training/"), undefined)).status).toBe(502);
    expect(f).not.toHaveBeenCalled();
  });

  it("reads the game's address at request time", async () => {
    const f = engine(() => new Response("ok"));
    await proxyGame(req("/training/app.js"), ["app.js"]);
    vi.stubEnv("CASEFORGE_DEMO_GAME_ORIGIN", "http://127.0.0.1:9999/");
    await proxyGame(req("/training/app.js"), ["app.js"]);
    expect(f.mock.calls.map((c) => c[0])).toEqual(["http://127.0.0.1:8791/app.js", "http://127.0.0.1:9999/app.js"]);
    expect(gameOrigin()).toBe("http://127.0.0.1:9999");
  });
});
