import { describe, expect, it, vi } from "vitest";
import { loadFolderMap, localProblems, nameKey, previewFolderMap, resetFolderMap, saveFolderMap } from "./folderMap";

const row = (name: string, per_order = false) => ({ name, per_order });

describe("local checks", () => {
  it("accepts a good list", () => {
    expect(localProblems([row("Lexcel-Docs"), row("Client's-Docs"), row("Notes", true)])).toEqual({});
  });
  it("flags empty, forbidden, dotted, long and duplicate names by row", () => {
    const found = localProblems([row(""), row("a/b"), row("..x"), row("x".repeat(61)), row("Docs"), row("d o c s"), row("a{b}")]);
    expect(Object.keys(found).map(Number)).toEqual([0, 1, 2, 3, 5, 6]);
    expect(found[5]).toMatch(/row 5/);
  });
  it("needs at least one folder", () => {
    expect(localProblems([])[-1]).toMatch(/at least one/);
  });
  it("reads two spellings as one folder", () => {
    expect(nameKey("Client's-Docs")).toBe(nameKey("clients docs"));
  });
});

describe("the calls", () => {
  it("treats a failed or odd load as an error", async () => {
    expect(await loadFolderMap(vi.fn().mockResolvedValue(new Response("{}", { status: 500 })))).toEqual({ state: "error" });
    expect(await loadFolderMap(vi.fn().mockResolvedValue(new Response("{}")))).toEqual({ state: "error" });
  });
  it("sends the list and returns the hub's words on a refusal", async () => {
    const ok = vi.fn().mockResolvedValue(new Response("{}"));
    expect((await saveFolderMap([row("A")], ok)).ok).toBe(true);
    expect(ok.mock.calls[0][1].method).toBe("PUT");
    expect(JSON.parse(ok.mock.calls[0][1].body)).toEqual({ entries: [row("A")] });
    const refused = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ error: "Plain words" }), { status: 422 }));
    expect(await saveFolderMap([row("A")], refused)).toEqual({ ok: false, message: "Plain words" });
    expect(await previewFolderMap([row("A")], refused)).toEqual({ ok: false, message: "Plain words" });
    const reset = vi.fn().mockResolvedValue(new Response("{}"));
    await resetFolderMap(reset);
    expect(reset.mock.calls[0][1].method).toBe("DELETE");
  });
});
