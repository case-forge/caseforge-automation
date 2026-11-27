import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { fetchMatterFlagsBatch, flagsReady, invalidateMatterFlags, knownMatterFlags } from "./matterFlagsFetch";
import { mergeFlags } from "../components/ResultsList";

function reply(flags: Record<string, Record<string, boolean>>) {
  return Promise.resolve(new Response(JSON.stringify({ flags_by_matter: flags }), { status: 200 }));
}

describe("fetchMatterFlagsBatch", () => {
  beforeEach(() => {
    invalidateMatterFlags();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shares one request between simultaneous callers", async () => {
    const fetchMock = vi.fn(() => reply({ "1": { flagged: true } }));
    vi.stubGlobal("fetch", fetchMock);
    const [a, b] = await Promise.all([fetchMatterFlagsBatch(["1"]), fetchMatterFlagsBatch(["1"])]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(a).toEqual(b);
  });

  it("reads afresh after invalidation", async () => {
    const fetchMock = vi.fn(() => reply({}));
    vi.stubGlobal("fetch", fetchMock);
    await fetchMatterFlagsBatch(["1"]);
    invalidateMatterFlags();
    await fetchMatterFlagsBatch(["1"]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("tries a failed read once more, so one hiccup does not leave the first results without their pills", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => Promise.reject(new Error("down")))
      .mockImplementationOnce(() => reply({ "1": { persistent_caller: true } }));
    vi.stubGlobal("fetch", fetchMock);
    expect(await fetchMatterFlagsBatch(["1"])).toEqual({ "1": { persistent_caller: true } });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not keep a failure that happened twice", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => Promise.reject(new Error("down")))
      .mockImplementationOnce(() => Promise.resolve(new Response("{}", { status: 502 })))
      .mockImplementationOnce(() => reply({ "1": { flagged: true } }));
    vi.stubGlobal("fetch", fetchMock);
    expect(await fetchMatterFlagsBatch(["1"])).toEqual({});
    expect(await fetchMatterFlagsBatch(["1"])).toEqual({ "1": { flagged: true } });
  });

  it("knows an answered matter's flags at once, for the first render of the next list, until a flag changes", async () => {
    vi.stubGlobal("fetch", vi.fn(() => reply({ "1": { persistent_caller: true }, "2": {} })));
    expect(knownMatterFlags(["1", "2"])).toEqual({});
    await fetchMatterFlagsBatch(["1", "2"]);
    expect(knownMatterFlags(["1", "3"])).toEqual({ "1": { persistent_caller: true } });
    expect(knownMatterFlags(["1"], Date.now() + 60_000)).toEqual({});
    invalidateMatterFlags();
    expect(knownMatterFlags(["1"])).toEqual({});
  });

  it("a search waits for its cards' flags, so the frequent-caller icon is known on the list's first render", async () => {
    vi.stubGlobal("fetch", vi.fn(() => reply({ "7": { persistent_caller: true } })));
    await flagsReady(["7"]);
    expect(knownMatterFlags(["7"])).toEqual({ "7": { persistent_caller: true } });
    const page = readFileSync(fileURLToPath(new URL("../components/Workspace.tsx", import.meta.url)), "utf8");
    expect(page).toMatch(/await flagsReady\([\s\S]*?\);\s*if \(controller\.signal\.aborted\) return;\s*setResults\(body\.results\)/);
    const list = readFileSync(fileURLToPath(new URL("../components/ResultsList.tsx", import.meta.url)), "utf8");
    expect(list).toContain("...knownMatterFlags(matterIds)");
  });

  it("does not hold a search back more than the cap when the flags are slow", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    const started = Date.now();
    await flagsReady(["8"], 50);
    expect(Date.now() - started).toBeLessThan(1000);
  });

  it("merges a late answer into what is held instead of dropping it", () => {
    expect(mergeFlags({ "1": { flagged: true } }, { "2": { persistent_caller: true } })).toEqual({ "1": { flagged: true }, "2": { persistent_caller: true } });
    const held = { "1": { flagged: true } };
    expect(mergeFlags(held, {})).toBe(held);
  });
});
