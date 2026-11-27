import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (name: string) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8");
const ROWS = read("./ClientRows.tsx");
const EDITS = read("./ClientEdits.tsx");
const PANEL = read("./DetailPanel.tsx");

describe("ClientRows.tsx parties editor", () => {
  it("uses a role box, not a slider", () => {
    expect(ROWS).not.toContain("RoleToggle");
    expect(ROWS).not.toContain("cf-segment");
    expect(ROWS).toContain("<RoleBox");
    expect(ROWS).toContain("ROLE_CHOICES.map");
    expect(ROWS).toContain('aria-label="Role (other)"');
    expect(ROWS).toContain('<Box label="Party">');
    expect(ROWS).toContain('choice === "Other" && (');
  });
  it("starts a new party as Respondent, and never says default", () => {
    expect(ROWS).toMatch(/"Applicant" : "Respondent"/);
    expect(ROWS.toLowerCase()).not.toContain("default");
  });
  it("labels the alias Alias and puts it under the last name in the name box", () => {
    expect(ROWS).not.toMatch(/AKA/);
    const parts = ROWS.slice(ROWS.indexOf("const PARTY_NAME_PARTS"), ROWS.indexOf("const NAME_PARTS"));
    expect(parts.indexOf("name_last")).toBeGreaterThan(-1);
    expect(parts.indexOf("aka_name")).toBeGreaterThan(parts.indexOf("name_last"));
    expect(ROWS).toContain("`Alias ${row.aka_name}`");
    expect(ROWS).toContain("Alias ${row.aka_name}");
    expect(ROWS).not.toContain('<Single label="AKA"');
  });
  it("says opponent / other party on the add button and unsaved label", () => {
    expect(ROWS).toContain('addLabel: "Add opponent / other party"');
    expect(ROWS).not.toMatch(/[Rr]espondent \/ other/);
    expect(ROWS).toContain('unsavedLabel: "Opponent / other parties"');
  });
  it("puts the remove button inside the party block, after the details", () => {
    const form = ROWS.slice(ROWS.indexOf("const form ="), ROWS.indexOf("const body = loading"));
    expect(form).toContain('<div className="row-editor-form-foot">{remove}</div>');
    expect(form.indexOf("{remove}")).toBeGreaterThan(form.indexOf("Work address"));
    expect(form).not.toContain("row-editor-form-head");
  });
  it("has no sex control or row for a party", () => {
    expect(ROWS).not.toContain("SexBox");
    expect(ROWS).not.toContain("sexText");
    expect(ROWS).not.toContain("sex_other");
    expect(ROWS).not.toContain('aria-label="Sex');
  });
});

describe("boxes in read and edit mode", () => {
  const labelsIn = (text: string, labels: string[]) => labels.map((l) => text.indexOf(`label="${l}"`));
  const ascending = (xs: number[]) => xs.every((x, i) => x > -1 && (i === 0 || x > xs[i - 1]));
  it("reads a party as separate boxes in the owner's order", () => {
    const kind = ROWS.slice(ROWS.indexOf("const PARTY_KIND"), ROWS.indexOf("const CHILD_KIND"));
    const order = ["Name", "Party", "Date of birth", "Telephone", "Email", "Address", "Work address"].map((l) => kind.indexOf(`label: "${l}"`));
    expect(ascending(order)).toBe(true);
    expect(kind).not.toContain("envelope");
  });
  it("reads a child as Name, PR, Date of birth, Sex, with Client when PR is blank", () => {
    const kind = ROWS.slice(ROWS.indexOf("const CHILD_KIND"), ROWS.indexOf("function useRows"));
    const order = ["Name", "PR", "Date of birth", "Sex"].map((l) => kind.indexOf(`label: "${l}"`));
    expect(ascending(order)).toBe(true);
    expect(kind).toContain('|| "Client"');
  });
  it("shows an empty box as Not on record, in the client's box classes", () => {
    expect(ROWS).toContain("Not on record");
    expect(ROWS).toContain('className="detail-field"');
    expect(ROWS).toContain("detail-field-value--empty");
    expect(ROWS).not.toContain("row-editor-row-name");
  });
  it("edits in the same order", () => {
    const form = ROWS.slice(ROWS.indexOf("const form ="), ROWS.indexOf("const body = loading"));
    const party = form.slice(0, form.indexOf(") : ("));
    expect(ascending(labelsIn(party, ["Name", "Date of birth", "Telephone", "Email", "Address", "Work address"]))).toBe(true);
    expect(party.indexOf("<RoleBox")).toBeGreaterThan(party.indexOf('label="Name"'));
    expect(party.indexOf("<RoleBox")).toBeLessThan(party.indexOf('label="Date of birth"'));
    const child = form.slice(form.indexOf(") : ("));
    expect(ascending([child.indexOf('label="Name"'), child.indexOf('label="PR"'), child.indexOf('label="Date of birth"'), child.indexOf('label="Sex"')])).toBe(true);
  });
});

describe("client Sex box", () => {
  it("is gone from the client's Basics", () => {
    expect(PANEL).not.toContain("InlineSex");
    expect(PANEL).not.toContain('label="Sex"');
    expect(EDITS).not.toContain("InlineSex");
    expect(EDITS).not.toContain("sex_other");
  });
});
