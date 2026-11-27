import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { groupAlerts, type OpsHealthAlert } from "./opsHealth";
import { dateTimeLabel, expiryLabel, spanLabel, trendLabel } from "./systemStatus";
import { stubSystemStatus } from "./stubSystemStatus";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const alert = (severity: OpsHealthAlert["severity"], category: OpsHealthAlert["category"], title: string): OpsHealthAlert => ({
  severity, category, title, next_action: "", kind: "state", age_minutes: null,
});

describe("the front page checks are gone; To check and Information are on System Health", () => {
  it("System health shows Needs you, the boxes, and Details folded away, not the old groups", () => {
    const page = read("../components/SystemHealthPanel.tsx");
    const sections = read("../components/SystemStatusSections.tsx");
    expect(page).not.toContain("For information");
    expect(page).not.toContain("Housekeeping");
    expect(page).not.toContain("Worth a look</h2>");
    expect(page).toContain("<NeedsYou");
    expect(sections).toContain(">Needs you<");
    expect(page).toContain('title="Also worth a look"');
    expect(page).toContain('title="Casework to check"');
  });

  it("the front page no longer draws To check or Information", () => {
    expect(existsSync(fileURLToPath(new URL("../components/FrontPageChecks.tsx", import.meta.url)))).toBe(false);
    expect(read("../components/Workspace.tsx")).not.toContain("FrontPageChecks");
  });

  it("splits housekeeping from info, and keeps amber and red health alerts apart", () => {
    const groups = groupAlerts([
      alert("amber", "housekeeping", "3 hearings waiting for review"),
      alert("info", "health", "Mail intake has items waiting"),
      alert("red", "health", "Workers failing"),
      alert("amber", "health", "Tunnel report stale"),
    ]);
    expect(groups.housekeeping.map((a) => a.title)).toEqual(["3 hearings waiting for review"]);
    expect(groups.info).toHaveLength(1);
    expect(groups.attention).toHaveLength(1);
    expect(groups.look).toHaveLength(1);
  });
});

describe("worker, backup and expiry wording", () => {
  it("words spans, trends and expiries", () => {
    expect(spanLabel(300)).toBe("5 min");
    expect(spanLabel(86400 * 3)).toBe("3 days");
    expect(trendLabel([1, 1, 2])).toHaveLength(3);
    const rows = stubSystemStatus().expiries.rows;
    expect(expiryLabel(rows[1])).toBe("12 days left");
    expect(expiryLabel(rows[2])).toBe("no expiry set");
    expect(expiryLabel(rows[3])).toContain("Application.Read.All");
    expect(dateTimeLabel("")).toBe("");
  });

  it("the stub has no Microsoft 365 row, an amber spend, a flagged worker and a no-data function", () => {
    const s = stubSystemStatus();
    expect(s.providers.providers.some((p) => p.key === "microsoft365")).toBe(false);
    expect(s.spend.tone).toBe("amber");
    expect(s.workers.boxes.flatMap((b) => b.rows).some((r) => r.overdue)).toBe(true);
    expect(s.functions.some((f) => f.state === "no_data")).toBe(true);
  });
});
