
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

describe("the bell", () => {
  it("shows everyone the same list: no person dropdown, no assignee in the pulse; Done is recorded under the signed-in person", () => {
    const bell = read("./AttentionBell.tsx");
    expect(bell).not.toContain("Show notifications for");
    expect(bell).toContain("useAttentionDone()");
    expect(bell).not.toContain("hideName");
    expect(read("../lib/pulse.ts")).not.toContain("assignee");
    expect(read("../lib/useAttention.ts")).not.toContain("Assignee");
  });

  it("puts Open client, Open email and Done on one aligned line", () => {
    const css = read("../app/attention.css");
    expect(css).toMatch(/\.attention-item-actions \{[^}]*align-items: center/);
    expect(css).toMatch(/\.attention-item-link \{[^}]*display: inline-flex[^}]*min-height/);
  });
});

describe("Other parties", () => {
  it("sit on the Client tab under the one client edit session, with no client row and no separate Child label", () => {
    const rows = read("./ClientRows.tsx");
    expect(rows).toContain("isClientParty(String(row.role");
    expect(rows).toContain("detail-field-label");
    expect(rows).not.toContain("groupLabel");
    expect(rows).toContain("registerSaver");
    const panel = read("./DetailPanel.tsx");
    expect(panel).toContain('<RowsSection key={`parties-${matterId}`} kind="parties"');
    expect(panel).toContain("clientRole={match.client_role}");
    expect(panel).not.toContain('detailTab === "parties"');
  });
});

describe("Assigned to", () => {
  it("is gone from the Details tab, the code and the stylesheets", () => {
    expect(existsSync(fileURLToPath(new URL("./AssignedTo.tsx", import.meta.url)))).toBe(false);
    expect(existsSync(fileURLToPath(new URL("../lib/matterAssignee.ts", import.meta.url)))).toBe(false);
    expect(read("./DetailPanel.tsx")).not.toContain("Assigned to");
    expect(read("../lib/pipeline.ts")).not.toContain("assignment-changed");
    expect(read("../lib/pulse.ts")).not.toContain("assignment-changed");
  });
});

describe("the opponent / other parties and the children", () => {
  it("put a copy button beside every populated box, as the client's own fields have", () => {
    const rows = read("./ClientRows.tsx");
    expect(rows).toContain('import { CopyButton } from "./CopyButton";');
    expect(rows).toContain('<CopyButton text={box.values.join(", ")} label={box.label.toLowerCase()} />');

    expect(rows).toContain("box.values.length > 0 && <CopyButton");
  });
});
