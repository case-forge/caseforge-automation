import { describe, expect, it } from "vitest";
import { TABS, forMatter, groupItems, parseResponse, stateLabel } from "./autoSend";
import type { AutoSendItem } from "./autoSend";

const item = (over: Partial<AutoSendItem>): AutoSendItem => ({
  id: "d1", matter_id: "646", client_name: "Test Client", subject: "S", recipients: ["c@example.test"], class: "Amended statement", state: "blocked",
  armed_utc: "", leaves_utc: "", sent_utc: "", stopped_utc: "2026-11-13T16:50:00Z", stopped_reason: "the arm key could not be read", body_text: "", outlook_link: "", sharepoint_link: "", ...over,
});

describe("the Blocked tab", () => {
  it("is the fourth tab and keeps blocked rows, newest first", () => {
    expect(TABS.map((t) => t.state)).toEqual(["leaving_soon", "left", "cancelled", "blocked"]);
    const groups = groupItems([item({ id: "a", stopped_utc: "2026-11-12T10:00:00Z" }), item({ id: "b", stopped_utc: "2026-11-13T10:00:00Z" })]);
    expect(groups.blocked.map((i) => i.id)).toEqual(["b", "a"]);
  });

  it("is accepted from the hub and says why, and since when", () => {
    expect(parseResponse({ items: [item({}), { state: "mystery" }] })).toHaveLength(1);
    expect(stateLabel(item({}))).toBe("the arm key could not be read, since 13 Nov, 16:50");
    expect(stateLabel(item({ stopped_reason: "", stopped_utc: "" }))).toBe("Not armed");
    expect(stateLabel(item({ stopped_reason: "Not armed. Sent by a person." }))).toBe("Not armed. Sent by a person, since 13 Nov, 16:50");
  });

  it("can be limited to one client", () => {
    const rows = [item({ id: "a", matter_id: "646" }), item({ id: "b", matter_id: "648" })];
    expect(forMatter(rows, "648").map((i) => i.id)).toEqual(["b"]);
    expect(forMatter(rows, "999")).toEqual([]);
  });
});
