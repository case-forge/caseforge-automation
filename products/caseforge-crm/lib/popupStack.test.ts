import { beforeEach, describe, expect, it } from "vitest";
import { POPUP_Z_BASE, popupStack, raised, removed, stackZ } from "./popupStack";

describe("popup stack", () => {
  beforeEach(() => popupStack.reset());

  it("puts the most recently opened on top", () => {
    let o = raised([], "status-board");
    o = raised(o, "hearings-rail");
    o = raised(o, "whats-new");
    expect(stackZ(o, "whats-new")!).toBeGreaterThan(stackZ(o, "hearings-rail")!);
    expect(stackZ(o, "hearings-rail")!).toBeGreaterThan(stackZ(o, "status-board")!);
  });
  it("raising one already open moves it to the top without duplicating it", () => {
    const o = raised(raised(raised([], "a"), "b"), "a");
    expect(o).toEqual(["b", "a"]);
  });
  it("a closed popup leaves the stack and has no z-index", () => {
    expect(stackZ(removed(["a", "b"], "a"), "a")).toBeNull();
  });
  it("stays under the pinned band", () => {
    expect(POPUP_Z_BASE + 100).toBeLessThan(3999);
  });
  it("the store keeps the order across raise and drop", () => {
    popupStack.raise("a");
    popupStack.raise("b");
    popupStack.raise("a");
    expect(popupStack.zFor("a")!).toBeGreaterThan(popupStack.zFor("b")!);
    popupStack.drop("a");
    expect(popupStack.zFor("a")).toBeNull();
    expect(popupStack.zFor("b")).toBe(POPUP_Z_BASE);
  });
});

import { reportShowing, clearShowing, toggleDecision, toggleWindow, consumeRequest, consumeCloseRequest } from "./cornerPrompts";

describe("launcher toggle (floating windows: Hearings Panel, What's New, Improve Classifier)", () => {
  it("decides to close a window that is showing and to open one that is not", () => {
    expect(toggleDecision(true)).toBe("close");
    expect(toggleDecision(false)).toBe("open");
  });
  it("opens when closed (raising it), and a second press asks it to close instead of opening again", () => {
    popupStack.reset();
    reportShowing("whats-new", false);
    toggleWindow("whats-new");
    expect(consumeRequest("whats-new")).toBe(true);
    expect(popupStack.zFor("whats-new")).not.toBeNull();
    reportShowing("whats-new", true);
    toggleWindow("whats-new");
    expect(consumeCloseRequest("whats-new")).toBe(true);
    expect(consumeCloseRequest("whats-new")).toBe(false);
    expect(consumeRequest("whats-new")).toBe(false);
    reportShowing("whats-new", false);
    toggleWindow("whats-new");
    expect(consumeRequest("whats-new")).toBe(true);
    clearShowing("whats-new");
  });
});
