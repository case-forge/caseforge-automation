import { describe, expect, it } from "vitest";
import { measureScrollbarWidth, type MeasurableDocument } from "./scrollbarWidth";

type MeasurableElement = { style: Record<string, string>; offsetWidth: number; clientWidth: number };

function fakeDoc(offsetWidth: number, clientWidth: number) {
  const log: string[] = [];
  const el: MeasurableElement = { style: {}, offsetWidth, clientWidth };
  const doc = {
    createElement: () => el,
    body: {
      appendChild: () => log.push("append"),
      removeChild: () => log.push("remove"),
    },
  } as unknown as MeasurableDocument;
  return { doc, el, log };
}

describe("measureScrollbarWidth", () => {
  it("is the difference between the outer and inner width", () => {
    expect(measureScrollbarWidth(fakeDoc(100, 85).doc)).toBe(15);
  });

  it("is 0 for overlay scrollbars", () => {
    expect(measureScrollbarWidth(fakeDoc(100, 100).doc)).toBe(0);
  });

  it("refuses an absurd or non-finite measurement", () => {
    expect(measureScrollbarWidth(fakeDoc(100, 20).doc)).toBe(0);
    expect(measureScrollbarWidth(fakeDoc(Number.NaN, 85).doc)).toBe(0);
  });

  it("always removes its probe, and forces a scrollbar on it", () => {
    const { doc, el, log } = fakeDoc(100, 85);
    measureScrollbarWidth(doc);
    expect(log).toEqual(["append", "remove"]);
    expect(el.style.overflow).toBe("scroll");
  });
});
