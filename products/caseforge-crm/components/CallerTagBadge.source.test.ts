import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { callerTagsOf } from "@/lib/callerTags";

const read = (name: string) => readFileSync(new URL(name, import.meta.url), "utf8");

describe("frequent caller icons", () => {
  it("are phone icons with the words as their name, and no list prints the PC code", () => {
    const badge = read("./CallerTagBadge.tsx");
    expect(badge).toContain("IconPhoneRinging");
    expect(badge).toContain("aria-label={tag.label}");
    expect(read("./ResultsList.tsx")).not.toMatch(/>\s*\{tag\.code\}\s*</);
  });

  it("sit straight after the name (and its copy box on the detail page), before the pills, on both pages", () => {
    const list = read("./ResultsList.tsx");
    expect(list).toContain("<CallerIcons");
    expect(list.indexOf("<CallerIcons")).toBeLessThan(list.indexOf("result-card-new"));
    const detail = read("./DetailPanel.tsx");
    expect(detail).toContain("<CallerIcons");
    expect(detail.indexOf('label="name" />')).toBeLessThan(detail.indexOf("<CallerIcons"));
    expect(detail.indexOf("<CallerIcons")).toBeLessThan(detail.indexOf("detail-title-new"));
  });

  it("show two distinguishable icons when the client and the opponent are both frequent callers", () => {
    const tags = callerTagsOf({ persistent_caller: true, persistent_caller_respondent: true });
    expect(tags.map((t) => t.kind)).toEqual(["client", "opponent"]);
    expect(new Set(tags.map((t) => t.label)).size).toBe(2);
    expect(callerTagsOf({ persistent_caller_respondent: true }).map((t) => t.kind)).toEqual(["opponent"]);
  });

  it("colour the opponent's red and the client's the plain text colour (black), never the accent", () => {
    const css = read("../app/globals.css");
    expect(css).toMatch(/\.caller-icon--opponent \{ color: var\(--flag-red\); \}/);
    expect(css).toMatch(/\.caller-icon--client \{ color: var\(--fg\); \}/);
    expect(css).not.toMatch(/\.caller-icon--client \{ color: var\(--accent\)/);
  });

  it("keep their original size on the results page, a little smaller beside the client page's large title, and sit on the text line", () => {
    const css = read("../app/globals.css");
    expect(css).toMatch(/\.caller-icon-svg \{ width: 1\.05em; height: 1\.05em; \}/);
    expect(css).toMatch(/\.detail-title \.caller-icon-svg \{ width: 0\.85em; height: 0\.85em; \}/);

    expect(css).toMatch(/\.caller-icons \{[^}]*vertical-align: middle;/);
    expect(css).not.toMatch(/\.caller-icon \{[^}]*vertical-align/);
  });
});

describe("empty opponent list", () => {
  it("says there is no opponent, not that nobody is on record", () => {
    expect(read("./ClientRows.tsx")).toContain('emptyLabel: "No opponent on record"');
    expect(read("./ClientRows.tsx")).not.toContain("Nobody on record");
  });
});
