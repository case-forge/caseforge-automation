import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { FIRST_VISIT_LIMIT, loadSeen, storageKey, storeSeen, unseen, type WhatsNewItem } from "./whatsNew";

const items: WhatsNewItem[] = Array.from({ length: 8 }, (_, i) => ({ sha: `s${i}`, date: "2026-10-15T10:00:00+01:00", note: `Note ${i}` }));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("What's new", () => {
  it("shows only the notes newer than the last one seen", () => {
    expect(unseen(items, "s3").map((i) => i.sha)).toEqual(["s0", "s1", "s2"]);
    expect(unseen(items, "s0")).toEqual([]);
  });

  it("shows the newest few on a first visit, or when the seen note fell off the list", () => {
    expect(unseen(items, "").length).toBe(FIRST_VISIT_LIMIT);
    expect(unseen(items, "gone").length).toBe(FIRST_VISIT_LIMIT);
    expect(unseen([], "")).toEqual([]);
  });

  it("remembers per editor name, and works with no storage at all", () => {
    expect(storageKey("  Sam ")).not.toBe(storageKey(""));
    const store = new Map<string, string>();
    vi.stubGlobal("window", {
      localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
    });
    storeSeen("Sam", "s2");
    expect(loadSeen("sam")).toBe("s2");
    expect(loadSeen("")).toBe("");
    vi.stubGlobal("window", {
      localStorage: {
        getItem: () => {
          throw new Error("blocked");
        },
        setItem: () => {
          throw new Error("blocked");
        },
      },
    });
    expect(loadSeen("Sam")).toBe("");
    expect(() => storeSeen("Sam", "s1")).not.toThrow();
  });

  it("renders notes as text, never HTML", () => {
    const source = readFileSync(fileURLToPath(new URL("../components/WhatsNew.tsx", import.meta.url)), "utf8");
    expect(source).not.toContain("dangerouslySetInnerHTML");
    expect(source).toContain("{item.note}");
  });
});
