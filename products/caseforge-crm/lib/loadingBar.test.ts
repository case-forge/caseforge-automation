import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FINISH_MS, SHOW_DELAY_MS, TRICKLE_MS, countFetches, createLoadingBar, nextProgress, runInBackground } from "./loadingBar";

describe("nextProgress", () => {
  it("creeps up and never passes 90", () => {
    let p = 8;
    for (let i = 0; i < 200; i++) p = nextProgress(p);
    expect(p).toBe(90);
    expect(nextProgress(8)).toBeGreaterThan(8);
  });
});

describe("the loading bar", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("never shows for a request that answers at once", () => {
    const bar = createLoadingBar();
    bar.begin();
    vi.advanceTimersByTime(SHOW_DELAY_MS - 10);
    bar.end();
    vi.advanceTimersByTime(1000);
    expect(bar.getState().visible).toBe(false);
  });

  it("shows, trickles, and finishes only when every request has settled", () => {
    const bar = createLoadingBar();
    bar.begin();
    bar.begin();
    vi.advanceTimersByTime(SHOW_DELAY_MS + 1);
    expect(bar.getState().visible).toBe(true);
    const first = bar.getState().progress;
    vi.advanceTimersByTime(TRICKLE_MS * 3);
    expect(bar.getState().progress).toBeGreaterThan(first);
    bar.end();
    expect(bar.getState().progress).toBeLessThan(100);
    bar.end();
    expect(bar.getState().progress).toBe(100);
    vi.advanceTimersByTime(FINISH_MS + 1);
    expect(bar.getState()).toEqual({ visible: false, progress: 0, waiting: [] });
    expect(bar.pending()).toBe(0);
  });

  it("keeps going when a new request starts during the finish", () => {
    const bar = createLoadingBar();
    bar.begin();
    vi.advanceTimersByTime(SHOW_DELAY_MS + 1);
    bar.end();
    bar.begin();
    vi.advanceTimersByTime(FINISH_MS + 1);
    expect(bar.getState().visible).toBe(true);
  });

  it("ignores an extra end", () => {
    const bar = createLoadingBar();
    bar.end();
    expect(bar.pending()).toBe(0);
  });
});

describe("countFetches", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("counts a foreground fetch until it settles, success or failure", async () => {
    const bar = createLoadingBar();
    let resolve!: (r: Response) => void;
    const original = vi.fn(() => new Promise<Response>((r) => (resolve = r))) as unknown as typeof fetch;
    const counted = countFetches(original, bar);
    const p = counted("/api/x");
    expect(bar.pending()).toBe(1);
    resolve(new Response("{}"));
    await p;
    expect(bar.pending()).toBe(0);

    const failing = countFetches((() => Promise.reject(new Error("down"))) as unknown as typeof fetch, bar);
    await expect(failing("/api/y")).rejects.toThrow("down");
    expect(bar.pending()).toBe(0);
  });

  it("does not count a fetch a background poll starts", async () => {
    const bar = createLoadingBar();
    const counted = countFetches((() => Promise.resolve(new Response("{}"))) as unknown as typeof fetch, bar);
    await runInBackground(() => counted("/api/poll"));
    expect(bar.pending()).toBe(0);
  });
});

describe("naming what the bar waits on", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("lists the paths still pending, without their query, and drops each as it settles", async () => {
    const bar = createLoadingBar();
    let slow!: (r: Response) => void;
    const original = vi.fn((url: string) => (url.includes("slow") ? new Promise<Response>((r) => (slow = r)) : Promise.resolve(new Response("{}")))) as unknown as typeof fetch;
    const counted = countFetches(original, bar);
    const a = counted("/api/clients/slow?matter_id=1");
    await counted("/api/clients/fast?x=2");
    vi.advanceTimersByTime(SHOW_DELAY_MS + 1);
    expect(bar.getState().waiting).toEqual(["/api/clients/slow"]);
    slow(new Response("{}"));
    await a;
    expect(bar.getState().waiting).toEqual([]);
  });
});

describe("backgroundFetch", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("stays background across awaits, because the request itself is marked", async () => {
    const bar = createLoadingBar();
    const { backgroundFetch } = await import("./loadingBar");
    const original = vi.fn(() => Promise.resolve(new Response("{}"))) as unknown as typeof fetch;
    vi.stubGlobal("fetch", countFetches(original, bar));
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(50);
    const pending = backgroundFetch("/api/poll", { cache: "no-store" });
    expect(bar.pending()).toBe(0);
    await pending;
    expect(bar.pending()).toBe(0);
  });

  it("does not mark an ordinary fetch, and does not change the caller's own init", async () => {
    const bar = createLoadingBar();
    const { backgroundFetch } = await import("./loadingBar");
    const original = vi.fn(() => new Promise<Response>(() => {})) as unknown as typeof fetch;
    vi.stubGlobal("fetch", countFetches(original, bar));
    const init = { cache: "no-store" as const };
    void backgroundFetch("/api/a", init);
    void fetch("/api/b", init);
    expect(bar.pending()).toBe(1);
    expect((init as Record<string, unknown>).background).toBeUndefined();
  });
});
