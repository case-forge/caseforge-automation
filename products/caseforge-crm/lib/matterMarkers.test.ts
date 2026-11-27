import { describe, expect, it } from "vitest";
import { markerView } from "./matterMarkers";

describe("markerView", () => {
  it("shows a received marker with its London date", () => {
    expect(markerView({ status: "received", date: "2026-10-02T23:30:00Z" }, false)).toEqual({ state: "received", text: "Received 3 Oct 2026", url: "" });
    expect(markerView({ status: "received", date: "" }, false)).toEqual({ state: "received", text: "Received", url: "" });
  });

  it("reads not yet, still checking, or could not check", () => {
    expect(markerView({ status: "missing", date: "" }, false)).toEqual({ state: "missing", text: "Not yet", url: "" });
    expect(markerView(undefined, false).state).toBe("loading");
    expect(markerView({ status: "unknown", date: "" }, false).text).toBe("Couldn't check");
    expect(markerView({ status: "received", date: "2026-10-02T08:00:00Z" }, true).state).toBe("unknown");
  });

  it("reads a marker the hub has not searched for yet as not checked, never as missing", () => {
    expect(markerView({ status: "pending", date: "" }, false)).toEqual({ state: "pending", text: "Not checked yet", url: "" });
  });

  it("reads a client with no folder to search as that, never as not yet or missing", () => {
    expect(markerView({ status: "unsearchable", reason: "no_folder", date: "" }, false)).toEqual({ state: "unsearchable", text: "No folder recorded", url: "" });
    expect(markerView({ status: "unsearchable", reason: "folder_not_found", date: "" }, false).text).toBe("Folder not found");
  });

  it("carries the link to the filed document, but only for a received marker", () => {
    const received = markerView({ status: "received", date: "2026-10-02T08:00:00Z", url: "https://short.example.invalid/abc" }, false);
    expect(received.url).toBe("https://short.example.invalid/abc");
    expect(markerView({ status: "missing", date: "", url: "https://short.example.invalid/abc" }, false).url).toBe("");
  });

  it("only links to an https address", () => {
    expect(markerView({ status: "received", date: "2026-10-02T08:00:00Z", url: "javascript:alert(1)" }, false).url).toBe("");
  });
});
