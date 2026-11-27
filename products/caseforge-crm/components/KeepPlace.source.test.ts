
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const PAGE = read("../components/Workspace.tsx");
const RESULTS = read("./ResultsList.tsx");
const select = PAGE.slice(PAGE.indexOf("function selectResult"), PAGE.indexOf("function openRecent("));

describe("selecting a client keeps the results where they were", () => {
  it("selectResult scrolls nothing and the results list never scrolls itself", () => {
    expect(select).not.toMatch(/scrollTo\(|scrollIntoView|\.scrollTop = /);
    expect(RESULTS).not.toMatch(/scrollTo\(|scrollIntoView|scrollTop = /);
  });

  it("the results list is never re-keyed by the selection (a remount would lose its scroll)", () => {
    expect(PAGE).not.toMatch(/<ResultsList\s+key=/);
  });

  it("on a phone, opening a client remembers the results' place and Back lands there", () => {
    expect(select).toMatch(/narrowResultsTop\.current = page\.scrollTop;/);
    expect(PAGE).toMatch(/narrowResultsTop\.current = null;\s*page\.scrollTop = saved;/);
  });

  it("folding the results away and back keeps their place", () => {
    expect(PAGE).toMatch(/if \(!resultsCollapsed\) resultsTop\.current = pageRef\.current\?\.querySelector\("\.results-pane"\)\?\.scrollTop \?\? 0;/);
    expect(PAGE).toMatch(/if \(pane && resultsTop\.current\) pane\.scrollTop = resultsTop\.current;/);
  });
});
