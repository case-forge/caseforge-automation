
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StoragePie } from "./StoragePie";
import { pieSlices } from "@/lib/storageStatus";
import { stubStorageStatus } from "@/lib/stubStorageStatus";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

describe("Storage tab", () => {
  const panel = read("./StoragePanel.tsx");
  it("refreshes itself every minute, only while the page is visible, and cleans up", () => {
    expect(panel).toContain("window.setInterval");
    expect(panel).toContain('document.visibilityState !== "visible"');
    expect(panel).toContain("window.clearInterval(timer)");
  });
  it("shows the update time, the recycle bin explanation and a refresh button", () => {
    expect(panel).toContain("updatedLabel(data.generated_at)");
    expect(panel).toContain("up to 93 days");
    expect(panel).toContain("Refresh");
  });
  it("draws the donut as SVG with a text table beside it, in palette tokens only", () => {
    const html = renderToStaticMarkup(createElement(StoragePie, { slices: pieSlices(stubStorageStatus().rows) }));
    expect(html).toContain('role="img"');
    expect(html).toContain("<table");
    expect(html).toContain("var(--accent)");
    expect(html).not.toMatch(/#[0-9a-f]{3,8}\b|rgb\(/i);
    expect(read("../app/storage.css")).not.toMatch(/#[0-9a-f]{3,8}\b|rgb\(|hsl\(/i);
  });
  it("is a developer-only route and tab", () => {
    expect(read("../app/api/storage-status/route.ts")).toContain("refuseUnlessDev");
    expect(read("./SettingsPage.tsx")).toContain('{ id: "storage", title: "Storage", body: <StoragePanel />, devOnly: true }');
  });
});
