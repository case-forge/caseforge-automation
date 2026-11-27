import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPulseSlice, fetchPulse, pulseStore } from "./pulse";
import type { Pulse } from "./pulse";
import type { AttentionResponse } from "./types";

function setPulse(next: Pulse) {
  pulseStore.set(next);
}

describe("createPulseSlice", () => {
  beforeEach(() => setPulse({}));

  it("gives the same object for the same pulse, which React needs", () => {
    const slice = createPulseSlice<{ n: number }>((p) => (p.flag_counts ? { n: p.flag_counts.counts?.flagged ?? 0 } : null));
    setPulse({ flag_counts: { counts: { flagged: 3 } } });
    const first = slice.getSnapshot();
    expect(first).toEqual({ n: 3 });
    expect(slice.getSnapshot()).toBe(first);
  });

  it("keeps the last good answer when a later pulse has that part missing", () => {
    const slice = createPulseSlice<string>((p) => p.statement_replies as unknown as string | null);
    setPulse({ statement_replies: "ok" as never });
    expect(slice.getSnapshot()).toBe("ok");
    setPulse({ statement_replies: null, errors: ["statement_replies"] });
    expect(slice.getSnapshot()).toBe("ok");
  });

  it("shows an optimistic set at once and gives way to the next pulse", () => {
    const slice = createPulseSlice<{ v: number }>((p) => (p.robot_notices ? { v: p.robot_notices.count } : null));
    setPulse({ robot_notices: { count: 2, items: [] } });
    expect(slice.getSnapshot()).toEqual({ v: 2 });
    slice.set({ v: 1 });
    expect(slice.getSnapshot()).toEqual({ v: 1 });
    setPulse({ robot_notices: { count: 5, items: [] } });
    expect(slice.getSnapshot()).toEqual({ v: 5 });
  });

  it("is empty while that part has not arrived", () => {
    const slice = createPulseSlice<AttentionResponse>((p) => p.attention);
    setPulse({});
    expect(slice.getSnapshot()).toBe(null);
  });
});

describe("fetchPulse", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("asks once, for everyone, and throws on a failure so the last answer is kept", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ errors: [] })));
    vi.stubGlobal("fetch", fetchMock);
    await fetchPulse();
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/pulse");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("x", { status: 502 })));
    await expect(fetchPulse()).rejects.toThrow();
  });
});
