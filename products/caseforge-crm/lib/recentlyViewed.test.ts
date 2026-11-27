import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { clearRecentlyViewed, forgetRecentlyViewed, loadRecentlyViewed, recordRecentlyViewed, withoutMatters } from "./recentlyViewed";
import type { ClientMatch } from "./types";

class FakeLocalStorage {
  private store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  clear(): void {
    this.store.clear();
  }
}

function match(matterId: number, name: string): ClientMatch {
  return { matter_id: matterId, client_name: name, extra: {} };
}

beforeEach(() => {
  (globalThis as unknown as { window: Window }).window = {
    localStorage: new FakeLocalStorage(),
  } as unknown as Window;
});

afterEach(() => {
  delete (globalThis as { window?: unknown }).window;
});

describe("recentlyViewed", () => {
  it("is empty when nothing has been viewed yet", () => {
    expect(loadRecentlyViewed()).toEqual([]);
  });

  it("records a viewed match and puts it first", () => {
    recordRecentlyViewed(match(1, "Alice"));
    const entries = loadRecentlyViewed();
    expect(entries).toHaveLength(1);
    expect(entries[0].match.client_name).toBe("Alice");
    expect(typeof entries[0].viewedAt).toBe("string");
  });

  it("moves an already-viewed matter to the front instead of duplicating it", () => {
    recordRecentlyViewed(match(1, "Alice"));
    recordRecentlyViewed(match(2, "Bob"));
    recordRecentlyViewed(match(1, "Alice"));

    const entries = loadRecentlyViewed();
    expect(entries).toHaveLength(2);
    expect(entries[0].match.client_name).toBe("Alice");
    expect(entries[1].match.client_name).toBe("Bob");
  });

  it("caps at 20 entries, dropping the oldest", () => {
    for (let i = 0; i < 25; i++) {
      recordRecentlyViewed(match(i, `Client ${i}`));
    }
    const entries = loadRecentlyViewed();
    expect(entries).toHaveLength(20);
    expect(entries[0].match.client_name).toBe("Client 24");
    expect(entries.some((e) => e.match.client_name === "Client 0")).toBe(false);
  });

  it("never records a match with no matter_id", () => {
    recordRecentlyViewed({ client_name: "No matter id", extra: {} });
    expect(loadRecentlyViewed()).toEqual([]);
  });

  it("survives corrupt localStorage content rather than throwing", () => {
    window.localStorage.setItem("caseforge-client-viewer:recently-viewed", "{not json");
    expect(loadRecentlyViewed()).toEqual([]);
  });
});

describe("recentSelection", () => {
  const m = (id: number | null, name = "x") => ({ matter_id: id, client_name: name }) as unknown as import("./types").ClientMatch;
  it("selects a client that is not first in the list at its real index", async () => {
    const { recentSelection } = await import("./recentlyViewed");
    const all = [m(1), m(2), m(3)];
    const out = recentSelection(all, all[2]);
    expect(out.index).toBe(2);
    expect(out.matches).toHaveLength(3);
  });
  it("drops repeats and puts a client missing from the list in front", async () => {
    const { recentSelection } = await import("./recentlyViewed");
    expect(recentSelection([m(1), m(1), m(2)], m(2)).matches).toHaveLength(2);
    const out = recentSelection([m(1)], m(9));
    expect(out.index).toBe(0);
    expect(out.matches.map((x) => x.matter_id)).toEqual([9, 1]);
  });

  it("clears the whole list", () => {
    recordRecentlyViewed(match(1, "One"));
    recordRecentlyViewed(match(2, "Two"));
    clearRecentlyViewed();
    expect(loadRecentlyViewed()).toEqual([]);
  });
});

describe("forgetting merged-away clients", () => {
  const entry = (id: number) => ({ match: { matter_id: id } as ClientMatch, viewedAt: "2026-10-19T10:00:00Z" });

  it("drops only the named matters", () => {
    expect(withoutMatters([entry(607), entry(623)], ["623"]).map((e) => e.match.matter_id)).toEqual([607]);
  });

  it("leaves the list alone when nothing is hidden", () => {
    expect(withoutMatters([entry(607)], [])).toHaveLength(1);
    forgetRecentlyViewed([]);
  });
});
