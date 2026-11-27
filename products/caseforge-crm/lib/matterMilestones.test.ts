import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  MILESTONES,
  boardDate,
  emptyMilestones,
  fromLocalInputValue,
  isManualMilestone,
  milestoneSourceNote,
  milestoneTime,
  toLocalInputValue,
} from "./matterMilestones";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

describe("the milestones", () => {
  it("are in the agreed order, and only legal aid done and invoice paid can be set by hand", () => {
    expect(MILESTONES.map((m) => m.key)).toEqual(["contacted", "papers_signed", "filed", "service_requested", "served", "legal_aid_done", "invoice_paid", "laa_interim_cert", "laa_final_cert"]);
    expect(MILESTONES.filter((m) => isManualMilestone(m.key)).map((m) => m.key)).toEqual(["legal_aid_done", "invoice_paid"]);
    expect(isManualMilestone("filed")).toBe(false);
  });

  it("start empty, with only the two manual ones settable", () => {
    const empty = emptyMilestones();
    expect(Object.values(empty).every((v) => v.at === "")).toBe(true);
    expect(Object.entries(empty).filter(([, v]) => v.can_set).map(([k]) => k)).toEqual(["legal_aid_done", "invoice_paid"]);
  });

  it.skipIf(!existsSync(fileURLToPath(new URL("../../../tools/onboarding/pipeline/milestones.py", import.meta.url))))("agree with the hub's list in milestones.py", () => {
    const py = read("../../../tools/onboarding/pipeline/milestones.py");
    for (const { key, label } of MILESTONES) expect(py).toContain(`("${key}", "${label}")`);
  });
});

describe("milestoneTime", () => {
  it("shows London time with the date and the minute, so a summer time reads an hour on", () => {
    expect(milestoneTime("2026-10-23T09:15:00Z")).toBe("23 Oct 2026, 10:15");
    expect(milestoneTime("2026-01-15T09:15:00Z")).toBe("15 Jan 2026, 09:15");
  });

  it("is empty for nothing recorded or not a time", () => {
    expect(milestoneTime("")).toBe("");
    expect(milestoneTime("yesterday")).toBe("");
  });

  it("gives the date alone for the older columns", () => {
    expect(boardDate("2026-10-23T09:15:00Z")).toBe("23 Oct 2026");
    expect(boardDate("2026-10-30")).toBe("30 Oct 2026");
    expect(boardDate("")).toBe("");
  });
});

describe("the datetime-local helpers", () => {
  it("write an instant as London time the input accepts, and read back only a complete value", () => {
    expect(toLocalInputValue(new Date("2026-10-23T09:15:00Z"))).toBe("2026-10-23T10:15");
    expect(toLocalInputValue(new Date("2026-01-15T09:15:00Z"))).toBe("2026-01-15T09:15");
    expect(fromLocalInputValue("2026-10-23T10:15")).toBe("2026-10-23T10:15");
    expect(fromLocalInputValue("2026-10-23")).toBe("");
    expect(fromLocalInputValue("")).toBe("");
  });
});

describe("milestoneSourceNote", () => {
  it("says who recorded it, or where the system found it, and nothing for an empty time", () => {
    const base = { at: "2026-10-23T09:15:00Z", source: "court email sent", set_by: "", manual: false, can_set: false };
    expect(milestoneSourceNote(base)).toBe("From: court email sent");
    expect(milestoneSourceNote({ ...base, source: "manual", set_by: "a@example.invalid", manual: true })).toBe("Recorded by a@example.invalid");
    expect(milestoneSourceNote({ ...base, at: "" })).toBe("");
    expect(milestoneSourceNote(undefined)).toBe("");
  });
});

describe("the Details tab and the menu", () => {
  it("mounts the milestones in the Case section beside the markers", () => {
    const panel = read("../components/DetailPanel.tsx");
    expect(panel).toContain('import { MatterMilestones } from "./MatterMilestones"');
    expect(panel.indexOf("<MatterMarkers")).toBeLessThan(panel.indexOf("<MatterMilestones"));
  });

  it("links the Status board from the apps menu with a Lucide icon, and loads its stylesheet", () => {
    const drawer = read("../components/AppDrawer.tsx");
    expect(drawer).toContain('href="/status-board"');
    expect(drawer).toContain("<IconListChecks");
    expect(read("../app/layout.tsx")).toContain('import "./statusboard.css"');
  });

  it("draws no svg of its own and records a time only through the hub route", () => {
    for (const file of ["../components/MatterMilestones.tsx", "../app/status-board/page.tsx"]) expect(read(file)).not.toContain("<svg");
    const component = read("../components/MatterMilestones.tsx");
    expect(component).toContain("/api/clients/matter-milestones");
    expect(component).not.toContain("localStorage");
  });
});
