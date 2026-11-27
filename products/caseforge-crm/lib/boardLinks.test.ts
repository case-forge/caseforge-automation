
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { boardLinkFor, safeBoardLink } from "./boardLinks";
import type { StatusBoardItem } from "./matterMilestones";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const MAIL = "https://outlook.office365.com/owa/?ItemID=AAA";
const FILE = "https://example.sharepoint.com/sites/x/WS.pdf";
const item = { links: { referred: MAIL, contacted: MAIL, initial_ws: FILE, filed: MAIL, laa_final_cert: FILE } } as unknown as StatusBoardItem;

describe("board date links", () => {
  it("accepts only https links on Microsoft 365 hosts", () => {
    expect(safeBoardLink(MAIL)).toBe(MAIL);
    for (const bad of ["", undefined, null, 5, "javascript:alert(1)", "http://example.sharepoint.com/x", "https://evil.example/x", "https://u:p@example.sharepoint.com/x", "https://example.sharepoint.com.evil.example/x", "https://example.sharepoint.com/a b"]) {
      expect(safeBoardLink(bad)).toBe("");
    }
  });

  it("maps both boards' column keys to the five links and gives none to the others", () => {
    expect(["referred", "joined", "contacted", "ws", "filed", "laa_final"].map((k) => boardLinkFor(item, k))).toEqual([MAIL, MAIL, MAIL, FILE, MAIL, FILE]);
    expect(boardLinkFor(item, "loa")).toBe("");
    expect(boardLinkFor(item, "laa_signed")).toBe("");
    expect(boardLinkFor({ ...item, links: undefined } as StatusBoardItem, "filed")).toBe("");
  });

  it("is rendered by the compact box and the full page, in a new tab with noopener noreferrer and a screen-reader note", () => {
    expect(read("../components/BoardDateLink.tsx")).toMatch(/target="_blank" rel="noopener noreferrer"/);
    expect(read("../components/BoardDateLink.tsx")).toContain("sr-only");
    expect(read("../components/StatusBoardCompact.tsx")).toContain("<BoardDateLink");
    expect(read("../app/status-board/page.tsx")).toContain("<BoardDateLink");
    expect(read("../components/MatterMilestones.tsx")).toMatch(/rel="noopener noreferrer"/);
  });
});
