import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { attachDismiss, isOutside } from "./dismiss";
import type { DismissReason } from "./dismiss";

function box(...inside: object[]) {
  const self = { contains: (node: unknown) => node === self || inside.includes(node as object) };
  return self;
}

function fakeHost() {
  const listeners = new Map<string, Set<(event: Event) => void>>();
  return {
    addEventListener(type: string, listener: (event: Event) => void) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type)!.add(listener);
    },
    removeEventListener(type: string, listener: (event: Event) => void) {
      listeners.get(type)?.delete(listener);
    },
    fire(type: string, event: object) {
      for (const listener of [...(listeners.get(type) ?? [])]) listener(event as Event);
    },
    count: () => [...listeners.values()].reduce((n, set) => n + set.size, 0),
  };
}

describe("isOutside", () => {
  const child = {};
  const menu = box(child);
  const entry = box();

  it("is false for the dropdown itself and anything inside it", () => {
    expect(isOutside(menu, [menu])).toBe(false);
    expect(isOutside(child, [menu])).toBe(false);
  });

  it("is true for anything else on the page", () => {
    expect(isOutside({}, [menu])).toBe(true);
  });

  it("treats every root as part of the dropdown (a panel and its entry in the apps menu)", () => {
    expect(isOutside(entry, [menu, entry])).toBe(false);
    expect(isOutside(entry, [menu])).toBe(true);
  });

  it("ignores a root that is not mounted", () => {
    expect(isOutside(child, [null, undefined, menu])).toBe(false);
    expect(isOutside(child, [null, undefined])).toBe(true);
  });
});

describe("attachDismiss", () => {
  function setup() {
    const host = fakeHost();
    const child = {};
    const menu = box(child);
    const reasons: DismissReason[] = [];
    const detach = attachDismiss(host, () => [menu], (reason) => reasons.push(reason));
    return { host, child, menu, reasons, detach };
  }

  it("closes on a press outside", () => {
    const { host, reasons } = setup();
    host.fire("pointerdown", { target: {} });
    expect(reasons).toEqual(["outside"]);
  });

  it("stays open on a press inside", () => {
    const { host, child, menu, reasons } = setup();
    host.fire("pointerdown", { target: child });
    host.fire("pointerdown", { target: menu });
    expect(reasons).toEqual([]);
  });

  it("closes on Escape and on no other key", () => {
    const { host, reasons } = setup();
    host.fire("keydown", { key: "Enter" });
    host.fire("keydown", { key: "a" });
    expect(reasons).toEqual([]);
    host.fire("keydown", { key: "Escape" });
    expect(reasons).toEqual(["escape"]);
  });

  it("reads the roots at each press, so a part that mounts later counts", () => {
    const host = fakeHost();
    const late = box();
    const roots: object[] = [];
    const reasons: DismissReason[] = [];
    attachDismiss(host, () => roots as never, (reason) => reasons.push(reason));
    host.fire("pointerdown", { target: late });
    roots.push(late);
    host.fire("pointerdown", { target: late });
    expect(reasons).toEqual(["outside"]);
  });

  it("stops listening once detached", () => {
    const { host, reasons, detach } = setup();
    expect(host.count()).toBe(2);
    detach();
    expect(host.count()).toBe(0);
    host.fire("pointerdown", { target: {} });
    host.fire("keydown", { key: "Escape" });
    expect(reasons).toEqual([]);
  });
});

describe("every dropdown closes the same way", () => {
  const dir = fileURLToPath(new URL("../components/", import.meta.url));
  const sources = readdirSync(dir)
    .filter((name) => name.endsWith(".tsx"))
    .map((name) => ({ name, text: readFileSync(dir + name, "utf8") }));

  it("has no component listening for outside presses by hand", () => {
    const byHand = sources.filter(({ text }) => /addEventListener\(\s*"(pointerdown|mousedown)"/.test(text)).map(({ name }) => name);
    expect(byHand).toEqual([]);
  });

  it("uses the hook in the apps menu, every header panel and Recently viewed", () => {
    for (const name of ["AppDrawer", "AttentionBell", "TodoHeader", "RobotNotices", "RecentlyViewedMenu"]) {
      const text = sources.find((s) => s.name === `${name}.tsx`)!.text;
      expect(text, name).toMatch(/useDismiss\(\s*open,/);
    }
  });

  it("uses it in every component that opens something with aria-expanded={open}", () => {
    const missing = sources.filter(({ text }) => text.includes("aria-expanded={open}") && !text.includes("useDismiss(")).map(({ name }) => name);
    expect(missing).toEqual([]);
  });

  it("controls the apps menu's open state, so it can be closed from outside it", () => {
    const drawer = sources.find((s) => s.name === "AppDrawer.tsx")!.text;
    expect(drawer).toContain("open={open}");
    expect(drawer).toContain("onToggle={(event) => setOpen(event.currentTarget.open)}");
    expect(drawer).toContain('closest("[data-menu-close]")');
  });
});
