import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";
import { GET } from "../route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

const post = (body: unknown, headers: Record<string, string> = {}) =>
  new NextRequest("http://localhost/api/audit-folders/flag", { method: "POST", headers: { "content-type": "application/json", ...headers }, body: typeof body === "string" ? body : JSON.stringify(body) });

describe("POST /api/audit-folders/flag", () => {
  it("flags and unflags in the stub, and the next read shows it on the item and counts it for the client", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await POST(post({ client: "Sample Client", path: "Orders/26.11.16 Email from landlord.pdf", flagged: true }))).status).toBe(200);
    const read = await (await GET(new NextRequest("http://localhost/api/audit-folders?folder=Sample%20Client"))).json();
    const mine = read.folder.items.filter((i: { flags: { person?: unknown } }) => i.flags.person);
    expect(mine.map((i: { path: string }) => i.path)).toEqual(["Orders/26.11.16 Email from landlord.pdf"]);
    expect(read.folder.summary.flags_by_kind).toEqual({ person: 1, agent: 2, automation: 2 });
    expect(read.clients.find((c: { name: string }) => c.name === "Sample Client").flagged).toBe(3);
    await POST(post({ client: "Sample Client", path: "Orders/26.11.16 Email from landlord.pdf", flagged: false }));
    const after = await (await GET(new NextRequest("http://localhost/api/audit-folders?folder=Sample%20Client"))).json();
    expect(after.folder.summary.flags_by_kind.person).toBe(0);
    expect(after.folder.summary.flags_by_kind.agent).toBe(2);
  });

  it("refuses a cross-site write, a bad body and a missing field before anything is sent", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await POST(post({ client: "c", path: "p", flagged: true }, { "sec-fetch-site": "cross-site" }))).status).toBe(403);
    expect((await POST(post("not json"))).status).toBe(400);
    expect((await POST(post({ client: "c", flagged: true }))).status).toBe(400);
    expect((await POST(post({ client: "c", path: "p", flagged: "yes" }))).status).toBe(400);
  });

  it("forwards only client, path, type and flagged to the hub, never a person, and passes a 403 through", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ flagged: true }))).mockResolvedValueOnce(new Response("{}", { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);
    const ok = await POST(post({ client: "Client One", path: "a/b.pdf", type: "folder", flagged: true, by: "someone-else", evil: 1 }));
    expect(ok.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/audit-folders/flag");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ client: "Client One", path: "a/b.pdf", type: "folder", flagged: true });
    expect((await POST(post({ client: "c", path: "p", flagged: false }))).status).toBe(403);
  });
});
