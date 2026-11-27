import { describe, expect, it } from "vitest";
import { calendarPath, clientPath, parseWorkspacePath, searchPath, viewToMode } from "./workspaceUrl";

describe("workspace addresses", () => {
  it("reads each route", () => {
    expect(parseWorkspacePath("/")).toEqual({ kind: "home" });
    expect(parseWorkspacePath("/clients")).toEqual({ kind: "clients" });
    expect(parseWorkspacePath("/clients/614")).toEqual({ kind: "client", matterId: "614", tab: null });
    expect(parseWorkspacePath("/clients/614/hearings")).toEqual({ kind: "client", matterId: "614", tab: "hearings" });
    expect(parseWorkspacePath("/clients/abc")).toEqual({ kind: "clients" });
    expect(parseWorkspacePath("/calendar")).toEqual({ kind: "calendar", date: null, mode: null });
    expect(parseWorkspacePath("/calendar/2026-12")).toEqual({ kind: "calendar", date: "2026-12", mode: null });
    expect(parseWorkspacePath("/calendar/2026-12-14/week")).toEqual({ kind: "calendar", date: "2026-12-14", mode: "week" });
    expect(parseWorkspacePath("/calendar/2026-12/agenda")).toEqual({ kind: "calendar", date: "2026-12", mode: "agenda" });
  });

  it("ignores a calendar date or mode that is not one", () => {
    expect(parseWorkspacePath("/calendar/2026-13")).toEqual({ kind: "calendar", date: null, mode: null });
    expect(parseWorkspacePath("/calendar/2026-12/year")).toEqual({ kind: "calendar", date: "2026-12", mode: null });
  });

  it("builds addresses that read back the same", () => {
    expect(calendarPath("2026-12-01", "month")).toBe("/calendar/2026-12");
    expect(calendarPath("2026-12-14", "week")).toBe("/calendar/2026-12-14/week");
    expect(calendarPath("2026-12-01", "agenda")).toBe("/calendar/2026-12/agenda");
    expect(parseWorkspacePath(calendarPath("2026-12-14", "week"))).toMatchObject({ date: "2026-12-14", mode: "week" });
    expect(clientPath("614", "hearings", "Jo Smith")).toBe("/clients/614/hearings?q=Jo%20Smith");
    expect(clientPath("614", null, " ")).toBe("/clients/614");
    expect(searchPath("a")).toBe("/");
    expect(searchPath("smith")).toBe("/clients?q=smith");
  });

  it("names a view by its mode", () => {
    expect(viewToMode("timeGridWeek")).toBe("week");
    expect(viewToMode("listMonth")).toBe("agenda");
    expect(viewToMode("dayGridMonth")).toBe("month");
  });
});
