import { describe, expect, it, vi } from "vitest";
import { checkedLabel, durationLabel, groupAlerts, loadOpsHealth, overallLabel, settingsSummary, type OpsHealthResponse } from "./opsHealth";
import { stubOpsHealth } from "./stubOpsHealth";

const red = stubOpsHealth("red") as OpsHealthResponse;

describe("System health", () => {
  it("words each overall state calmly", () => {
    expect(overallLabel(stubOpsHealth("clear") as OpsHealthResponse).label).toBe("All clear");
    expect(overallLabel(stubOpsHealth("amber") as OpsHealthResponse)).toMatchObject({ label: "Worth a look", tone: "look" });
    expect(overallLabel(red)).toMatchObject({ label: "Needs attention", tone: "attention" });
    expect(overallLabel(stubOpsHealth("none") as OpsHealthResponse).label).toBe("No report yet");
    expect(overallLabel({ ...red, overall_severity: "unknown" }).label).toBe("Not known");
  });

  it("says when the report is out of date", () => {
    expect(settingsSummary(stubOpsHealth("stale") as OpsHealthResponse)).toBe("All clear, out of date");
    expect(overallLabel(stubOpsHealth("stale") as OpsHealthResponse).line).toBe("At the last check: everything is working.");
    expect(settingsSummary(red)).toBe("Needs attention");
    expect(settingsSummary(stubOpsHealth("none") as OpsHealthResponse)).toBe("No report yet");
  });

  it("groups health by severity and keeps housekeeping apart", () => {
    const groups = groupAlerts(red.alerts);
    expect(groups.attention.map((a) => a.severity)).toEqual(["red"]);
    expect(groups.look.every((a) => a.severity === "amber" && a.category === "health")).toBe(true);
    expect(groups.info.every((a) => a.category === "health")).toBe(true);
    expect(groups.housekeeping.length).toBe(2);
    expect(groups.housekeeping.some((a) => a.severity === "amber")).toBe(true);
  });

  it("formats durations and the check time", () => {
    expect(durationLabel(null)).toBe("");
    expect(durationLabel(0)).toBe("just now");
    expect(durationLabel(12)).toBe("12 min");
    expect(durationLabel(125)).toBe("2 h 5 min");
    expect(durationLabel(120)).toBe("2 h");
    expect(durationLabel(4 * 1440)).toBe("4 days");
    const label = checkedLabel({ ...red, generated_at: "2026-10-16T11:50:00Z", snapshot_age_minutes: 10 });
    expect(label).toContain("12:50");
    expect(label).toContain("(10 min ago)");
    expect(checkedLabel(stubOpsHealth("none") as OpsHealthResponse)).toBe("");
  });

  it("turns a 403 into hidden and a failure into error", async () => {
    const respond = (status: number, body: unknown = {}) => vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
    expect(await loadOpsHealth(respond(403))).toEqual({ state: "hidden" });
    expect(await loadOpsHealth(respond(502))).toEqual({ state: "error" });
    expect(await loadOpsHealth(vi.fn().mockRejectedValue(new Error("offline")))).toEqual({ state: "error" });
    const ok = await loadOpsHealth(respond(200, red));
    expect(ok.state).toBe("ok");
  });
});
