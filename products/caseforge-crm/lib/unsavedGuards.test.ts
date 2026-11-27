import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

const FORMS = ["../components/ClientEdits.tsx", "../components/HearingDrawer.tsx", "../components/TodoParts.tsx"];

describe("every place that holds typed-but-unsaved work reports it, keeps a draft and is guarded", () => {
  it("reports from the Client edit, the party and child rows, both hearing drawers and the new to-do box", () => {
    expect(read("../components/ClientEdits.tsx")).toContain('useReportUnsaved(\n    "client-edit"');
    expect(read("../components/ClientRows.tsx")).toContain("useReportUnsaved(\n    `row-editor-${config.endpoint}`,");
    const drawer = read("../components/HearingDrawer.tsx");
    expect(drawer).toContain('useReportUnsaved(guardId, useHearingSource("Hearing"');
    expect(drawer).toContain('useReportUnsaved(guardId, useHearingSource("New hearing", matterId, clientName)');
    expect(read("../components/TodoParts.tsx")).toContain("useReportUnsaved(\n    sourceId,");
  });

  it("each form keeps a draft, shows the restored note, and carries the anchor Show me looks for", () => {
    for (const path of FORMS) {
      const src = read(path);
      expect(src, path).toContain("useFormDraft");
      expect(src, path).toContain("<DraftRestoredNote");
      expect(src, path).toContain("data-unsaved-source=");
    }
  });

  it("names the client: the panel provides it, the forms read it", () => {
    expect(read("../components/DetailPanel.tsx")).toContain("<CurrentClientContext.Provider value={currentClient}>");
    for (const path of ["../components/ClientRows.tsx", "../components/HearingDrawer.tsx", "../components/TodoParts.tsx"]) {
      expect(read(path), path).toContain("useCurrentClient()");
    }
    expect(read("../components/ClientEdits.tsx")).toContain("clientName: fullNameOf(match)");
  });

  it("asks before the drawer closes (button, Escape), and Escape out of edit mode asks to discard", () => {
    const drawer = read("../components/HearingDrawer.tsx");
    expect(drawer).toContain("(beforeClose ?? (() => confirmLeaveUnsaved([guardId])))()");
    expect(drawer).toContain("if (!confirmDiscardUnsaved([guardId])) return true;");
  });

  it("a Cancel or a create that closes the new-hearing drawer also forgets its draft", () => {
    const drawer = read("../components/HearingDrawer.tsx");
    expect(drawer).toMatch(/function cancel\(\) \{\s*kept\.clear\(\);\s*onClose\(\);/);
    expect(drawer).toMatch(/kept\.clear\(\);\s*if \(draftId\) deleteHearingDraft\(draftId\);\s*onCreated\(body\.hearing\);/);
  });

  it("keys the forms per matter, so a draft never lands on another client", () => {
    const panel = read("../components/DetailPanel.tsx");
    expect(panel).toMatch(/<ClientEditProvider\s+key=\{matterId\}/);
    expect(panel).toContain("<RowsSection key={`parties-${matterId}`}");
    expect(panel).toContain("<RowsSection key={`children-${matterId}`}");
    expect(read("../components/HearingDrawer.tsx")).toContain("<HearingDrawerBody key={props.hearing.hearing_id}");
  });

  it("asks before every way of leaving the client: tab, case, another client, a list, the logo, a notice", () => {
    const panel = read("../components/DetailPanel.tsx");
    expect(panel.match(/confirmLeaveUnsaved\(\)/g)!.length).toBeGreaterThanOrEqual(5);
    const page = read("../components/Workspace.tsx");
    for (const fn of ["function selectResult", "function handleQuickListResults", "function goHome"]) {
      const body = page.slice(page.indexOf(fn), page.indexOf(fn) + 400);
      expect(body, fn).toContain("confirmLeaveUnsaved()");
    }
  });

  it("keeps an open client with a half-typed edit open when a new search no longer lists it", () => {
    expect(read("../components/Workspace.tsx")).toContain("!stillPresent && unsavedLabels().length === 0");
  });
});
