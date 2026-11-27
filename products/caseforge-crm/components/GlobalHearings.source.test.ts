import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { hearingHref } from "../lib/hearingsHost";
import { PINNED_Z_BASE, pinnedZ, pressed } from "../lib/windowPins";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

describe("the upcoming hearings window is app-level", () => {
  it("is mounted once, in the root layout, and nowhere else", () => {
    expect(read("../app/layout.tsx")).toContain("<GlobalHearings />");
    expect(read("../app/layout.tsx").match(/<GlobalHearings/g)).toHaveLength(1);
    for (const file of ["./Workspace.tsx", "./CalendarView.tsx", "./Shell.tsx", "../app/template.tsx"]) expect(read(file)).not.toContain("<UpcomingRail");
    expect(read("./GlobalHearings.tsx")).toContain("<UpcomingRail");
    expect(read("./Workspace.tsx")).not.toContain("useRailOpen");
  });
  it("the workspace reserves nothing for it and shares its refresh and review count through the host", () => {
    const workspace = read("./Workspace.tsx");
    expect(workspace).toContain("useHearingsVersion()");
    expect(workspace).toContain("hearingsHost.register(openClientFromHearing)");
    expect(workspace).not.toMatch(/data-rail|railHearings|setRailOpen/);
  });
  it("opens a client from a hearing through the workspace when it is on screen, and by address otherwise", () => {
    const code = read("./GlobalHearings.tsx");
    expect(code).toContain("hearingsHost.openInWorkspace(h)");
    expect(code).toContain("router.push(hearingHref(h))");
    const base = { case_ref: " ZZ00F00001 ", client_name: "A Client", hearing_id: 7 } as never;
    expect(hearingHref({ ...(base as object), matter_id: 12 } as never)).toBe("/clients/12/hearings?q=ZZ00F00001&hearing=7");
    expect(hearingHref({ ...(base as object), matter_id: null } as never)).toBe("/clients?q=ZZ00F00001");
    expect(hearingHref({ case_ref: "", client_name: "", matter_id: null, hearing_id: 1 } as never)).toBe("/");
  });
});

describe("pinning lifts a window", () => {
  it("a pinned window is above every unpinned window's z-index, and fronts when pressed", () => {
    const unpinnedZs = [40, 60, 900 + 5, 913, 5000 - 1];
    const order = pressed(pressed([], "panel"), "drawer");
    const z = pinnedZ(order, new Set(["drawer"]), "drawer");
    expect(z).not.toBeNull();
    for (const other of unpinnedZs.filter((n) => n < PINNED_Z_BASE)) expect(z!).toBeGreaterThan(other);
    const both = new Set(["panel", "drawer"]);
    expect(pinnedZ(order, both, "drawer")!).toBeGreaterThan(pinnedZ(order, both, "panel")!);
    const back = pressed(order, "panel");
    expect(pinnedZ(back, both, "panel")!).toBeGreaterThan(pinnedZ(back, both, "drawer")!);
  });
  it("the hearing slide-out is portalled to the body so its parent's stacking context cannot trap it", () => {
    expect(read("./HearingSlideOut.tsx")).toContain("document.body");
    expect(read("./HearingSlideOut.tsx")).toContain("createPortal(");
  });
});
