
import { afterEach, describe, expect, it, vi } from "vitest";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { GET } from "./route";

vi.mock("@/lib/accessIdentity", () => ({
  resolveIdentityForRoute: vi.fn(async () => ({ remoteUser: null, rejection: null })),
}));

vi.mock("@/lib/firm", () => ({ FIRM: { short_name: "Firm", workers: ["Alex", "Sam"], hostnames: {} } }));

function req(): Request {
  return new Request("http://localhost/api/me");
}

afterEach(() => {
  vi.mocked(resolveIdentityForRoute).mockReset();
  vi.mocked(resolveIdentityForRoute).mockImplementation(async () => ({ remoteUser: null, rejection: null }));
});

describe("GET /api/me", () => {
  it("names the signed-in worker", async () => {
    vi.mocked(resolveIdentityForRoute).mockResolvedValueOnce({ remoteUser: "alex.smith@example.test", rejection: null });
    const res = await GET(req());
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ name: "Alex", signed_in: true });
    expect(res.headers.get("Cache-Control")).toBe("no-store");
  });

  it("is the email for a signed-in person who is not a worker", async () => {
    vi.mocked(resolveIdentityForRoute).mockResolvedValueOnce({ remoteUser: "office@example.test", rejection: null });
    expect(await (await GET(req())).json()).toEqual({ name: "office@example.test", signed_in: true });
  });

  it("is tailnet, not signed in, with no Access identity", async () => {
    expect(await (await GET(req())).json()).toEqual({ name: "tailnet", signed_in: false });
  });

  it("passes an identity rejection straight back", async () => {
    vi.mocked(resolveIdentityForRoute).mockResolvedValueOnce({
      remoteUser: null,
      rejection: Response.json({ error: "identity verification failed" }, { status: 403 }),
    });
    const res = await GET(req());
    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({ error: "identity verification failed" });
  });
});
