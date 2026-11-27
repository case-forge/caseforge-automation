
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearTailnetWhoisCache } from "@/lib/hubProxy";
import { resolveCrmRole, tailnetOnly } from "@/lib/crmRole";
import { HUB_STUB_ENV, HUB_TOKEN_ENV, HUB_URL_ENV } from "@/lib/hubProxy";
import { ACCESS_AUD_ENV, ACCESS_TEAM_DOMAIN_ENV } from "@/lib/accessIdentity";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn().mockRejectedValue(new Error("bad")) }));
vi.mock("node:child_process", () => ({
  execFile: (_cmd: string, _args: string[], _opts: unknown, cb: (err: Error | null, stdout: string) => void) =>
    cb(null, JSON.stringify({ Node: { ComputedName: "laptop" }, UserProfile: { LoginName: "owner@example.test" } })),
}));

const TAILNET_IP = "100.64.0.7";

beforeEach(() => {
  vi.stubEnv(HUB_URL_ENV, "http://hub.internal:8770");
  vi.stubEnv(HUB_TOKEN_ENV, "test-token-not-a-real-secret");
  vi.stubEnv(HUB_STUB_ENV, "");
  vi.stubEnv(ACCESS_TEAM_DOMAIN_ENV, "team.example.cloudflareaccess.com");
  vi.stubEnv(ACCESS_AUD_ENV, "aud-example");
  clearTailnetWhoisCache();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

const request = (headers: Record<string, string>) => new Request("http://100.64.0.1:3010/api/me/role", { headers });

describe("the tailnet path is the developer", () => {
  it("asks the hub with the tailnet identity and takes its dev answer", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ role: "dev" })));
    vi.stubGlobal("fetch", fetchMock);
    expect((await resolveCrmRole(request({ "x-forwarded-for": TAILNET_IP }))).role).toBe("dev");
    const sent = fetchMock.mock.calls[0][1].headers as Record<string, string>;
    expect(JSON.parse(sent["X-CaseForge-Tailnet-Identity"])).toMatchObject({ login: "owner@example.test", ip: TAILNET_IP });
    expect(sent["Remote-User"]).toBeUndefined();
  });

  it("is a worker when the hub says so (a tagged node, an unknown device)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ role: "worker" }))));
    expect((await resolveCrmRole(request({ "x-forwarded-for": TAILNET_IP }))).role).toBe("worker");
  });
});

describe("the Cloudflare path never falls into the tailnet branch", () => {
  it.each([
    ["Cf-Ray", { "cf-ray": "8f00-LHR" }],
    ["Cf-Connecting-Ip", { "cf-connecting-ip": "203.0.113.7" }],
    ["Cf-Ipcountry", { "cf-ipcountry": "GB" }],
    ["Cf-Visitor", { "cf-visitor": '{"scheme":"https"}' }],
  ])("a request carrying %s is a worker or refused, and the hub is never asked", async (_name, cf) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ role: "dev" })));
    vi.stubGlobal("fetch", fetchMock);
    const outcome = await resolveCrmRole(request({ "x-forwarded-for": TAILNET_IP, ...cf }));
    expect(outcome.role).toBe("worker");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("an Access token that does not verify is refused, never the tailnet developer", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const outcome = await resolveCrmRole(request({ "x-forwarded-for": TAILNET_IP, "cf-access-jwt-assertion": "forged" }));
    expect(outcome.role).toBe("worker");
    expect(outcome.rejection?.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ["no forwarded address", {}],
    ["a public address", { "x-forwarded-for": "203.0.113.7" }],
    ["a forwarded list (a client-supplied value Cloudflare appended to)", { "x-forwarded-for": `${TAILNET_IP}, 203.0.113.7` }],
  ])("%s is a worker without asking the hub", async (_name, headers) => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect((await resolveCrmRole(request(headers))).role).toBe("worker");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("tailnetOnly needs a single tailnet address and no Cloudflare header", () => {
    expect(tailnetOnly(request({ "x-forwarded-for": TAILNET_IP }))).toBe(true);
    expect(tailnetOnly(request({ "x-forwarded-for": TAILNET_IP, "cf-ray": "x" }))).toBe(false);
    expect(tailnetOnly(request({ "x-forwarded-for": "10.0.0.1" }))).toBe(false);
  });
});
