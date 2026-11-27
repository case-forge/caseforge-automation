import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPolledStore } from "./polledStore";

class FakeTarget {
  private handlers = new Map<string, Set<() => void>>();
  addEventListener(name: string, fn: () => void) {
    if (!this.handlers.has(name)) this.handlers.set(name, new Set());
    this.handlers.get(name)!.add(fn);
  }
  removeEventListener(name: string, fn: () => void) {
    this.handlers.get(name)?.delete(fn);
  }
  dispatch(name: string) {
    this.handlers.get(name)?.forEach((fn) => fn());
  }
  count(name: string) {
    return this.handlers.get(name)?.size ?? 0;
  }
}

let win: FakeTarget & { setInterval: typeof setInterval; clearInterval: typeof clearInterval };
let doc: FakeTarget & { visibilityState: string };

beforeEach(() => {
  vi.useFakeTimers();
  win = Object.assign(new FakeTarget(), {
    setInterval: ((fn: () => void, ms: number) => setInterval(fn, ms)) as typeof setInterval,
    clearInterval: ((id: number) => clearInterval(id)) as typeof clearInterval,
  });
  doc = Object.assign(new FakeTarget(), { visibilityState: "visible" });
  vi.stubGlobal("window", win);
  vi.stubGlobal("document", doc);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function flush() {
  await vi.advanceTimersByTimeAsync(0);
}

describe("createPolledStore", () => {
  it("fetches once however many components subscribe", async () => {
    const fetcher = vi.fn(async () => 1);
    const store = createPolledStore({ fetch: fetcher, intervalMs: 60_000 });
    const off1 = store.subscribe(() => {});
    const off2 = store.subscribe(() => {});
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot()).toBe(1);
    off1();
    off2();
  });

  it("polls on the interval and stops when the last subscriber leaves", async () => {
    const fetcher = vi.fn(async () => 1);
    const store = createPolledStore({ fetch: fetcher, intervalMs: 60_000 });
    const off = store.subscribe(() => {});
    await vi.advanceTimersByTimeAsync(120_000);
    expect(fetcher).toHaveBeenCalledTimes(3);
    off();
    await vi.advanceTimersByTimeAsync(300_000);
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("does not poll while the tab is hidden and catches up when it returns", async () => {
    const fetcher = vi.fn(async () => 1);
    const store = createPolledStore({ fetch: fetcher, intervalMs: 60_000 });
    const off = store.subscribe(() => {});
    await flush();
    doc.visibilityState = "hidden";
    doc.dispatch("visibilitychange");
    await vi.advanceTimersByTimeAsync(600_000);
    expect(fetcher).toHaveBeenCalledTimes(1);
    doc.visibilityState = "visible";
    doc.dispatch("visibilitychange");
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(2);
    off();
  });

  it("refetches on its events and removes the listeners when unsubscribed", async () => {
    const fetcher = vi.fn(async () => 1);
    const store = createPolledStore({ fetch: fetcher, intervalMs: 60_000, events: ["caseforge:changed"] });
    const off = store.subscribe(() => {});
    await flush();
    win.dispatch("caseforge:changed");
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(2);
    off();
    expect(win.count("caseforge:changed")).toBe(0);
  });

  it("keeps the last answer when a refresh fails", async () => {
    let fail = false;
    const store = createPolledStore({
      fetch: async () => {
        if (fail) throw new Error("down");
        return 7;
      },
      intervalMs: 60_000,
    });
    const off = store.subscribe(() => {});
    await flush();
    fail = true;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(store.getSnapshot()).toBe(7);
    off();
  });

  it("reads again after a refresh asked for while a read is already in flight", async () => {
    const resolvers: Array<(v: number) => void> = [];
    const fetcher = vi.fn(() => new Promise<number>((resolve) => resolvers.push(resolve)));
    const store = createPolledStore({ fetch: fetcher, intervalMs: 60_000 });
    const off = store.subscribe(() => {});
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);
    store.refresh();
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);
    resolvers[0](1);
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(2);
    resolvers[1](2);
    await flush();
    expect(store.getSnapshot()).toBe(2);
    off();
  });
});
