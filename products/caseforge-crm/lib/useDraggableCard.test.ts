import { describe, expect, it } from "vitest";
import {
  clampOffset,
  clearStoredFractions,
  DEFAULT_OFFSET,
  dragOffset,
  EDGE_PX,
  fromFractions,
  isNarrow,
  keyAction,
  readStoredFractions,
  toFractions,
  writeStoredFractions,
} from "./useDraggableCard";

const view = { w: 1000, h: 800 };
const card = { w: 380, h: 200 };

function memoryStore(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => void (data[k] = v),
    removeItem: (k: string) => void delete data[k],
  };
}

const blockedStore = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
  removeItem: () => {
    throw new Error("blocked");
  },
};

describe("clamping a card to the window", () => {
  it("leaves a place that fits alone", () => {
    expect(clampOffset({ right: 100, bottom: 120 }, card, view)).toEqual({ right: 100, bottom: 120 });
  });
  it("keeps the whole card on screen on every side", () => {
    expect(clampOffset({ right: -50, bottom: -50 }, card, view)).toEqual({ right: EDGE_PX, bottom: EDGE_PX });
    expect(clampOffset({ right: 5000, bottom: 5000 }, card, view)).toEqual({
      right: view.w - card.w - EDGE_PX,
      bottom: view.h - card.h - EDGE_PX,
    });
  });
  it("puts a card bigger than the window at the edge rather than off screen", () => {
    expect(clampOffset({ right: 300, bottom: 300 }, { w: 1200, h: 900 }, view)).toEqual({ right: EDGE_PX, bottom: EDGE_PX });
  });
  it("re-clamps a remembered place into a smaller window", () => {
    const fractions = toFractions({ right: 600, bottom: 500 }, view);
    const small = { w: 700, h: 500 };
    expect(clampOffset(fromFractions(fractions, small), card, small)).toEqual({
      right: small.w - card.w - EDGE_PX,
      bottom: small.h - card.h - EDGE_PX,
    });
  });
});

describe("dragging", () => {
  it("moves the card with the pointer: right and down shrink the offsets", () => {
    const start = { x: 500, y: 400, offset: DEFAULT_OFFSET };
    expect(dragOffset(start, { x: 480, y: 380 })).toEqual({ right: 36, bottom: 36 });
    expect(dragOffset(start, { x: 510, y: 410 })).toEqual({ right: 6, bottom: 6 });
  });
});

describe("the keyboard", () => {
  const at = { right: 100, bottom: 100 };
  it("moves by 16px, or 64px with Shift, in the direction pressed", () => {
    expect(keyAction("ArrowLeft", false, at)).toEqual({ type: "move", offset: { right: 116, bottom: 100 } });
    expect(keyAction("ArrowRight", false, at)).toEqual({ type: "move", offset: { right: 84, bottom: 100 } });
    expect(keyAction("ArrowUp", true, at)).toEqual({ type: "move", offset: { right: 100, bottom: 164 } });
    expect(keyAction("ArrowDown", true, at)).toEqual({ type: "move", offset: { right: 100, bottom: 36 } });
  });
  it("resets on Escape and ignores other keys", () => {
    expect(keyAction("Escape", false, at)).toEqual({ type: "reset" });
    expect(keyAction("Enter", false, at)).toBeNull();
    expect(keyAction("a", false, at)).toBeNull();
  });
});

describe("remembering the place", () => {
  it("round-trips as a fraction of the window", () => {
    const store = memoryStore();
    writeStoredFractions("k", toFractions({ right: 250, bottom: 80 }, view), store);
    const back = readStoredFractions("k", store);
    expect(back).toEqual({ x: 0.25, y: 0.1 });
    expect(fromFractions(back!, { w: 2000, h: 1000 })).toEqual({ right: 500, bottom: 100 });
  });
  it("forgets on reset", () => {
    const store = memoryStore();
    writeStoredFractions("k", { x: 0.1, y: 0.1 }, store);
    clearStoredFractions("k", store);
    expect(readStoredFractions("k", store)).toBeNull();
  });
  it("ignores junk: bad JSON, wrong types, out of range", () => {
    for (const raw of ["", "nope", "{}", '{"x":"1","y":0}', '{"x":2,"y":0.5}', '{"x":-0.1,"y":0.5}', "null"]) {
      expect(readStoredFractions("k", memoryStore({ k: raw })), raw).toBeNull();
    }
  });
  it("works with storage blocked or missing: nothing throws, nothing is read", () => {
    expect(() => writeStoredFractions("k", { x: 0.1, y: 0.1 }, blockedStore)).not.toThrow();
    expect(() => clearStoredFractions("k", blockedStore)).not.toThrow();
    expect(readStoredFractions("k", blockedStore)).toBeNull();
    expect(readStoredFractions("k", null)).toBeNull();
    expect(() => writeStoredFractions("k", { x: 0.1, y: 0.1 }, null)).not.toThrow();
  });
});

describe("a phone-width window", () => {
  it("turns dragging off under 480px", () => {
    expect(isNarrow(479)).toBe(true);
    expect(isNarrow(480)).toBe(false);
  });
});
