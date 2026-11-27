import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { alreadyExcluded, confirmQuestion, exclusionLabel, exclusionPath, folderBookLabel, isReadOnly } from "../lib/folderLocks";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const locks = (paths: string[]) => ({ fixed: [], locked: paths.map((path) => ({ path, locked_by: "x", locked_utc: "" })), books: [], children: {} });

describe("the retired Assignment Board's controls in Settings", () => {
  it("Folders carries the 'Folders not to touch' list, with one plain confirmation and no read-only switches", () => {
    expect(read("./SettingsPage.tsx")).toMatch(/id: "folders"[^}]*extra: <ExcludedFoldersPanel \/>/);
    const panel = read("./ExcludedFoldersPanel.tsx");
    expect(panel).toContain("Folders not to touch");
    expect(panel).toContain("confirmQuestion(pending)");
    expect(panel).not.toContain("CONFIRMS");
    expect(panel).toContain("Remove");
  });

  it("the per-person Outlook category box is no longer shown in Settings", () => {
    expect(read("./SettingsPage.tsx")).not.toContain("<MailCategoriesBox />");
  });

  it("the status board has no category column, picker or sort", () => {
    const page = read("../app/status-board/page.tsx");
    expect(page).not.toMatch(/categor/i);
    expect(existsSync(fileURLToPath(new URL("./CategoryDot.tsx", import.meta.url)))).toBe(false);
  });

  it("the columns are fixed (no resizing, no moving) and nothing wraps", () => {
    const page = read("../app/status-board/page.tsx");
    for (const gone of ["ColumnResizeHandle", "Reset widths", "draggable", "onDragStart", "reorder", "WIDTHS_KEY"]) expect(page).not.toContain(gone);
    expect(page).toContain("nextSort(sort, c.id)");
    expect(read("../app/statusboard.css")).toContain("white-space: nowrap");
    expect(read("../app/statusboard.css")).not.toContain("white-space: normal");
  });

  it("the Full Status Board has Year (with All years) and Month (with All months) selects and no Folder select", () => {
    const page = read("../app/status-board/page.tsx");
    expect(page).toContain("All years");
    expect(page).toContain("All months");
    expect(page).not.toMatch(/Folder|All folders|booksIn/);
    expect(read("../app/statusboard.css")).toMatch(/\.status-board-year select,\s*\.status-board-month select/);
  });
  it("one shape: fixed table layout and column widths, a box that keeps its height, an empty state inside it, a 1600 px column", () => {
    const css = read("../app/statusboard.css");
    expect(css).toContain("table-layout: fixed");
    expect(css).toMatch(/\.status-board-col-date \{ width: [0-9.]+%; \}/);
    expect(css).toMatch(/\.status-board-scroll \{[^}]*min-height: 36rem/);
    expect(css).toMatch(/\.status-board \{[^}]*max-width: 1600px;[^}]*padding: 16px/);
    expect(css).toContain(".status-board-empty-state");
    expect(read("../app/status-board/page.tsx")).toContain("status-board-empty-state");
  });
});

describe("folder exclusion helpers", () => {
  it("labels a book without its sort prefix and reads the list", () => {
    expect(folderBookLabel("2AA-Z - NMO-CAO")).toBe("NMO-CAO");
    expect(isReadOnly(locks(["2A-Z - Alex"]), "2a-z - alex")).toBe(true);
    expect(isReadOnly(locks(["2A-Z - Alex"]), "2B-Z - Sam")).toBe(false);
  });

  it("builds a path from the book, a folder inside it and a typed deeper path, refusing dot segments", () => {
    expect(exclusionPath("2A-Z - Alex")).toBe("2A-Z - Alex");
    expect(exclusionPath("2A-Z - Alex", "Client A", " Court bundle\\Drafts/ ")).toBe("2A-Z - Alex/Client A/Court bundle/Drafts");
    expect(exclusionPath("", "Client A")).toBe("");
    expect(exclusionPath("2A-Z - Alex", "", "../x")).toBe("");
  });

  it("says what a path covers and spots one that is already covered", () => {
    expect(exclusionLabel("2A-Z - Alex/Client A")).toBe("Alex / Client A");
    const l = locks(["2A-Z - Alex"]);
    expect(alreadyExcluded(l, "2a-z - alex/Client A")).toBe(true);
    expect(alreadyExcluded(l, "2B-Z - Sam/Client D")).toBe(false);
    expect(alreadyExcluded(locks(["2A-Z - Alex/Client A"]), "2A-Z - Alex")).toBe(false);
  });

  it("asks once, in plain words, for an add and for a remove", () => {
    expect(confirmQuestion({ kind: "add", path: "2A-Z - Alex/Client A" })).toBe("Stop automation changing anything in Alex / Client A?");
    expect(confirmQuestion({ kind: "remove", path: "2A-Z - Alex" })).toBe("Let automation work in Alex again?");
  });
});
