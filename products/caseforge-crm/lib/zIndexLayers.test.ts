
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const css = (name: string) => readFileSync(fileURLToPath(new URL(`../app/${name}`, import.meta.url)), "utf8");
const all = css("globals.css") + css("calendar.css") + css("attention.css");

function zOf(selector: string): number {
  const at = all.indexOf(`${selector} {`);
  if (at < 0) throw new Error(`no rule for ${selector}`);
  const block = all.slice(at, all.indexOf("}", at));
  const match = block.match(/z-index:\s*(\d+)/);
  if (!match) throw new Error(`no z-index on ${selector}`);
  return Number(match[1]);
}

describe("layers", () => {
  const banners = [".session-stale-banner", ".update-banner"];

  it("keeps both banners in front of the demo windows and behind the header, whose menus open over them", () => {
    const header = zOf(".app-header");
    for (const banner of banners) {
      expect(zOf(banner), banner).toBeLessThan(header);
      expect(zOf(banner), banner).toBeGreaterThan(2000);
    }
  });
});

describe("the header on a phone", () => {
  it("keeps one row and never wraps: buttons that do not fit are in the apps menu", () => {
    const globals = css("globals.css");
    const header = globals.slice(globals.indexOf(".app-header {"), globals.indexOf(".update-banner {"));
    expect(header).not.toContain("flex-wrap");
    expect(header).toMatch(/\.app-header-actions \{[^}]*flex: 1 1 0/);
    const phone = globals.slice(globals.indexOf("@media (max-width: 640px) {\n  .app-header {"));
    expect(phone.slice(0, phone.indexOf("\n}\n"))).not.toMatch(/flex-wrap|height: auto/);
  });
});
