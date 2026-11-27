import { beforeEach, describe, expect, it } from "vitest";
import { parseOpen, widgetOpen, withOpen } from "./widgetOpen";

describe("which boxes are open", () => {
  beforeEach(() => widgetOpen.reset());
  it("showing or hiding one box leaves the others as they were", () => {
    let o = withOpen([], "hearings", true);
    o = withOpen(o, "classifier", true);
    o = withOpen(o, "classifier", false);
    expect(o).toEqual(["hearings"]);
  });
  it("survives a route change: the state is module-level, not a page's", () => {
    widgetOpen.set("status-board", true);
    widgetOpen.set("auto-sent", true);
    widgetOpen.set("auto-sent", false);

    expect(widgetOpen.isOpen("status-board")).toBe(true);
    expect(widgetOpen.isOpen("auto-sent")).toBe(false);
  });
  it("reads a stored list defensively", () => {
    expect(parseOpen(null)).toEqual([]);
    expect(parseOpen("not json")).toEqual([]);
    expect(parseOpen('{"a":1}')).toEqual([]);
    expect(parseOpen('["a",3,"b"]')).toEqual(["a", "b"]);
  });
});
