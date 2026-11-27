import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import * as icons from "./icons";
import { LUCIDE_ICON_NODES } from "@/lib/lucideIconNodes";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const exported = Object.entries(icons).filter(([name]) => name.startsWith("Icon")) as [string, (p: object) => never][];

describe("the Lucide icons", () => {
  it("draws every exported icon as a decorative, currentColor outline that exists in the generated table", () => {
    expect(exported.length).toBeGreaterThanOrEqual(46);
    for (const [name, Icon] of exported) {
      const html = renderToStaticMarkup(createElement(Icon as never, {}));
      expect(html, name).toContain('aria-hidden="true"');
      expect(html, name).toContain('stroke="currentColor"');
      expect(html, name).toMatch(/<(path|circle|rect|line|polyline)[ >]/);
    }
  });

  it("has elements for every name in lucideIcons.json and nothing in the table that the list does not name", () => {
    const listed = (JSON.parse(read("../lib/lucideIcons.json")) as { icons: string[] }).icons;
    expect(Object.keys(LUCIDE_ICON_NODES).sort()).toEqual([...new Set(listed)].sort());
  });

  it("lights a flag or a star with its filled version, and a drawer opens", () => {
    expect(renderToStaticMarkup(createElement(icons.IconStar, { filled: true }))).not.toBe(renderToStaticMarkup(createElement(icons.IconStar, {})));
    expect(renderToStaticMarkup(createElement(icons.IconFlag, { filled: true }))).not.toBe(renderToStaticMarkup(createElement(icons.IconFlag, {})));
    expect(renderToStaticMarkup(createElement(icons.IconDrawer, { open: true }))).not.toBe(renderToStaticMarkup(createElement(icons.IconDrawer, {})));
  });

  it("is generated, not hand-edited, and no component draws its own icon svg", () => {
    expect(read("../lib/lucideIconNodes.ts")).toContain("Do not edit by hand");
    expect(read("../lib/lucideIconNodes.ts")).toContain("(ISC)");
    expect(read("./RobotNotices.tsx")).not.toContain("<svg");
    expect(read("./RobotNotices.tsx")).toContain("IconAutomation");
  });
});
