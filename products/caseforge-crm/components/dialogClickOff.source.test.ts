
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const read = (p: string) => readFileSync(join(__dirname, p), "utf8");

describe("form dialogs", () => {
  it("are not closed by a click on the dim layer", () => {
    for (const f of ["NewClientButton.tsx", "MergeClientButton.tsx", "RemoveClientButton.tsx"]) {
      expect(read(f), f).not.toMatch(/className="new-client-backdrop"[^>]*onClick/);
    }
  });
  it("have one way out once finished", () => {
    expect(read("MergeClientButton.tsx")).toContain("{!merged && <DialogClose");
    expect(read("NewClientButton.tsx")).toContain("{!(made || manualMade) && <DialogClose");
  });
  it("scroll on the layer, not inside the box, and the merge box is wide only with a preview", () => {
    const css = read("../app/newclient.css");
    expect(css).toMatch(/\.new-client-backdrop \{[^}]*overflow-y: auto/);
    expect(css).not.toMatch(/\.new-client-dialog \{[^}]*overflow-y/);
    expect(css).toMatch(/\.new-client-dialog\.merge-dialog--wide \{/);
    expect(read("MergeClientButton.tsx")).toContain('preview && !merged ? " merge-dialog--wide" : ""');
  });
  it("the portal alert is one sentence with See list, and Open portal at its end", () => {
    const src = read("PortalAlert.tsx");
    expect(src).not.toContain("<strong>Portal case</strong>");
    expect(src).toContain("only takes applications through HMCTS Access.");
    expect(src).toContain("For FL401/C100, attach witness statement, draft orders and notice of acting as supporting evidence.");
    expect(src.lastIndexOf("See list")).toBeLessThan(src.lastIndexOf("For FL401/C100"));
    expect(src.lastIndexOf("For FL401/C100")).toBeLessThan(src.lastIndexOf("Open portal"));
  });
});
