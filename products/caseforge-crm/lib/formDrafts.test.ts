import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  DRAFT_MAX_AGE_MS,
  DRAFT_PREFIX,
  changedValues,
  clearDraft,
  draftKey,
  draftTimeLabel,
  loadDraft,
  pruneExpiredDrafts,
  saveDraft,
} from "./formDrafts";

function fakeStorage() {
  const store = new Map<string, string>();
  return {
    store,
    get length() {
      return store.size;
    },
    key: (i: number) => [...store.keys()][i] ?? null,
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  };
}

let storage: ReturnType<typeof fakeStorage>;
beforeEach(() => {
  storage = fakeStorage();
  vi.stubGlobal("window", { localStorage: storage });
});

const NOW = Date.UTC(2026, 9, 21, 13, 32);

describe("form drafts", () => {
  it("keeps one draft per matter and form, and gives it back as saved", () => {
    saveDraft("STUB-001", "client-edit", { changes: { name_last: "Alphatest" }, note: "casing" }, NOW);
    saveDraft("STUB-002", "client-edit", { changes: { name_last: "Other" }, note: "" }, NOW);
    expect(loadDraft("STUB-001", "client-edit", NOW)).toEqual({ savedAt: NOW, data: { changes: { name_last: "Alphatest" }, note: "casing" } });
    expect(loadDraft("STUB-001", "row-editor-children", NOW)).toBeNull();
    expect(loadDraft("STUB-002", "client-edit", NOW)?.data).toEqual({ changes: { name_last: "Other" }, note: "" });
  });

  it("files a form with no matter under none", () => {
    expect(draftKey(null, "todo-add")).toBe(`${DRAFT_PREFIX}none:todo-add`);
    expect(draftKey("", "hearing-new")).toBe(`${DRAFT_PREFIX}none:hearing-new`);
    expect(draftKey(614, "todo-add")).toBe(`${DRAFT_PREFIX}614:todo-add`);
  });

  it("clears a draft on save or cancel", () => {
    saveDraft("STUB-001", "todo-add", { text: "ring the court" }, NOW);
    clearDraft("STUB-001", "todo-add");
    expect(loadDraft("STUB-001", "todo-add", NOW)).toBeNull();
  });

  it("drops a draft older than seven days, and keeps one just inside", () => {
    saveDraft("STUB-001", "todo-add", { text: "old" }, NOW - DRAFT_MAX_AGE_MS - 1);
    saveDraft("STUB-002", "todo-add", { text: "recent" }, NOW - DRAFT_MAX_AGE_MS + 60_000);
    expect(loadDraft("STUB-001", "todo-add", NOW)).toBeNull();
    expect(storage.store.has(draftKey("STUB-001", "todo-add"))).toBe(false);
    expect(loadDraft("STUB-002", "todo-add", NOW)?.data).toEqual({ text: "recent" });
  });

  it("prunes every expired or unreadable draft and leaves other storage alone", () => {
    saveDraft("STUB-001", "todo-add", { text: "old" }, NOW - DRAFT_MAX_AGE_MS - 1);
    saveDraft("STUB-002", "todo-add", { text: "recent" }, NOW);
    storage.setItem(`${DRAFT_PREFIX}STUB-003:client-edit`, "{not json");
    storage.setItem("caseforge-client-viewer:an-work:596", "{}");
    pruneExpiredDrafts(NOW);
    expect([...storage.store.keys()].sort()).toEqual([draftKey("STUB-002", "todo-add"), "caseforge-client-viewer:an-work:596"].sort());
  });

  it("never throws when storage is missing or refuses", () => {
    vi.stubGlobal("window", {});
    expect(() => saveDraft("STUB-001", "todo-add", { text: "x" })).not.toThrow();
    expect(loadDraft("STUB-001", "todo-add")).toBeNull();
    vi.stubGlobal("window", {
      localStorage: {
        getItem: () => {
          throw new Error("blocked");
        },
        setItem: () => {
          throw new Error("full");
        },
        removeItem: () => {
          throw new Error("blocked");
        },
        key: () => null,
        length: 0,
      },
    });
    expect(() => saveDraft("STUB-001", "todo-add", { text: "x" })).not.toThrow();
    expect(loadDraft("STUB-001", "todo-add")).toBeNull();
    expect(() => clearDraft("STUB-001", "todo-add")).not.toThrow();
    expect(() => pruneExpiredDrafts()).not.toThrow();
  });

  it("keeps only the values that differ from what is stored", () => {
    expect(changedValues({ a: "1", b: "two", c: true }, { a: "1", b: "2", c: false })).toEqual({ b: "two", c: true });
    expect(changedValues({ a: "1" }, { a: "1" })).toEqual({});
  });

  it("says when a draft was kept, London time", () => {
    expect(draftTimeLabel(NOW)).toBe("14:32 on Wed 21 Oct");
  });
});
