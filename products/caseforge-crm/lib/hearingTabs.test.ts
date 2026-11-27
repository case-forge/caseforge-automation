import { describe, expect, it } from "vitest";
import { MAX_HEARING_TABS, TABS_FULL_HINT, activateTab, addTab, closeTab, emptyTabs, parseTabs, serialiseTabs, tabTitle, tabsFull } from "./hearingTabs";
import type { TabsState } from "./hearingTabs";

const spec = (name?: string) => ({ clientName: name });
function fill(n: number): TabsState<{ clientName?: string }> {
  let s: TabsState<{ clientName?: string }> = emptyTabs();
  for (let i = 0; i < n; i++) s = addTab(s, { key: `k${i}`, spec: spec(`Client ${i}`) }).state;
  return s;
}

describe("Add a Hearing tabs", () => {
  it("adds a tab and shows it; the same client is shown, not doubled", () => {
    let s = addTab(emptyTabs(), { key: "a", spec: spec("A") }).state;
    s = addTab(s, { key: "b", spec: spec() }).state;
    expect(s.active).toBe("b");
    const again = addTab(s, { key: "a", spec: spec("A") });
    expect(again.added).toBe(false);
    expect(again.state.tabs).toHaveLength(2);
    expect(again.state.active).toBe("a");
  });
  it("is capped at five: the sixth is refused and the showing tab stays", () => {
    expect(MAX_HEARING_TABS).toBe(5);
    const s = fill(5);
    expect(tabsFull(s)).toBe(true);
    const sixth = addTab(s, { key: "k5", spec: spec() });
    expect(sixth.full).toBe(true);
    expect(sixth.state).toBe(s);
    expect(TABS_FULL_HINT).toBe("Close a tab to start another");
  });
  it("closing a tab removes only that tab and shows its neighbour", () => {
    const s = fill(3);
    const closed = closeTab(s, "k2");
    expect(closed.tabs.map((t) => t.key)).toEqual(["k0", "k1"]);
    expect(closed.active).toBe("k1");
    expect(closeTab(s, "k0").active).toBe("k2");
    expect(closeTab(activateTab(s, "k0"), "k1").active).toBe("k0");
    expect(closeTab(fill(1), "k0")).toEqual({ tabs: [], active: "" });
  });
  it("a closed tab frees a place under the cap", () => {
    const s = closeTab(fill(5), "k1");
    expect(addTab(s, { key: "new", spec: spec() }).added).toBe(true);
  });
  it("titles by client, else New hearing", () => {
    expect(tabTitle({ clientName: " Ada " })).toBe("Ada");
    expect(tabTitle({})).toBe("New hearing");
  });
  it("hiding the box is not in this state at all: tabs are untouched by anything but add, close and show", () => {
    const s = fill(3);
    expect(activateTab(s, "k1").tabs).toBe(s.tabs);
    expect(activateTab(s, "nope")).toBe(s);
  });
  it("round-trips for the visit without callbacks, and reads garbage safely", () => {
    const s = addTab(emptyTabs(), { key: "a", spec: { clientName: "A", onCreated: () => undefined } as never }).state;
    const back = parseTabs<{ clientName?: string }>(serialiseTabs(s as never));
    expect(back.tabs[0].spec).toEqual({ clientName: "A" });
    expect(parseTabs("nope")).toEqual(emptyTabs());
    expect(parseTabs(null)).toEqual(emptyTabs());
  });
});
