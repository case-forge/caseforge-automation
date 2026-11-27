import { describe, expect, it } from "vitest";
import { addTab, moveTab, removeTab } from "./minimisedTabs";

describe("minimised tabs store steps", () => {
  it("adds a tab last in its slot, and only refreshes the title of one already there", () => {
    let tabs = addTab([], "a", "Alpha", undefined, 1);
    tabs = addTab(tabs, "b", "Beta", { side: "left", slot: "top" }, 2);
    expect(tabs.map((t) => [t.id, t.side, t.slot])).toEqual([["a", "right", "middle"], ["b", "left", "top"]]);
    const again = addTab(tabs, "a", "Alpha 2", undefined, 9);
    expect(again).toHaveLength(2);
    expect(again[0]).toMatchObject({ title: "Alpha 2", seq: 1 });
  });
  it("moves a tab to the end of another slot and removes one", () => {
    let tabs = addTab(addTab([], "a", "A", undefined, 1), "b", "B", undefined, 2);
    tabs = moveTab(tabs, "a", { side: "left", slot: "bottom" }, 3);
    expect(tabs.find((t) => t.id === "a")).toMatchObject({ side: "left", slot: "bottom", seq: 3 });
    expect(removeTab(tabs, "b").map((t) => t.id)).toEqual(["a"]);
    expect(removeTab(tabs, "zzz")).toBe(tabs);
  });
});
