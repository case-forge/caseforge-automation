import { describe, expect, it } from "vitest";
import { REFRESH_MS, backupFraction, pieSlices, shareLabel, sizeLabel, storageGroups, updatedLabel, type StorageRow } from "./storageStatus";
import { stubStorageStatus } from "./stubStorageStatus";

const GB = 10 ** 9;
const row = (key: string, group: string, gb: number | null, total: number | null = null): StorageRow => ({
  key, group, name: key, bytes: gb === null ? null : gb * GB, total_bytes: total === null ? null : total * GB, state: gb === null ? "unknown" : "ok", note: "",
});

describe("storage helpers", () => {
  it("builds the donut from the cloud drives only, in a fixed order, and leaves out what is not measured", () => {
    const slices = pieSlices([row("sharepoint_recycle", "cloud", 600), row("personal_live", "cloud", 300), row("sharepoint_live", "cloud", 100), row("personal_recycle", "cloud", null), row("server_root", "server", 50)]);
    expect(slices.map((s) => s.key)).toEqual(["personal_live", "sharepoint_live", "sharepoint_recycle"]);
    expect(slices.reduce((n, s) => n + s.fraction, 0)).toBeCloseTo(1);
    expect(slices[0].fraction).toBeCloseTo(0.3);
    expect(slices.every((s) => s.colour.startsWith("var(--"))).toBe(true);
  });
  it("gives no slices when nothing is measured", () => {
    expect(pieSlices([row("personal_live", "cloud", null)])).toEqual([]);
  });
  it("says not measured for an unknown size, never zero", () => {
    expect(sizeLabel({ bytes: null })).toBe("not measured");
    expect(sizeLabel({ bytes: 5 * GB })).toMatch(/GB$/);
  });
  it("measures the backup folder against its target", () => {
    expect(backupFraction([row("backup_folder", "backup", 34, 40)])).toBeCloseTo(0.85);
    expect(backupFraction([row("backup_folder", "backup", null, 40)])).toBeNull();
    expect(backupFraction([])).toBeNull();
  });
  it("groups the holders in reading order and drops empty groups", () => {
    const groups = storageGroups([row("a", "server", 1), row("b", "backup", 1), row("c", "cloud", 1)]);
    expect(groups.map((g) => g.id)).toEqual(["backup", "server"]);
  });
  it("labels the share and the update time", () => {
    expect(shareLabel(0.004)).toBe("under 1%");
    expect(shareLabel(0.624)).toBe("62%");
    expect(updatedLabel("")).toBe("Not updated yet");
    expect(updatedLabel("2026-11-26T14:05:00Z")).toMatch(/^Updated \d\d:\d\d$/);
  });
  it("refreshes every minute", () => {
    expect(REFRESH_MS).toBe(60_000);
  });
  it("has a stub whose rows all carry the contract's fields", () => {
    const stub = stubStorageStatus();
    expect(stub.rows.length).toBeGreaterThan(5);
    for (const r of stub.rows) expect(Object.keys(r).sort()).toEqual(["bytes", "group", "key", "name", "note", "state", "total_bytes"]);
    expect(pieSlices(stub.rows).length).toBe(4);
  });
});
