import { describe, expect, it } from "vitest";
import { portalAlertShows } from "./portalAlert";

describe("the portal alert", () => {
  it("shows for a portal matter that is still running", () => {
    expect(portalAlertShows({ portal: true }, false)).toBe(true);
  });
  it("stays whatever else is known about the case: it is not tied to a hearing date or case number", () => {
    expect(portalAlertShows({ portal: true, transferred: false, billed: true }, false)).toBe(true);
  });
  it("goes once the matter is concluded", () => {
    expect(portalAlertShows({ portal: true }, true)).toBe(false);
  });
  it("is absent for a matter not at a portal court, or with no flags yet", () => {
    expect(portalAlertShows({ portal: false }, false)).toBe(false);
    expect(portalAlertShows({}, false)).toBe(false);
    expect(portalAlertShows(undefined, false)).toBe(false);
  });
});
