import { afterEach, describe, expect, it, vi } from "vitest";
import { CONCLUDED_PAGE, appendUnique, loadConcludedPage } from "./flagLists";
import { stubConcludedMatters } from "./stub";
import type { ClientMatch } from "./types";

const m = (id: string) => ({ matter_id: id }) as unknown as ClientMatch;

afterEach(() => vi.unstubAllGlobals());

describe("appendUnique", () => {
  it("adds a page and drops a client already listed", () => {
    expect(appendUnique([m("1"), m("2")], [m("2"), m("3")]).map((x) => String(x.matter_id))).toEqual(["1", "2", "3"]);
  });
});

describe("stubConcludedMatters", () => {
  it("serves 50 at a time and ends with no next page", () => {
    const first = stubConcludedMatters(0, 50);
    expect(first.results).toHaveLength(50);
    expect(first.total).toBe(120);
    expect(first.next_offset).toBe(50);
    const last = stubConcludedMatters(100, 50);
    expect(last.results).toHaveLength(20);
    expect(last.next_offset).toBeNull();
  });
});

describe("loadConcludedPage", () => {
  it("asks for a page of 50 at the offset and returns the next offset", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ results: [m("9")], total: 61, next_offset: 50 })));
    vi.stubGlobal("fetch", fetchMock);
    const page = await loadConcludedPage(0);
    expect(String(fetchMock.mock.calls[0][0])).toBe(`/api/clients/concluded-matters?limit=${CONCLUDED_PAGE}&offset=0`);
    expect(page).toEqual({ results: [m("9")], total: 61, nextOffset: 50 });
  });

  it("throws on a failed request, so the page can stop paging", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("x", { status: 502 })));
    await expect(loadConcludedPage(50)).rejects.toThrow();
  });
});
