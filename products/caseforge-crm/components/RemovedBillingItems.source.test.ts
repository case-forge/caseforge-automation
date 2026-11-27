
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(fileURLToPath(new URL("./RemovedBillingItems.tsx", import.meta.url)), "utf8");
const PANEL = readFileSync(fileURLToPath(new URL("./DetailPanel.tsx", import.meta.url)), "utf8");

describe("RemovedBillingItems.tsx", () => {
  it("is never printed and starts closed", () => {
    expect(SOURCE).toContain('className="billing-removed no-print"');
    expect(SOURCE).toContain("useState(false)");
    expect(SOURCE).toContain("aria-expanded={expanded}");
  });

  it("shows who and when, and Undo calls the restore route", () => {
    expect(SOURCE).toContain("item.removed_by");
    expect(SOURCE).toContain("item.removed_utc");
    expect(SOURCE).toContain('"/api/billing/restore-item"');
    expect(SOURCE).toContain("Undo");
  });

  it("sits outside the printed bill on the Billing tab and refreshes it after Undo", () => {
    const printEnd = PANEL.indexOf("<RemovedBillingItems");
    expect(printEnd).toBeGreaterThan(PANEL.indexOf('className="billing-print-area"'));
    expect(PANEL.slice(printEnd, printEnd + 120)).toContain("onRestored={() => setRefresh((n) => n + 1)}");
  });
});
