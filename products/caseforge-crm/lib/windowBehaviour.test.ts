import { afterEach, describe, expect, it, vi } from "vitest";
import { WINDOW_DOCK_STORAGE_KEY, WINDOW_SNAP_STORAGE_KEY, readStoredWindowGesture } from "./windowBehaviour";
import { windowGestures } from "./windowSnap";

function store(values: Record<string, string>) {
  vi.stubGlobal("window", { localStorage: { getItem: (k: string) => values[k] ?? null }, addEventListener: () => {}, removeEventListener: () => {} });
}

afterEach(() => vi.unstubAllGlobals());

describe("window gesture settings", () => {
  it("are on unless stored as off", () => {
    expect(readStoredWindowGesture(null)).toBe(true);
    expect(readStoredWindowGesture("on")).toBe(true);
    expect(readStoredWindowGesture("off")).toBe(false);
  });

  it("leave a window's own gestures alone when nothing is stored", () => {
    store({});
    expect(windowGestures("hearings-rail")).toEqual({ snaps: true, docks: true });
  });

  it("switch snapping and dragging to an edge tab off independently", () => {
    store({ [WINDOW_SNAP_STORAGE_KEY]: "off" });
    expect(windowGestures("hearings-rail")).toEqual({ snaps: false, docks: true });
    store({ [WINDOW_DOCK_STORAGE_KEY]: "off" });
    expect(windowGestures("hearings-rail")).toEqual({ snaps: true, docks: false });
    store({ [WINDOW_SNAP_STORAGE_KEY]: "off", [WINDOW_DOCK_STORAGE_KEY]: "off" });
    expect(windowGestures("hearings-rail")).toEqual({ snaps: false, docks: false });
  });

  it("never turns on a gesture a kind of window does not have", () => {
    store({});
    expect(windowGestures("whats-new")).toEqual({ snaps: false, docks: true });
  });
});
