import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/glitchtip-tunnel/route";
import { reportBackendFailure, routeName } from "./backendFailure";
import { envelopeUrl, filterEnvelope, MAX_ENVELOPE_BYTES, parseDsn } from "./glitchtipTunnel";

const DSN = "http://abc123@glitchtip.example.invalid:8140/1";
const allowed = parseDsn(DSN)!;

function envelope(opts: { dsn?: string; type?: string; event?: object } = {}): string {
  const event = opts.event ?? { message: "boom", request: { url: "https://crm.example.invalid/api/clients/search?q=jane%20example&limit=5" } };
  const payload = JSON.stringify(event);
  return [
    JSON.stringify({ event_id: "e1", dsn: opts.dsn ?? DSN }),
    JSON.stringify({ type: opts.type ?? "event", length: payload.length }),
    payload,
  ].join("\n") + "\n";
}

describe("parseDsn", () => {
  it("reads origin, project and key, and refuses anything else", () => {
    expect(allowed).toEqual({ origin: "http://glitchtip.example.invalid:8140", projectId: "1", key: "abc123" });
    expect(envelopeUrl(allowed)).toBe("http://glitchtip.example.invalid:8140/api/1/envelope/?sentry_key=abc123");
    expect(parseDsn("")).toBeNull();
    expect(parseDsn("not a url")).toBeNull();
    expect(parseDsn("http://glitchtip.example.invalid/1")).toBeNull();
  });
});

describe("filterEnvelope", () => {
  it("forwards an error event with the search term redacted and the stale length dropped", () => {
    const out = filterEnvelope(envelope(), allowed);
    expect(out.ok).toBe(true);
    if (!out.ok) return;
    expect(out.body).toContain("q=%5Bredacted%5D");
    expect(out.body).not.toContain("jane");
    expect(out.body).toContain("limit=5");
    expect(JSON.parse(out.body.split("\n")[1])).toEqual({ type: "event" });
  });

  it("rejects an envelope for another project or key (not an open relay)", () => {
    expect(filterEnvelope(envelope({ dsn: "http://abc123@glitchtip.example.invalid:8140/2" }), allowed)).toMatchObject({ ok: false, status: 403 });
    expect(filterEnvelope(envelope({ dsn: "http://other@glitchtip.example.invalid:8140/1" }), allowed)).toMatchObject({ ok: false, status: 403 });
    expect(filterEnvelope(envelope({ dsn: "" }), allowed)).toMatchObject({ ok: false, status: 403 });
  });

  it("forwards only error events, nothing else", () => {
    for (const type of ["transaction", "attachment", "session", "replay_event"]) {
      expect(filterEnvelope(envelope({ type }), allowed)).toMatchObject({ ok: false, status: 400 });
    }
  });

  it("refuses garbage and an oversized body", () => {
    expect(filterEnvelope("not json", allowed)).toMatchObject({ ok: false, status: 400 });
    expect(filterEnvelope(JSON.stringify({ dsn: DSN }) + "\n", allowed)).toMatchObject({ ok: false, status: 400 });
    expect(filterEnvelope("x".repeat(MAX_ENVELOPE_BYTES + 1), allowed)).toMatchObject({ ok: false, status: 413 });
  });
});

describe("the tunnel route", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  const post = (body: string) => POST(new Request("https://crm.example.invalid/api/glitchtip-tunnel", { method: "POST", body }));

  it("does nothing when error reporting is not configured", async () => {
    vi.stubEnv("GLITCHTIP_DSN", "");
    expect((await post(envelope())).status).toBe(204);
  });

  it("forwards a scrubbed event to the stub GlitchTip, with q redacted", async () => {
    vi.stubEnv("GLITCHTIP_DSN", DSN);
    const seen: { url: string; body: string }[] = [];
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      seen.push({ url, body: String(init.body) });
      return new Response(null, { status: 200 });
    });
    const res = await post(envelope());
    expect(res.status).toBe(200);
    expect(seen).toHaveLength(1);
    expect(seen[0].url).toBe("http://glitchtip.example.invalid:8140/api/1/envelope/?sentry_key=abc123");
    expect(seen[0].body).not.toContain("jane");
  });

  it("rejects an envelope for another project without calling GlitchTip", async () => {
    vi.stubEnv("GLITCHTIP_DSN", DSN);
    const fetched = vi.fn();
    vi.stubGlobal("fetch", fetched);
    const res = await post(envelope({ dsn: "http://abc123@glitchtip.example.invalid:8140/9" }));
    expect(res.status).toBe(403);
    expect(fetched).not.toHaveBeenCalled();
  });

  it("answers 502 when GlitchTip cannot be reached", async () => {
    vi.stubEnv("GLITCHTIP_DSN", DSN);
    vi.stubGlobal("fetch", async () => {
      throw new Error("down");
    });
    expect((await post(envelope())).status).toBe(502);
  });
});

describe("backend failure reports", () => {
  it("name the route with ids made :id and no query, so no client name or search term can be in it", () => {
    expect(routeName("/client-viewer/matter/636/parties?q=jane%20example")).toBe("/client-viewer/matter/:id/parties");
    expect(routeName("/client-viewer/search")).toBe("/client-viewer/search");
  });

  it("report only a 5xx, and only when error reporting is on", async () => {
    vi.stubEnv("GLITCHTIP_DSN", "");
    expect(() => reportBackendFailure("/x", 503)).not.toThrow();
    vi.unstubAllEnvs();
  });
});

describe("a failing hub call in a proxy route", () => {
  it("is reported with the route name and status through the one shared helper", async () => {
    const seen: unknown[] = [];
    vi.doMock("@sentry/nextjs", () => ({ captureMessage: (message: string, options: unknown) => seen.push([message, options]) }));
    vi.stubEnv("GLITCHTIP_DSN", DSN);
    vi.resetModules();
    const { reportBackendFailure: report } = await import("./backendFailure");
    report("/client-viewer/matter/636/parties?q=jane", 502);
    report("/client-viewer/matter/636/parties", 404);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(seen).toEqual([["Backend failure 502 on /client-viewer/matter/:id/parties", { level: "error", tags: { route: "/client-viewer/matter/:id/parties", status: "502" } }]]);
    vi.unstubAllEnvs();
    vi.doUnmock("@sentry/nextjs");
  });

  it("is reported at most once per route per minute, so a hub restart is not a flood", async () => {
    const seen: [string, { tags: Record<string, string> }][] = [];
    vi.doMock("@sentry/nextjs", () => ({ captureMessage: (message: string, options: { tags: Record<string, string> }) => seen.push([message, options]) }));
    vi.stubEnv("GLITCHTIP_DSN", DSN);
    vi.resetModules();
    const { reportBackendFailure: report, REPORT_WINDOW_MS } = await import("./backendFailure");
    const t0 = 1_000_000;
    for (let i = 0; i < 50; i += 1) report(`/client-viewer/matter/${i}/parties`, 503, t0 + i);
    report("/client-viewer/search?q=jane", 502, t0);
    report("/client-viewer/matter/7/parties", 503, t0 + REPORT_WINDOW_MS - 1);
    report("/client-viewer/matter/7/parties", 502, t0 + REPORT_WINDOW_MS);
    await vi.waitFor(() => expect(seen).toHaveLength(3), { timeout: 5000 });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(seen.map(([message]) => message)).toEqual([
      "Backend failure 503 on /client-viewer/matter/:id/parties",
      "Backend failure 502 on /client-viewer/search",
      "Backend failure 502 on /client-viewer/matter/:id/parties",
    ]);
    expect(seen[0][1].tags.suppressed).toBeUndefined();
    expect(seen[2][1].tags.suppressed).toBe("50");
    vi.unstubAllEnvs();
    vi.doUnmock("@sentry/nextjs");
  });
});

describe("the tunnel route's safeguards", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("refuses a cross-site write without calling GlitchTip", async () => {
    vi.stubEnv("GLITCHTIP_DSN", DSN);
    const fetched = vi.fn();
    vi.stubGlobal("fetch", fetched);
    const url = "https://crm.example.invalid/api/glitchtip-tunnel";
    const bySite = await POST(new Request(url, { method: "POST", body: envelope(), headers: { "sec-fetch-site": "cross-site" } }));
    const byOrigin = await POST(new Request(url, { method: "POST", body: envelope(), headers: { origin: "https://evil.example.invalid", host: "crm.example.invalid" } }));
    expect(bySite.status).toBe(403);
    expect(byOrigin.status).toBe(403);
    expect(fetched).not.toHaveBeenCalled();
  });

  it("forwards only to the configured origin, whatever host the envelope's own DSN names", async () => {
    vi.stubEnv("GLITCHTIP_DSN", DSN);
    const urls: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      urls.push(url);
      return new Response(null, { status: 200 });
    });
    const res = await POST(
      new Request("https://crm.example.invalid/api/glitchtip-tunnel", { method: "POST", body: envelope({ dsn: "http://abc123@attacker.example.invalid:9999/1" }) }),
    );
    expect(res.status).toBe(200);
    expect(urls).toEqual(["http://glitchtip.example.invalid:8140/api/1/envelope/?sentry_key=abc123"]);
  });

  it("never puts the DSN or its key in a response or the log", async () => {
    vi.stubEnv("GLITCHTIP_DSN", DSN);
    vi.stubGlobal("fetch", async () => {
      throw new Error(`connect failed to ${DSN}`);
    });
    const logged: string[] = [];
    const spies = (["log", "info", "warn", "error"] as const).map((level) =>
      vi.spyOn(console, level).mockImplementation((...args: unknown[]) => void logged.push(args.map(String).join(" "))),
    );
    const post = (body: string) => POST(new Request("https://crm.example.invalid/api/glitchtip-tunnel", { method: "POST", body }));
    const responses = [await post(envelope()), await post(envelope({ dsn: "http://other@glitchtip.example.invalid:8140/1" })), await post("not json")];
    const text = (await Promise.all(responses.map((r) => r.text()))).join(" ") + logged.join(" ");
    spies.forEach((spy) => spy.mockRestore());
    expect(text).not.toContain("abc123");
    expect(text).not.toContain("glitchtip.example.invalid");
  });
});
