import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { NOTHING, cachedAnswer, forgetAnswers, rememberAnswer, resultFor, startLazyFetch, type LazyResult } from "./useLazyFetch";

function reply(status: number, body: unknown): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

async function settle<T>(fetcher: (url: string) => Promise<Response>, cancelFirst = false): Promise<LazyResult<T>[]> {
  const seen: LazyResult<T>[] = [];
  const cancel = startLazyFetch<T>("/api/clients/x?matter_id=9001", (r) => seen.push(r), fetcher);
  if (cancelFirst) cancel();
  await new Promise((resolve) => setTimeout(resolve, 0));
  return seen;
}

describe("startLazyFetch", () => {
  it("hands over the JSON of a good reply once", async () => {
    expect(await settle(() => reply(200, { count: 2 }))).toEqual([{ data: { count: 2 }, failed: false }]);
  });

  it("reads a non-2xx reply or a network failure as failed, with no data", async () => {
    expect(await settle(() => reply(502, { detail: "down" }))).toEqual([{ data: null, failed: true }]);
    expect(await settle(() => Promise.reject(new TypeError("offline")))).toEqual([{ data: null, failed: true }]);
  });

  it("drops a reply that lands after it was cancelled (the client changed)", async () => {
    expect(await settle(() => reply(200, { count: 2 }), true)).toEqual([]);
    expect(await settle(() => reply(500, {}), true)).toEqual([]);
  });

  it("asks for exactly the URL it was given", async () => {
    const asked: string[] = [];
    await settle((url) => {
      asked.push(url);
      return reply(200, {});
    });
    expect(asked).toEqual(["/api/clients/x?matter_id=9001"]);
  });
});

describe("resultFor", () => {
  const stored = { url: "/a?matter_id=1", data: { n: 1 }, failed: false };

  it("shows the answer only for the URL it answers", () => {
    expect(resultFor(stored, "/a?matter_id=1")).toEqual({ data: { n: 1 }, failed: false });
    expect(resultFor(stored, "/a?matter_id=2")).toBe(NOTHING);
    expect(resultFor(stored, null)).toBe(NOTHING);
  });

  it("carries a failure for its own URL", () => {
    expect(resultFor({ url: "/a", data: null, failed: true }, "/a")).toEqual({ data: null, failed: true });
  });
});

describe("the Details tab's lazy reads", () => {
  const panel = readFileSync(fileURLToPath(new URL("../components/DetailPanel.tsx", import.meta.url)), "utf8");

  it("go through the one hook, with no hand-rolled cancel flag left", () => {
    for (const route of ["sos-status", "bill-of-costs", "matter-flags", "person-matters"]) {
      expect(panel).toMatch(new RegExp(`useLazyFetch<[^>]+>\\(\\s*\\w+ \\? \`/api/clients/${route}\\?`));
    }
    const handRolled = panel.match(/let cancelled = false/g) ?? [];
    expect(handRolled.length).toBe(1);
  });
});

describe("the kept answers (cacheMs)", () => {
  it("gives back a good answer until it is as old as the limit, then forgets it", () => {
    forgetAnswers();
    rememberAnswer("/a?matter_id=1", { n: 1 }, 1_000);
    expect(cachedAnswer("/a?matter_id=1", 60_000, 1_000 + 59_999)).toEqual({ n: 1 });
    expect(cachedAnswer("/a?matter_id=2", 60_000, 1_000)).toBeUndefined();
    expect(cachedAnswer("/a?matter_id=1", 60_000, 1_000 + 60_000)).toBeUndefined();
    expect(cachedAnswer("/a?matter_id=1", 60_000, 1_000)).toBeUndefined();
  });

  it("keeps no answer for null", () => {
    forgetAnswers();
    rememberAnswer("/a", { n: 1 }, 0);
    rememberAnswer("/a", null, 0);
    expect(cachedAnswer("/a", 60_000, 0)).toBeUndefined();
  });

  const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

  it("is used by the three live Graph reads, each loaded only where it is shown", () => {
    for (const [file, route] of [
      ["../components/DetailPanel.tsx", "sos-status"],
      ["../components/MatterMarkers.tsx", "matter-markers"],
      ["../components/MatterTasks.tsx", "matter-tasks"],
    ]) {
      expect(read(file)).toMatch(
        new RegExp(`useLazyFetch<[^>]+>\\(\\s*\\w+ \\? \`/api/clients/${route}\\?[^\`]*\` : null,\\s*\\{ cacheMs: GRAPH_READ_CACHE_MS \\}`),
      );
    }

    const panel = read("../components/DetailPanel.tsx");
    const details = panel.slice(panel.indexOf('{detailTab === "details" && ('));
    expect(details.indexOf("<SosStatusField")).toBeGreaterThan(0);
    expect(details.indexOf("<MatterMarkers")).toBeGreaterThan(0);
    expect(panel.match(/<SosStatusField|<MatterMarkers /g)?.length).toBe(2);
  });
});
