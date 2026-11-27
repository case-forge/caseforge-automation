import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));
vi.mock("@/lib/hubProxy", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/hubProxy")>()), isStubMode: () => true }));

import { resetStubSpecialSenders } from "@/lib/stubSpecialSenders";
import { GET, PUT } from "./route";
import { DELETE, GET as GET_LOGO, POST } from "../special-sender-logo/route";

const put = (body: unknown, admin = true) =>
  new NextRequest("http://localhost/api/settings/special-senders", {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...(admin ? {} : { Cookie: "caseforge_stub_models_admin=0" }) },
    body: JSON.stringify(body),
  });

beforeEach(() => resetStubSpecialSenders());
afterEach(() => vi.unstubAllGlobals());

describe("Settings > Special senders routes (stub mode)", () => {
  it("lets anyone read the list", async () => {
    const res = await GET(new NextRequest("http://localhost/api/settings/special-senders"));
    expect(res.status).toBe(200);
    expect((await res.json()).items.length).toBeGreaterThan(0);
  });

  it("saves a changed list for an administrator and keeps a sender's logo while its id is kept", async () => {
    const before = (await (await GET(new NextRequest("http://localhost/api/settings/special-senders"))).json()).items[0];
    const res = await PUT(put({ senders: [{ id: before.id, name: "Renamed", domains: ["a.example"], new_clients: false }, { name: "Brand new", domains: [], new_clients: true }] }));
    expect(res.status).toBe(200);
    const items = (await res.json()).items;
    expect(items.map((i: { name: string }) => i.name)).toEqual(["Renamed", "Brand new"]);
    expect(items[0].logo).toBe(before.logo);
    expect(items[1].id).toMatch(/^ss_/);
  });

  it("refuses a non-administrator, a sender with nothing to recognise it by, and a malformed body", async () => {
    expect((await PUT(put({ senders: [] }, false))).status).toBe(403);
    const none = await PUT(put({ senders: [{ name: "Nothing", domains: [], new_clients: false }] }));
    expect(none.status).toBe(422);
    expect((await none.json()).error).toContain("needs a domain");
    expect((await PUT(put({ senders: "nope" }))).status).toBe(400);
  });
});

describe("Settings > Special senders logo route (stub mode)", () => {
  const at = (id: string, method = "GET", body?: BodyInit) =>
    new NextRequest(`http://localhost/api/settings/special-sender-logo?id=${id}`, { method, body });

  it("serves a picture with headers that stop it being treated as anything else, and 404s a sender with none", async () => {
    const res = await GET_LOGO(at("ss_demo1"));
    expect(res.status).toBe(200);
    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
    expect(res.headers.get("content-type")).toBe("image/svg+xml");
    expect((await GET_LOGO(at("ss_demo2"))).status).toBe(404);
  });

  it("only ever takes a sender id, never a path", async () => {
    expect((await GET_LOGO(at("../../etc/passwd"))).status).toBe(404);
    expect((await GET_LOGO(at("a/b"))).status).toBe(404);
  });

  it("adds and removes a logo, and refuses an empty file", async () => {
    expect((await POST(at("ss_demo2", "POST", new Uint8Array([1, 2, 3])))).status).toBe(200);
    expect((await GET_LOGO(at("ss_demo2"))).status).toBe(200);
    expect((await DELETE(at("ss_demo2", "DELETE"))).status).toBe(200);
    expect((await GET_LOGO(at("ss_demo2"))).status).toBe(404);
    expect((await POST(at("ss_demo2", "POST", new Uint8Array([])))).status).toBe(400);
    expect((await POST(at("ss_unknown", "POST", new Uint8Array([1])))).status).toBe(404);
  });
});

describe("a made logo (stub mode)", () => {
  const mark = { text: "ab", colours: ["#f0b400", "#ffffff"], background: "#1c7ed6" };

  it("is kept, upper-cased, and drops the uploaded picture", async () => {
    const before = (await (await GET(new NextRequest("http://localhost/api/settings/special-senders"))).json()).items[0];
    expect(before.logo).not.toBe("");
    const res = await PUT(put({ senders: [{ id: before.id, name: before.name, domains: before.domains, new_clients: false, mark }] }));
    expect(res.status).toBe(200);
    const saved = (await res.json()).items[0];
    expect(saved.mark).toEqual({ ...mark, text: "AB" });
    expect(saved.logo).toBe("");
  });

  it("is refused when it is not letters with colours", async () => {
    const res = await PUT(put({ senders: [{ name: "X", domains: [], new_clients: true, mark: { text: "TOOLONG", colours: [], background: "#fff" } }] }));
    expect(res.status).toBe(422);
  });
});
