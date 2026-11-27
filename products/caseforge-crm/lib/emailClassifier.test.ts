import { describe, expect, it, vi } from "vitest";
import { addEntry, auditLine, groupLists, labelFor, loadEmailClassifier, removeAdded, saveEmailClassifier, stopUsing, useAgain, type EmailClassifierView } from "./emailClassifier";

const view: EmailClassifierView = {
  lists: {
    court_domains: { default: ["court.example", "tribunal.example"], added: ["own.example"], removed: [], effective: [] },
    gp_keywords: { default: ["repeat prescription"], added: [], removed: ["repeat prescription"], effective: [] },
    gp_domains: { default: ["nhs.example"], added: [], removed: [], effective: [] },
    odd_list: { default: [], added: [], removed: [], effective: [] },
  },
  audit: [],
};

describe("labels", () => {
  it("gives plain labels, by prefix for families and by name for an unknown list", () => {
    expect(labelFor("chambers_domains").label).toBe("Chambers (Counsel)");
    expect(labelFor("drug_test_keywords").label).toBe("Drug test labs");
    expect(labelFor("contact_centre_domains").label).toBe("Contact centres");
    expect(labelFor("odd_list")).toEqual({ label: "odd_list", feeds: "" });
  });
  it("groups lists that share a label", () => {
    const groups = groupLists(view);
    expect(groups.map((g) => g.label)).toEqual(["Courts", "GPs", "odd_list"]);
    expect(groups[1].names).toEqual(["gp_keywords", "gp_domains"]);
  });
});

describe("body helpers", () => {
  it("adds an entry and keeps everything else", () => {
    expect(addEntry(view, "court_domains", "  New.Example ")).toEqual({
      add: { court_domains: ["own.example", "New.Example"] },
      remove: { gp_keywords: ["repeat prescription"] },
    });
  });
  it("ignores a blank, a repeated and a built-in entry", () => {
    for (const text of ["", "  ", "OWN.example", "court.example"]) expect(addEntry(view, "court_domains", text).add).toEqual({ court_domains: ["own.example"] });
  });
  it("removes one of the person's own entries and drops an emptied list", () => {
    expect(removeAdded(view, "court_domains", "own.example").add).toEqual({});
  });
  it("stops using a built-in entry once, and uses it again", () => {
    const stopped = stopUsing(view, "court_domains", "court.example");
    expect(stopped.remove.court_domains).toEqual(["court.example"]);
    expect(stopUsing(view, "gp_keywords", "repeat prescription").remove.gp_keywords).toEqual(["repeat prescription"]);
    expect(stopUsing(view, "court_domains", "not built in").remove.court_domains).toBeUndefined();
    expect(useAgain(view, "gp_keywords", "repeat prescription").remove).toEqual({});
  });
  it("does not change the view it was given", () => {
    addEntry(view, "court_domains", "x.example");
    expect(view.lists.court_domains.added).toEqual(["own.example"]);
  });
  it("writes an audit line from whatever parts there are", () => {
    expect(auditLine({ at: "27 Oct", who: "a@b.example", summary: "Changed" })).toBe("27 Oct · a@b.example · Changed");
    expect(auditLine({ summary: "Changed" })).toBe("Changed");
  });
});

describe("loading and saving", () => {
  it("reads a good answer and refuses an odd one", async () => {
    const ok = vi.fn().mockResolvedValue(new Response(JSON.stringify(view)));
    expect((await loadEmailClassifier(ok)).state).toBe("ok");
    const bad = vi.fn().mockResolvedValue(new Response(JSON.stringify({ nope: 1 })));
    expect((await loadEmailClassifier(bad)).state).toBe("error");
  });
  it("returns the hub's own refusal", async () => {
    const refused = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Too long" }), { status: 422 }));
    expect(await saveEmailClassifier({ add: {}, remove: {} }, refused)).toEqual({ ok: false, message: "Too long" });
    const down = vi.fn().mockRejectedValue(new Error("x"));
    expect((await saveEmailClassifier({ add: {}, remove: {} }, down)).ok).toBe(false);
  });
});

describe("lists whose category is no longer a folder", () => {
  it("say they feed Others, noted with the old name", () => {
    expect(labelFor("gp_keywords").feeds).toBe("Others (GP)");
    expect(labelFor("school_domains").feeds).toBe("Others (School)");
    expect(labelFor("hospital_domains").feeds).toBe("Others (Hospital)");
    expect(labelFor("newsletter_patterns").feeds).toBe("Junk");
    expect(labelFor("court_domains").feeds).toBe("Court");
  });
});
