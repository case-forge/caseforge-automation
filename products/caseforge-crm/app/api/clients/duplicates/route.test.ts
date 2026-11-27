import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));
vi.mock("@/lib/hubProxy", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/hubProxy")>()), isStubMode: () => true }));

afterEach(() => vi.unstubAllGlobals());

describe("GET /api/clients/duplicates", () => {
  it("returns made-up pairs in stub mode and never reaches the hub", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { GET } = await import("./route");
    const res = await GET(new Request("http://localhost/api/clients/duplicates") as never);
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body.items.length).toBeGreaterThan(0);
    expect(body.items[0]).toMatchObject({ reason: expect.any(String), a: { matter_id: expect.any(String) }, b: { client_name: expect.any(String) } });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
