import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { filedLabel } from "@/lib/types";

describe("filedLabel", () => {
  it("names the pages a bundle note billed", () => {
    expect(filedLabel({ billing_removed: false, bundle_pages: 312 })).toBe("Filed and billed: 312 pages.");
    expect(filedLabel({ billing_removed: false, bundle_pages: 1 })).toBe("Filed and billed: 1 page.");
  });

  it("says a note that billed nothing was not billed", () => {
    expect(filedLabel({ billing_removed: false, bundle_pages: null, billing_note: "Bundle not found, page count needed" })).toBe(
      "Filed, not billed.",
    );
  });

  it("keeps the plain wording for other notes and a removed charge", () => {
    expect(filedLabel({ billing_removed: false })).toBe("Filed and billed.");
    expect(filedLabel({ billing_removed: true, bundle_pages: 40 })).toBe("Filed. Taken off the bill.");
  });
});

describe("AttendanceNoteForm.tsx", () => {
  const SOURCE = readFileSync(fileURLToPath(new URL("../components/AttendanceNoteForm.tsx", import.meta.url)), "utf8");

  it("has no bundle or letter-note wording: a perusal or preparation takes a time and a page count", () => {
    expect(SOURCE).not.toContain("takesNoTime");
    expect(SOURCE).not.toContain("Bundles are billed per page");
    expect(SOURCE).not.toContain("LAA-Billing");
    expect(SOURCE).not.toContain("Need an envelope");
    expect(SOURCE).toContain('name="an-pages"');
  });
});
