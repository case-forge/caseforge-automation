import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  datedDraftsBetween,
  deleteHearingDraft,
  draftEvent,
  draftLabel,
  draftsForMatter,
  hasDraftContent,
  loadHearingDrafts,
  saveHearingDraft,
} from "./hearingDrafts";

function fakeStorage() {
  const store = new Map<string, string>();
  return {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  };
}

beforeEach(() => {
  vi.stubGlobal("window", { localStorage: fakeStorage(), addEventListener: () => undefined, removeEventListener: () => undefined });
});

describe("hearing drafts", () => {
  it("a form with only its starting values is not a draft; typing something makes one", () => {
    expect(hasDraftContent({})).toBe(false);
    expect(hasDraftContent({ matter_id: "12" })).toBe(false);
    expect(hasDraftContent({ matter_id: "12", court: "  " })).toBe(false);
    expect(hasDraftContent({ court: "Exampletown" })).toBe(true);
    expect(hasDraftContent({ is_final: true })).toBe(true);
  });

  it("saving keeps the draft, newest first, and a draft saved again by id replaces itself", () => {
    const a = saveHearingDraft({ matterId: "12", clientName: "A Client", values: { court: "One" } }, new Date("2026-11-07T10:00:00Z"));
    const b = saveHearingDraft({ matterId: "13", values: { hearing_date: "2026-12-01" } }, new Date("2026-11-07T11:00:00Z"));
    expect(loadHearingDrafts().map((d) => d.id)).toEqual([b.id, a.id]);
    const again = saveHearingDraft({ id: a.id, matterId: "12", clientName: "A Client", values: { court: "Two" } }, new Date("2026-11-07T12:00:00Z"));
    expect(again.id).toBe(a.id);
    const list = loadHearingDrafts();
    expect(list).toHaveLength(2);
    expect(list[0].values.court).toBe("Two");
  });

  it("discarding removes only that draft; a broken store reads as no drafts", () => {
    const a = saveHearingDraft({ matterId: "12", values: { court: "One" } });
    saveHearingDraft({ matterId: "13", values: { court: "Two" } });
    deleteHearingDraft(a.id);
    expect(loadHearingDrafts().map((d) => d.values.court)).toEqual(["Two"]);
    window.localStorage.setItem("caseforge-client-viewer:hearing-drafts", "not json");
    expect(loadHearingDrafts()).toEqual([]);
  });

  it("a draft is only ever in the browser: it never calls the server", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    saveHearingDraft({ matterId: "12", values: { court: "One" } });
    deleteHearingDraft("none");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("per client and per date: a client sees its own, the calendar sees the dated ones in range", () => {
    saveHearingDraft({ matterId: "12", values: { hearing_date: "2026-11-20", court: "One" } });
    saveHearingDraft({ matterId: "12", values: { court: "No date" } });
    saveHearingDraft({ matterId: "", values: { hearing_date: "2027-01-05" } });
    const all = loadHearingDrafts();
    expect(draftsForMatter(all, "12")).toHaveLength(2);
    expect(draftsForMatter(all, "")).toHaveLength(1);
    expect(datedDraftsBetween(all, "0000-01-01")).toHaveLength(2);
    expect(datedDraftsBetween(all, "2026-11-01", "2026-12-01").map((d) => d.values.court)).toEqual(["One"]);
  });

  it("names a draft by its client, else its case number", () => {
    expect(draftLabel({ id: "1", savedAt: "", matterId: "1", clientName: "A Client", values: {} })).toBe("A Client");
    expect(draftLabel({ id: "1", savedAt: "", matterId: "", values: { case_ref: "ZZ26F00000" } })).toBe("ZZ26F00000");
    expect(draftLabel({ id: "1", savedAt: "", matterId: "", values: {} })).toBe("Hearing draft");
  });
});

describe("a draft on the calendar", () => {
  it("sits on its date, untimed all day or at its time, dashed (hearing-ev--draft), and is never a hearing event", () => {
    const untimed = draftEvent({ id: "a", savedAt: "", matterId: "1", clientName: "A Client", values: { hearing_date: "2026-11-20" } });
    expect(untimed).toMatchObject({ id: "draft-a", start: "2026-11-20", allDay: true, title: "DRAFT - A Client" });
    expect(untimed.classNames).toContain("hearing-ev--draft");
    expect(untimed.classNames).not.toContain("hearing-ev--review");
    expect(untimed.extendedProps).not.toHaveProperty("hearing");
    const timed = draftEvent({ id: "b", savedAt: "", matterId: "1", values: { hearing_date: "2026-11-20", hearing_time: "10:30" } });
    expect(timed).toMatchObject({ start: "2026-11-20T10:30:00", allDay: false });
  });
});
