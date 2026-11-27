import { describe, expect, it } from "vitest";
import { groupExpiries, plainAction, schedulesSummary, spendItem, tierAlerts } from "./healthTiers";
import type { OpsHealthAlert } from "./opsHealth";
import type { ExpiryRow, SystemStatusResponse } from "./systemStatus";

const alert = (over: Partial<OpsHealthAlert>): OpsHealthAlert => ({
  severity: "amber",
  category: "health",
  title: "x",
  next_action: "",
  kind: "k",
  age_minutes: null,
  ...over,
});

describe("tierAlerts", () => {
  it("puts red alerts and the listed amber ones in Needs you, and everything else in Details", () => {
    const tiers = tierAlerts([
      alert({ severity: "red", title: "The database is down" }),
      alert({ title: "OpenRouter key spend cap nearly exhausted" }),
      alert({ title: "A company reference is held by more than one matter" }),
      alert({ severity: "info", title: "Client-exposure detector: usage over the soft threshold" }),
      alert({ severity: "red", category: "housekeeping", title: "66 chase to-dos open" }),
    ]);
    expect(tiers.needsYou.map((a) => a.title)).toEqual(["The database is down", "OpenRouter key spend cap nearly exhausted"]);
    expect(tiers.details).toHaveLength(3);
  });
});

describe("plainAction", () => {
  it("keeps a plain sentence and drops a developer's command", () => {
    expect(plainAction("Raise the cap in OpenRouter or leave it as it is.")).toContain("Raise the cap");
    expect(plainAction("Run python3 tools/monitoring/signin_watch.py ack --all.")).toBe("");
    expect(plainAction("On the production box run systemctl status clamav-daemon")).toBe("");
    expect(plainAction("")).toBe("");
  });
});

describe("groupExpiries", () => {
  it("counts secrets with no expiry instead of listing each", () => {
    const row = (state: string): ExpiryRow => ({ kind: "secret", name: "n", expires_at: "", days_left: null, state, tone: "ok", note: "", renew_url: "" });
    const groups = groupExpiries([row("no_expiry"), row("no_expiry"), row("ok")]);
    expect(groups.noExpiry).toBe(2);
    expect(groups.dated).toHaveLength(1);
  });
});

describe("spendItem", () => {
  const spend = (over: Partial<SystemStatusResponse["spend"]>): SystemStatusResponse["spend"] => ({
    available: true, note: "", generated_at: "", usage: 36.3, usage_daily: 5.08, limit: 6, limit_remaining: 0.92, remaining_fraction: 0.15, tone: "amber", ...over,
  });
  it("speaks only when the cap is running out", () => {
    expect(spendItem(spend({}))?.title).toBe("OpenRouter key: $0.92 of $6.00 left");
    expect(spendItem(spend({ tone: "ok" }))).toBeNull();
    expect(spendItem(spend({ limit: null }))).toBeNull();
  });
});

describe("schedulesSummary", () => {
  it("counts on time, failed and overdue across the boxes", () => {
    const row = (over: object) => ({ name: "n", kind: "timer", description: "", schedule: "", last_run: "", last_result: "success", next_run: "", period_seconds: null, overdue: false, check: null, no_check: false, tone: "ok", ...over });
    const status = { workers: { boxes: [{ box: "prod", label: "p", available: true, generated_at: "", age_minutes: 0, stale: false, rows: [row({}), row({}), row({ last_result: "failed" }), row({ overdue: true })] }] } } as unknown as SystemStatusResponse;
    expect(schedulesSummary(status)).toBe("2 on time, 1 failed, 1 overdue");
  });
});
