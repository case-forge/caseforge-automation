
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(fileURLToPath(new URL("./ClientEdits.tsx", import.meta.url)), "utf8");

describe("ClientEdits.tsx", () => {
  it("has Apply changes, Cancel, Save as draft in that order", () => {
    const apply = SOURCE.indexOf('"Apply changes"}\n');
    const cancel = SOURCE.indexOf("onClick={ed.cancelEdit} disabled");
    const draft = SOURCE.indexOf("onClick={ed.saveAsDraft}");
    expect(apply).toBeGreaterThan(-1);
    expect(apply < cancel && cancel < draft).toBe(true);
    expect(SOURCE).toContain("Save as draft");
  });

  it("keeps the draft, closes the box, and restores it on Edit with the restored note", () => {
    expect(SOURCE).toContain('SAVED_DRAFT_FORM = "client-edit-saved"');
    expect(SOURCE).toContain("saveDraft(matterId, SAVED_DRAFT_FORM");
    expect(SOURCE).toContain("loadDraft<{ changes: Record<string, string>; note: string }>(matterId, SAVED_DRAFT_FORM)");
    expect(SOURCE).toContain("kept.restoredAt ?? draftRestoredAt");
  });

  it("explains a dropped call instead of showing the browser's wording", () => {
    expect(SOURCE).toContain('describeFetchError(err, "Could not apply the changes")');
    expect(SOURCE).not.toContain('err instanceof Error ? err.message : "Could not apply the changes"');
  });
});
