import { describe, expect, it, vi } from "vitest";
import { ARROW_LABELS, fetchMatterByNumber, fetchNeighbour, keyDirection, neighbourIn } from "./matterNeighbour";

describe("neighbourIn", () => {
  const ids = ["3", "5", "6", "9", "10", "x"];
  it("steps by number, over gaps, either way", () => {
    expect(neighbourIn(ids, "6", "prev")).toBe("5");
    expect(neighbourIn(ids, "6", "next")).toBe("9");
    expect(neighbourIn(ids, "7", "prev")).toBe("6");
  });
  it("answers null at either end", () => {
    expect(neighbourIn(ids, "3", "prev")).toBeNull();
    expect(neighbourIn(ids, "10", "next")).toBeNull();
  });
});

describe("the arrow labels", () => {
  it("say number, never client, so nobody reads them as the client before", () => {
    expect(ARROW_LABELS.prev.title).toBe("Previous number");
    expect(ARROW_LABELS.next.title).toBe("Next number");
    for (const label of Object.values(ARROW_LABELS)) expect(JSON.stringify(label)).not.toMatch(/client/i);
  });
});

describe("keyDirection", () => {
  it("maps [ and ] with no modifier", () => {
    expect(keyDirection({ key: "[" })).toBe("prev");
    expect(keyDirection({ key: "]" })).toBe("next");
    expect(keyDirection({ key: "ArrowLeft" })).toBeNull();
    expect(keyDirection({ key: "[", ctrlKey: true })).toBeNull();
    expect(keyDirection({ key: "]", altKey: true })).toBeNull();
  });
  it("ignores keys typed into a box", () => {
    const input = { tagName: "INPUT" } as unknown as EventTarget;
    const editable = { tagName: "DIV", isContentEditable: true } as unknown as EventTarget;
    expect(keyDirection({ key: "[", target: input })).toBeNull();
    expect(keyDirection({ key: "]", target: editable })).toBeNull();
    expect(keyDirection({ key: "]", target: { tagName: "BUTTON" } as unknown as EventTarget })).toBe("next");
  });
});

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("fetchNeighbour", () => {
  it("asks for the neighbour, then opens its row from the person-matters read", async () => {
    const fetcher = vi.fn(async (url: string) =>
      url.startsWith("/api/clients/matter-neighbour")
        ? json({ matter_id: "512" })
        : json({ matter_id: "512", matters: [{ matter_id: "511" }, { matter_id: "512", client_name: "Placeholder Person" }] }),
    );
    const result = await fetchNeighbour("510", "next", fetcher);
    expect(fetcher.mock.calls[0][0]).toBe("/api/clients/matter-neighbour?matter_id=510&dir=next");
    expect(fetcher.mock.calls[1][0]).toBe("/api/clients/person-matters?matter_id=512");
    expect(result).toEqual({ kind: "found", match: { matter_id: "512", client_name: "Placeholder Person" } });
  });

  it("reports the end when there is no neighbour, without a second read", async () => {
    const fetcher = vi.fn(async () => json({ matter_id: null }));
    expect(await fetchNeighbour("3", "prev", fetcher)).toEqual({ kind: "end" });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("reports an error the hub gives, or a row it cannot find", async () => {
    expect(await fetchNeighbour("3", "prev", async () => json({ error: "Next matter number unavailable" }, 502))).toEqual({
      kind: "error",
      message: "Next matter number unavailable",
    });
    const missing = vi.fn(async (url: string) => (url.includes("neighbour") ? json({ matter_id: "8" }) : json({ matters: [] })));
    expect(await fetchNeighbour("7", "next", missing)).toEqual({ kind: "error", message: "Could not open matter 8" });
    expect(await fetchNeighbour("7", "next", async () => Promise.reject(new Error("offline")))).toEqual({
      kind: "error",
      message: "Could not find the next number",
    });
  });
});

describe("fetchMatterByNumber", () => {
  const reply = (body: unknown, ok = true) => vi.fn(async () => ({ ok, json: async () => body }) as Response);
  it("opens the row whose matter id is exactly the typed number", async () => {
    const row = { matter_id: "512" };
    const result = await fetchMatterByNumber(" 512 ", reply({ matters: [{ matter_id: "5120" }, row] }));
    expect(result).toEqual({ kind: "found", match: row });
  });
  it("says so when no client has that number, or the text is not a number", async () => {
    expect((await fetchMatterByNumber("999", reply({ matters: [] }))).kind).toBe("error");
    expect(await fetchMatterByNumber("abc", reply({}))).toEqual({ kind: "error", message: "Type a client number" });
  });
});
