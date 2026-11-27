import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  EMPTY_AN_FORM,
  clearWorkingCopy,
  deleteDraft,
  formatDraftTime,
  isBlankAnForm,
  loadDrafts,
  loadWorkingCopy,
  saveDraft,
  saveWorkingCopy,
} from "./anDrafts";

function fakeStorage() {
  const store = new Map<string, string>();
  return {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  };
}

beforeEach(() => {
  vi.stubGlobal("window", { localStorage: fakeStorage() });
});

describe("working copy", () => {
  it("comes back exactly as typed, per matter", () => {
    saveWorkingCopy("596", { caller: "court", callerOther: "", noteText: "Called Medway County Court." });
    expect(loadWorkingCopy("596").noteText).toBe("Called Medway County Court.");
    expect(loadWorkingCopy("597")).toEqual(EMPTY_AN_FORM);
  });

  it("is removed when the form is blank, so an empty box leaves nothing behind", () => {
    saveWorkingCopy("596", { caller: "court", callerOther: "", noteText: "x" });
    saveWorkingCopy("596", EMPTY_AN_FORM);
    expect(loadWorkingCopy("596")).toEqual(EMPTY_AN_FORM);
  });

  it("clearWorkingCopy drops it after a successful filing", () => {
    saveWorkingCopy("596", { caller: "client", callerOther: "", noteText: "x" });
    clearWorkingCopy("596");
    expect(loadWorkingCopy("596")).toEqual(EMPTY_AN_FORM);
  });

  it("does not write anything without a matter id", () => {
    saveWorkingCopy("", { caller: "client", callerOther: "", noteText: "x" });
    expect(loadWorkingCopy("")).toEqual(EMPTY_AN_FORM);
  });
});

describe("drafts", () => {
  const form = { caller: "other" as const, callerOther: "Ms Jones", noteText: "Asked about dates." };

  it("stamps each draft with when it was saved and lists newest first", () => {
    saveDraft("596", form, new Date("2026-09-24T09:00:00Z"));
    saveDraft("596", { ...form, noteText: "Second" }, new Date("2026-09-24T10:00:00Z"));
    const drafts = loadDrafts("596");
    expect(drafts.map((d) => d.noteText)).toEqual(["Second", "Asked about dates."]);
    expect(drafts[0].savedAt).toBe("2026-09-24T10:00:00.000Z");
    expect(drafts[0].callerOther).toBe("Ms Jones");
  });

  it("keeps drafts separate per matter and deletes one by id", () => {
    const a = saveDraft("596", form);
    saveDraft("597", form);
    expect(deleteDraft("596", a.id)).toEqual([]);
    expect(loadDrafts("597")).toHaveLength(1);
  });

  it("caps the list so storage cannot grow without limit", () => {
    for (let i = 0; i < 40; i++) saveDraft("596", { ...form, noteText: `n${i}` });
    expect(loadDrafts("596")).toHaveLength(30);
    expect(loadDrafts("596")[0].noteText).toBe("n39");
  });
});

describe("helpers", () => {
  it("treats whitespace-only text as blank", () => {
    expect(isBlankAnForm({ caller: "", callerOther: "  ", noteText: "\n" })).toBe(true);
    expect(isBlankAnForm({ caller: "court", callerOther: "", noteText: "" })).toBe(false);
  });

  it("formats an unreadable date as empty rather than throwing", () => {
    expect(formatDraftTime("nonsense")).toBe("");
  });
});

import { forgetSent, hasUnfinishedDraft, isWorkingFromDraft, loadSent, markWorkingFromDraft, rememberSent } from "./anDrafts";

describe("sent notes and the unfinished-draft rule", () => {
  const form = { caller: "client" as const, callerOther: "", noteText: "rang about her order" };

  it("keeps a sent note until it is forgotten, newest first, once per draft id", () => {
    rememberSent("601", "d1", form);
    rememberSent("601", "d2", { ...form, noteText: "second" });
    rememberSent("601", "d1", { ...form, noteText: "d1 again" });
    expect(loadSent("601").map((n) => n.draftId)).toEqual(["d1", "d2"]);
    expect(loadSent("601")[0].noteText).toBe("d1 again");
    forgetSent("601", "d1");
    forgetSent("601", "d2");
    expect(loadSent("601")).toEqual([]);
  });

  it("counts a saved draft, or a box that began as one, as unfinished; a blank slate is not", () => {
    expect(hasUnfinishedDraft("601")).toBe(false);
    saveDraft("601", form);
    expect(hasUnfinishedDraft("601")).toBe(true);
    deleteDraft("601", loadDrafts("601")[0].id);
    expect(hasUnfinishedDraft("601")).toBe(false);
    markWorkingFromDraft("601", true);
    expect(isWorkingFromDraft("601") && hasUnfinishedDraft("601")).toBe(true);
    markWorkingFromDraft("601", false);
    expect(hasUnfinishedDraft("601")).toBe(false);
  });

  it("keeps each client's drafts separate", () => {
    saveDraft("601", form);
    expect(hasUnfinishedDraft("598")).toBe(false);
  });
});

import { kindOf } from "./anDrafts";

describe("note type in drafts", () => {
  it("defaults to a call, for anything saved before there were types", () => {
    expect(kindOf({})).toBe("call");
    expect(kindOf({ kind: "nonsense" })).toBe("call");
    expect(kindOf({ kind: "bundle" })).toBe("bundle");
  });

  it("reads a letter note saved earlier as the note that replaced it", () => {
    expect(kindOf({ kind: "letter_in" })).toBe("perusal");
    expect(kindOf({ kind: "letter_out" })).toBe("preparation");
  });

  it("keeps a chosen type across a reload even before anything is typed, but forgets a plain call", () => {
    saveWorkingCopy("248", { caller: "", callerOther: "", noteText: "", kind: "preparation" });
    expect(loadWorkingCopy("248").kind).toBe("preparation");
    saveWorkingCopy("248", { caller: "", callerOther: "", noteText: "", kind: "call" });
    expect(loadWorkingCopy("248")).toEqual({ caller: "", callerOther: "", noteText: "", kind: "call" });
  });

  it("stores the type with a saved draft, and a type alone is not a note", () => {
    saveDraft("248", { caller: "respondent", callerOther: "", noteText: "sent letter", kind: "perusal" });
    expect(kindOf(loadDrafts("248")[0])).toBe("perusal");
    expect(isBlankAnForm({ caller: "", callerOther: "", noteText: "", kind: "bundle" })).toBe(true);
  });
});
