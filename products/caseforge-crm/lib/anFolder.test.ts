import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { offeredFolders, buildCreateBody, extraFolders, folderValue, otherFolderKind, OTHER_FOLDER, partyReady, takesParty, DOC_KINDS, DOC_OTHER_MAX, docOtherReady } from "./anFolder";

describe("offeredFolders", () => {
  it("offers FLA or CA only for a group the matter already holds a folder of", () => {
    expect(offeredFolders([])).toEqual([]);
    expect(offeredFolders([{ name: "Attendance-Notes-(FLA)-X", code: "FLA" }, { name: "Attendance-Notes-(OO)-X", code: "FLA" }])).toEqual(["FLA"]);
    expect(offeredFolders([{ name: "a", code: "CA" }, { name: "b", code: "FLA" }])).toEqual(["FLA", "CA"]);
    expect(offeredFolders([{ name: "Attendance-Notes-Other-X", code: "" }])).toEqual([]);
  });
});

const FORM = readFileSync(fileURLToPath(new URL("../components/AttendanceNoteForm.tsx", import.meta.url)), "utf8");

const base = {
  matterId: "9001",
  kind: "call" as const,
  caller: "client" as const,
  callerOther: "",
  noteText: "Spoke to her.",
  minutesSpent: null,
  pages: 0,
  docKind: "",
  folder: "" as const,
};

describe("FOLDER choice", () => {
  it("is never defaulted: nothing is sent until the person chooses", () => {
    expect(folderValue("", "")).toBe("");
    expect("attendance_folder" in buildCreateBody(base)).toBe(false);
    expect(buildCreateBody({ ...base, folder: "CA" }).attendance_folder).toBe("CA");
  });

  it("takes a fixed folder, a found folder, or Other with a name", () => {
    expect(folderValue("FLA", "")).toBe("FLA");
    expect(folderValue("Hearing notes", "")).toBe("Hearing notes");
    expect(folderValue(OTHER_FOLDER, "")).toBe("");
    expect(folderValue(OTHER_FOLDER, "  Mediation   notes ")).toBe("Mediation notes");
  });

  it("points order words typed under Other at FLA or CA, and refuses both together", () => {
    expect(otherFolderKind("NMO")).toBe("FLA");
    expect(otherFolderKind("oo")).toBe("FLA");
    expect(otherFolderKind("CAO")).toBe("CA");
    expect(otherFolderKind("PSO SIO")).toBe("CA");
    expect(otherFolderKind("Mediation")).toBe("custom");
    expect(otherFolderKind("NMO CAO")).toBe("");
    expect(folderValue(OTHER_FOLDER, "NMO CAO")).toBe("");
  });

  it("offers a matter's other attendance folders by name", () => {
    expect(extraFolders([{ name: "Attendance-Notes-(FLA)-X", code: "FLA" }, { name: "Attendance Notes X", code: "" }])).toEqual(["Attendance Notes X"]);
  });

  it("is a labelled, required select with no preset value", () => {
    expect(FORM).toContain('useState("")');
    expect(FORM).toContain('name="an-folder"');
    expect(FORM).toContain(">Folder</legend>");
    expect(FORM).toContain('data-shown={folder === OTHER_FOLDER}');
    expect(FORM).not.toContain("defaultFolder");
  });
});

describe("Perusal", () => {
  it("has no party and offers the document types", () => {
    expect(takesParty("perusal")).toBe(false);
    expect(takesParty("call")).toBe(true);
    expect(takesParty("preparation")).toBe(false);
    expect(takesParty("call")).toBe(true);
    expect(DOC_KINDS.map((d) => d.value)).toEqual(["application", "witness_statement", "bundle", "order", "letter", "other"]);
    expect(FORM).toContain(">Doc type</span>");
    expect(FORM).not.toContain("Document type");
    expect(FORM).toContain("takesParty(kind) && (");
  });

  it("is ready without a party, other kinds still need one", () => {
    expect(partyReady("perusal", "", "")).toBe(true);
    expect(partyReady("call", "", "")).toBe(false);
    expect(partyReady("call", "other", " ")).toBe(false);
    expect(partyReady("preparation", "", "")).toBe(true);
  });

  it("sends doc_kind and no caller", () => {
    const body = buildCreateBody({ ...base, kind: "perusal", caller: "", docKind: "order", pages: 12 });
    expect(body.doc_kind).toBe("order");
    expect(body.pages).toBe(12);
    expect("caller" in body).toBe(false);
    expect("doc_kind" in buildCreateBody({ ...base, docKind: "order" })).toBe(false);
  });

  it("a preparation sends doc_kind and no caller too", () => {
    const body = buildCreateBody({ ...base, kind: "preparation", caller: "", docKind: "order", pages: 3 });
    expect(body.doc_kind).toBe("order");
    expect("caller" in body).toBe(false);
  });

  it("Other shows a What was it? box that gates Create, and the typed text goes in the request", () => {
    expect(FORM).toContain('placeholder="What was it?"');
    expect(FORM).toContain('placeholder="Who was it?"');
    expect(FORM).toContain("docOtherReady(docKind, docOther)");
    expect(docOtherReady("other", "")).toBe(false);
    expect(docOtherReady("other", "  ")).toBe(false);
    expect(docOtherReady("other", "bank statement")).toBe(true);
    expect(docOtherReady("order", "")).toBe(true);
    const body = buildCreateBody({ ...base, kind: "perusal", caller: "", docKind: "other", docOther: "  bank\n statement ", pages: 2 });
    expect(body.doc_other).toBe("bank statement");
    expect("doc_other" in buildCreateBody({ ...base, kind: "perusal", caller: "", docKind: "order", docOther: "x", pages: 2 })).toBe(false);
    expect(String(buildCreateBody({ ...base, kind: "perusal", caller: "", docKind: "other", docOther: "x".repeat(200), pages: 2 }).doc_other)).toHaveLength(DOC_OTHER_MAX);
  });

  it("puts Folder in the top row beside Pages, not in the actions with Create", () => {
    const row = FORM.slice(FORM.indexOf('className="an-form-callers-row"'), FORM.indexOf('className="an-form-time"'));
    expect(row).toContain('name="an-folder"');
    expect(row.indexOf("{pagesField}")).toBeLessThan(row.indexOf('name="an-folder"'));
    const actions = FORM.slice(FORM.indexOf('className="an-form-actions"'));
    expect(actions).not.toContain('name="an-folder"');
    expect(FORM).not.toContain(">FOLDER<");
  });

  it("every select on the row shares the compact class", () => {
    const row = FORM.slice(FORM.indexOf('className="an-form-callers-row"'), FORM.indexOf('className="an-form-time"'));
    expect(row.match(/<select/g)?.length).toBe(row.match(/an-form-select an-form-compact/g)?.length);
  });

  it("labels Pages like the other labels and keeps it out of the time group", () => {
    expect(FORM).not.toContain("an-form-pages-label");
    const time = FORM.slice(FORM.indexOf('className="an-form-time"'), FORM.indexOf('className="an-form-time-toggle"'));
    expect(time).not.toContain("pagesField");
  });
});
