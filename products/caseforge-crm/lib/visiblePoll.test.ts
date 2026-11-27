import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { startVisiblePoll } from "./visiblePoll";

let visibility = "visible";
const docHandlers = new Set<() => void>();

beforeEach(() => {
  vi.useFakeTimers();
  visibility = "visible";
  docHandlers.clear();
  vi.stubGlobal("window", {
    setInterval: (fn: () => void, ms: number) => setInterval(fn, ms),
    clearInterval: (id: number) => clearInterval(id),
  });
  vi.stubGlobal("document", {
    get visibilityState() {
      return visibility;
    },
    addEventListener: (_: string, fn: () => void) => docHandlers.add(fn),
    removeEventListener: (_: string, fn: () => void) => docHandlers.delete(fn),
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const setVisibility = (value: string) => {
  visibility = value;
  docHandlers.forEach((fn) => fn());
};

describe("startVisiblePoll", () => {
  it("runs at once by default and then on the interval", () => {
    const tick = vi.fn();
    const stop = startVisiblePoll(tick, 1000);
    expect(tick).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(2000);
    expect(tick).toHaveBeenCalledTimes(3);
    stop();
  });

  it("skips the first run when immediate is false", () => {
    const tick = vi.fn();
    const stop = startVisiblePoll(tick, 1000, { immediate: false });
    expect(tick).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(tick).toHaveBeenCalledTimes(1);
    stop();
  });

  it("stops while hidden and catches up on return only when stale", () => {
    const tick = vi.fn();
    const stop = startVisiblePoll(tick, 1000);
    setVisibility("hidden");
    vi.advanceTimersByTime(10_000);
    expect(tick).toHaveBeenCalledTimes(1);
    setVisibility("visible");
    expect(tick).toHaveBeenCalledTimes(2);
    setVisibility("hidden");
    setVisibility("visible");
    expect(tick).toHaveBeenCalledTimes(2);
    stop();
  });

  it("removes its listener and timer when stopped", () => {
    const tick = vi.fn();
    const stop = startVisiblePoll(tick, 1000);
    stop();
    vi.advanceTimersByTime(5000);
    expect(tick).toHaveBeenCalledTimes(1);
    expect(docHandlers.size).toBe(0);
  });
});
