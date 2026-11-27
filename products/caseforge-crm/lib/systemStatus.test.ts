import { describe, expect, it } from "vitest";
import { attentionItems, bytesLabel, checkReason, cpuTone, levelTone, loadNote, loadSystemStatus, providerStateLabel, shrinkNote, zramLabel, type SystemBox, type WorkerCheck } from "./systemStatus";
import { stubSystemStatus } from "./stubSystemStatus";

describe("system status helpers", () => {
  it("is amber from 80 and red from 90, grey with no figure", () => {
    expect(levelTone(79.9)).toBe("ok");
    expect(levelTone(80)).toBe("amber");
    expect(levelTone(90)).toBe("red");
    expect(levelTone(null)).toBe("grey");
    expect(cpuTone(84)).toBe("ok");
    expect(cpuTone(95)).toBe("red");
  });

  it("words bytes and zram", () => {
    expect(bytesLabel(8 * 1024 ** 3)).toBe("8.0 GB");
    expect(bytesLabel(512 * 1024 ** 2)).toBe("512 MB");
    expect(bytesLabel(null)).toBe("n/a");
    const [dev, prod] = stubSystemStatus().boxes;
    expect(zramLabel(dev)).toContain("3.0:1");
    expect(zramLabel(prod as SystemBox)).toBe("none");
  });

  it("shows a declared outage as degraded and a failed check as grey, never as an outage", () => {
    const rows = stubSystemStatus().providers.providers;
    const by = (key: string) => providerStateLabel(rows.find((r) => r.key === key)!);
    expect(by("anthropic")).toEqual({ label: "Degraded", tone: "amber" });
    expect(by("openrouter")).toEqual({ label: "Could not check", tone: "grey" });
    expect(by("github").tone).toBe("ok");
  });

  it("loads null when the route fails", async () => {
    expect(await loadSystemStatus((async () => new Response("", { status: 403 })) as unknown as typeof fetch)).toBeNull();
    expect(await loadSystemStatus((async () => Promise.reject(new Error("x"))) as unknown as typeof fetch)).toBeNull();
  });
});

describe("why something is flagged", () => {
  const now = new Date("2026-11-24T12:00:00Z");
  const check = (over: Partial<WorkerCheck>): WorkerCheck => ({ name: "job", status: "down", last_ping: "2026-11-24T02:00:00Z", period_seconds: 900, ...over });

  it("tells a job that failed from one that went silent", () => {
    expect(checkReason(check({ last_kind: "fail" }), now)).toContain("reported a failure 10 h ago");
    expect(checkReason(check({}), now)).toContain("No check-in for 10 h; it should every 15 min");
    expect(checkReason(check({ last_ping: "" }), now)).toContain("never checked in");
    expect(checkReason(check({ status: "paused" }), now)).toContain("Paused on purpose");
    expect(checkReason(check({ status: "up" }), now)).toBe("");
  });

  it("lists red before amber, each with a reason, and never calls a stale report an outage", () => {
    const status = stubSystemStatus();
    const items = attentionItems(status, now);
    expect(items.length).toBeGreaterThan(0);
    expect(items.every((i) => i.why.length > 0)).toBe(true);
    const firstAmber = items.findIndex((i) => i.tone === "amber");
    expect(items.slice(firstAmber === -1 ? items.length : firstAmber).every((i) => i.tone === "amber")).toBe(true);

    const stale = items.find((i) => i.title.includes("has not reported"));
    expect(stale?.tone).toBe("amber");

    expect(items.some((i) => i.tone === "red" && i.title.includes("client-index-refresh") && i.why.includes("No check-in"))).toBe(true);
    expect(items.some((i) => i.title.startsWith("Backup qdrant") && i.why.includes("may be incomplete"))).toBe(true);
  });

  it("is quiet when nothing is wrong", () => {
    const status = stubSystemStatus();
    status.providers.providers.forEach((p) => (p.state = "operational"));
    status.boxes.forEach((b) => (b.stale = false));
    status.workers.boxes.forEach((b) => b.rows.forEach((r) => { r.overdue = false; r.last_result = "success"; r.check = null; }));
    status.workers.healthchecks.orphan_checks = [];
    status.backups.rows.forEach((b) => { b.status = "ok"; });
    status.expiries.rows.forEach((r) => { r.tone = "ok"; });
    status.spend.tone = "ok";
    expect(attentionItems(status, now).filter((i) => !i.title.includes("%"))).toEqual([]);
  });

  it("words the shrink and the load", () => {
    expect(shrinkNote([121 * 1024 ** 2, 60 * 1024 ** 2])).toBe("the newest backup is 60 MB, 50% of the one before (121 MB): it may be incomplete");
    expect(loadNote(3.2, 8)).toContain("not overloaded");
    expect(loadNote(8, 8)).toContain("busy");
    expect(loadNote(null, 8)).toBe("");
  });
});
