import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  TAILNET_IDENTITY_HEADER,
  accessJwtHeader,
  clearTailnetWhoisCache,
  hubGetJson,
  clientIp,
  hubIdentityHeaders,
  parseWhois,
  tailnetIdentityHeader,
  tailnetIp,
} from "./hubProxy";

function withJwt(value?: string): Request {
  return new Request("http://localhost/api/x", value ? { headers: { "Cf-Access-Jwt-Assertion": value } } : {});
}

function fromAddress(xff: string): Request {
  return new Request("http://localhost/api/x", { headers: { "x-forwarded-for": xff } });
}

describe("accessJwtHeader", () => {
  it("forwards the request's own Access JWT alongside a verified Remote-User", () => {
    expect(accessJwtHeader(withJwt("header.payload.signature"), "person@example.invalid")).toEqual({
      "Cf-Access-Jwt-Assertion": "header.payload.signature",
    });
  });

  it("forwards nothing without a verified Remote-User (tailnet, scripts)", () => {
    expect(accessJwtHeader(withJwt("header.payload.signature"), null)).toEqual({});
  });

  it("forwards nothing when the request carried no JWT", () => {
    expect(accessJwtHeader(withJwt(), "person@example.invalid")).toEqual({});
  });
});

describe("tailnetIp", () => {
  it("accepts tailnet addresses only", () => {
    expect(tailnetIp("100.101.102.103")).toBe("100.101.102.103");
    expect(tailnetIp("::ffff:100.64.0.1")).toBe("100.64.0.1");
    expect(tailnetIp("fd7a:115c:a1e0::1")).toBe("fd7a:115c:a1e0::1");
    expect(tailnetIp("203.0.113.9")).toBe("");
    expect(tailnetIp("100.128.0.1")).toBe("");
    expect(tailnetIp("100.101.102.103, 203.0.113.9")).toBe("");
    expect(tailnetIp(null)).toBe("");
  });
});

describe("parseWhois", () => {
  it("takes the login and short node name; a tagged node has no login", () => {
    const person = { Node: { ComputedName: "laptop-one", Tags: [] }, UserProfile: { LoginName: "person@example.invalid" } };
    expect(parseWhois(person)).toEqual({ login: "person@example.invalid", node: "laptop-one" });
    const tagged = { Node: { Name: "server.tailnet.ts.net.", Tags: ["tag:server"] }, UserProfile: { LoginName: "tagged-devices" } };
    expect(parseWhois(tagged)).toEqual({ login: "", node: "server" });
  });
});

describe("tailnetIdentityHeader", () => {
  afterEach(() => clearTailnetWhoisCache());

  it("forwards the whois answer for a tailnet caller with no Remote-User", async () => {
    const whois = vi.fn().mockResolvedValue({ login: "person@example.invalid", node: "laptop-one" });
    const header = await tailnetIdentityHeader(fromAddress("100.101.102.103"), null, whois);
    expect(JSON.parse(header[TAILNET_IDENTITY_HEADER])).toEqual({
      login: "person@example.invalid",
      node: "laptop-one",
      ip: "100.101.102.103",
    });
    expect(whois).toHaveBeenCalledWith("100.101.102.103");
  });

  it("caches the whois answer", async () => {
    const whois = vi.fn().mockResolvedValue({ login: "", node: "server" });
    await tailnetIdentityHeader(fromAddress("100.101.102.104"), null, whois);
    await tailnetIdentityHeader(fromAddress("100.101.102.104"), null, whois);
    expect(whois).toHaveBeenCalledTimes(1);
  });

  it("still names the address when whois fails", async () => {
    const whois = vi.fn().mockResolvedValue(null);
    const header = await tailnetIdentityHeader(fromAddress("100.101.102.105"), null, whois);
    expect(JSON.parse(header[TAILNET_IDENTITY_HEADER])).toEqual({ login: "", node: "", ip: "100.101.102.105" });
  });

  it("forwards nothing for a verified person or an address outside the tailnet", async () => {
    const whois = vi.fn();
    expect(await tailnetIdentityHeader(fromAddress("100.101.102.103"), "person@example.invalid", whois)).toEqual({});
    expect(await tailnetIdentityHeader(fromAddress("203.0.113.9"), null, whois)).toEqual({});
    expect(await tailnetIdentityHeader(new Request("http://localhost/api/x"), null, whois)).toEqual({});
    expect(whois).not.toHaveBeenCalled();
  });
});

describe("hubIdentityHeaders", () => {
  it("sends Remote-User and the JWT for a person, and no tailnet identity", async () => {
    const request = new Request("http://localhost/api/x", {
      headers: { "Cf-Access-Jwt-Assertion": "header.payload.signature", "x-forwarded-for": "100.101.102.103" },
    });
    expect(await hubIdentityHeaders(request, "person@example.invalid")).toEqual({
      "X-CaseForge-Client": "client-viewer",
      "X-CaseForge-Client-Ip": "100.101.102.103",
      "Remote-User": "person@example.invalid",
      "Cf-Access-Jwt-Assertion": "header.payload.signature",
    });
  });

  it("passes the person's own address on for the request log: Cloudflare's header first, only a plain address", async () => {
    const request = new Request("http://localhost/api/x", { headers: { "cf-connecting-ip": "203.0.113.9", "x-forwarded-for": "100.101.102.103" } });
    expect((await hubIdentityHeaders(request, "person@example.invalid"))["X-CaseForge-Client-Ip"]).toBe("203.0.113.9");
    const v6 = new Request("http://localhost/api/x", { headers: { "cf-connecting-ip": "2001:db8::1" } });
    expect(clientIp(v6)).toBe("2001:db8::1");
    for (const bad of ["not-an-ip", "192.0.2.4; drop", "", "x".repeat(80)]) {
      expect(clientIp(new Request("http://localhost/api/x", { headers: { "cf-connecting-ip": bad } }))).toBe("");
    }
  });
});

describe("hubGetJson forwarding", () => {
  const saved = { url: process.env.CASEFORGE_HUB_API_URL, token: process.env.CASEFORGE_CHAT_API_TOKEN };
  afterEach(() => {
    vi.unstubAllGlobals();
    for (const [key, value] of [["CASEFORGE_HUB_API_URL", saved.url], ["CASEFORGE_CHAT_API_TOKEN", saved.token]] as const) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    clearTailnetWhoisCache();
  });

  it("forwards the tailnet identity to the hub for a tailnet caller, and nothing otherwise", async () => {
    process.env.CASEFORGE_HUB_API_URL = "http://hub.internal:8771";
    process.env.CASEFORGE_CHAT_API_TOKEN = "t0ken";
    const fetchMock = vi.fn().mockImplementation(async () => Response.json({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await hubGetJson(fromAddress("100.101.102.106"), "/client-viewer/todos", {}, null);
    const sent = fetchMock.mock.calls[0][1].headers as Record<string, string>;
    expect(sent.Authorization).toBe("Bearer t0ken");
    expect(sent["Remote-User"]).toBeUndefined();
    expect(JSON.parse(sent[TAILNET_IDENTITY_HEADER]).ip).toBe("100.101.102.106");

    await hubGetJson(fromAddress("203.0.113.9"), "/client-viewer/todos", {}, null);
    expect(fetchMock.mock.calls[1][1].headers).toEqual({ Authorization: "Bearer t0ken", "X-CaseForge-Client": "client-viewer" });
  });
});

describe("hub call timing", () => {
  beforeEach(() => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.invalid");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "token");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("logs one line and sets Server-Timing on a hub call, with no client data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ ok: true })));
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const { resolveIdentityForRoute } = await import("@/lib/accessIdentity");
    const { hubGetJson } = await import("@/lib/hubProxy");
    const request = new Request("http://crm.invalid/api/clients/98765/notes?name=Jane%20Doe");
    const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
    expect(rejection).toBeNull();
    const response = await hubGetJson(request, "/client-viewer/x", { name: "Jane Doe" }, remoteUser);
    expect(response.status).toBe(200);
    expect(response.headers.get("Server-Timing")).toMatch(/^identity;dur=[\d.]+, hub;dur=[\d.]+, total;dur=[\d.]+$/);
    expect(info).toHaveBeenCalledTimes(1);
    const line = String(info.mock.calls[0][0]);
    expect(line).toMatch(/^\[api-timing\] route=\/api\/clients\/:id\/notes status=200 total_ms=[\d.]+ identity_ms=[\d.]+ hub_ms=[\d.]+$/);
    expect(line).not.toMatch(/Jane|98765/);
  });

});
