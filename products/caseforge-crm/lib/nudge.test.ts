import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { NUDGE_NOTE, nudgeDocFor, nudgeLabel, nudgeQuestion } from "./nudge";
import { stubStatusBoard } from "./stubMilestones";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const rule = { rule_id: "signing_loa_ws", since_date: "2026-11-05", working_days: 3 };

describe("which cell gets Nudge", () => {
  it("a client who has not been contacted yet gets no Nudge", () => {
    expect(nudgeDocFor({ nudge: { witness_statement: rule }, milestones: {} }, "ws", "")).toBeNull();
    expect(nudgeDocFor({ nudge: { client_docs: rule }, milestones: { contacted: "" } }, "loa", "")).toBeNull();
  });
  it("WS Signed offers the witness-statement nudge, and only while the cell is empty", () => {
    const item = { nudge: { witness_statement: rule }, milestones: { contacted: "2026-11-04" } };
    expect(nudgeDocFor(item, "ws", "")).toBe("witness_statement");
    expect(nudgeDocFor(item, "ws", "2026-11-04")).toBeNull();
  });
  it("LoA Signed offers the client-documents nudge, and the two never cross", () => {
    expect(nudgeDocFor({ nudge: { client_docs: rule }, milestones: { contacted: "2026-11-04" } }, "loa", "")).toBe("client_docs");
    expect(nudgeDocFor({ nudge: { client_docs: rule } }, "ws", "")).toBeNull();
    expect(nudgeDocFor({ nudge: { witness_statement: rule } }, "loa", "")).toBeNull();
  });
  it("no nudge on the item, an older hub, or another column: a dash", () => {
    expect(nudgeDocFor({}, "ws", "")).toBeNull();
    expect(nudgeDocFor({ nudge: {} }, "ws", "")).toBeNull();
    expect(nudgeDocFor({ nudge: { witness_statement: rule, client_docs: rule } }, "contacted", "")).toBeNull();
  });
  it("words", () => {
    expect(nudgeLabel("Ada Example", "witness_statement")).toBe("Nudge Ada Example to sign their witness statement");
    expect(nudgeLabel("Ada Example", "client_docs")).toBe("Nudge Ada Example to sign their documents");
    expect(nudgeQuestion("Ada Example")).toBe("Send a reminder to Ada Example?");
    expect(NUDGE_NOTE).toBe("This makes the reminder email. If Case flow is on Auto for this client it sends itself after a short wait; otherwise it waits in Drafts for you to send.");
  });
  it("the demo has a witness-statement nudge, a client-docs nudge and both", () => {
    const items = stubStatusBoard().items;
    const docs = (id: string) => Object.keys(items.find((i) => i.matter_id === id)?.nudge ?? {}).sort();
    expect(docs("9012")).toEqual(["witness_statement"]);
    expect(docs("9013")).toEqual(["client_docs"]);
    expect(docs("9014")).toEqual(["client_docs", "witness_statement"]);
  });
});

describe("one cell component, one question", () => {
  it("the Full Status Board and the box both draw NudgeCell, decided by nudgeDocFor", () => {
    for (const f of ["../app/status-board/page.tsx", "../components/StatusBoardCompact.tsx"]) {
      const src = read(f);
      expect(src, f).toContain("<NudgeCell");
      expect(src, f).toContain("nudgeDocFor(");
    }
  });
  it("the box has no LoA column, so it never offers the client-documents nudge", () => {
    expect(read("./boardCompact.ts")).not.toMatch(/key: "loa"/);
  });
  it("the Nudge is plain text in the dash colour, with the same modal as WeTransfer and no badge", () => {
    const cell = read("../components/NudgeCell.tsx");
    expect(cell).toContain('className="sb-wetransfer sb-nudge"');
    expect(cell).toContain("<BoardConfirm");
    expect(read("../components/StatusBoardCompact.tsx")).toContain("<BoardConfirm");
    expect(read("../components/BoardConfirm.tsx")).toContain("createPortal(");
    expect(read("./launcherBadges.ts")).not.toMatch(/nudge/i);
  });
  it("OK posts the matter and document only, and a success reads Nudged", () => {
    const cell = read("../components/NudgeCell.tsx");
    expect(cell).toContain("JSON.stringify({ matter_id: matterId, doc })");
    expect(cell).not.toMatch(/by:|set_by|name:/);
    expect(cell).toContain("Nudged");
  });
});

import { PORTAL_TITLE, showsPortal } from "./portalCell";

describe("Portal in the Filed to Court cell", () => {
  it("only an empty filed cell of a portal-court matter, and never another column", () => {
    expect(showsPortal({ portal_court: true }, "filed", "")).toBe(true);
    expect(showsPortal({ portal_court: true }, "filed", "2026-11-04T10:00:00Z")).toBe(false);
    expect(showsPortal({ portal_court: false }, "filed", "")).toBe(false);
    expect(showsPortal({}, "filed", "")).toBe(false);
    expect(showsPortal({ portal_court: true }, "ws", "")).toBe(false);
    expect(PORTAL_TITLE).toBe("Filed through the court's online portal");
  });
  it("the demo has one portal row not filed and one filed", () => {
    const items = stubStatusBoard().items.filter((i) => i.portal_court);
    expect(items.map((i) => i.matter_id)).toEqual(["9015", "9016"]);
    expect(showsPortal(items[0], "filed", items[0].milestones.filed ?? "")).toBe(true);
    expect(showsPortal(items[1], "filed", items[1].milestones.filed ?? "")).toBe(false);
  });
  it("one shared plain-text cell in the box and the Full Status Board, in the dash colour, no button", () => {
    for (const f of ["../app/status-board/page.tsx", "../components/StatusBoardCompact.tsx"]) {
      const src = read(f);
      expect(src, f).toContain("<PortalCell");
      expect(src, f).toContain("showsPortal(");
    }
    const cell = read("../components/PortalCell.tsx");
    expect(cell).not.toContain("<button");
    expect(cell).toContain("PORTAL_TITLE");
    expect(read("../components/StatusBoardCompact.tsx")).toMatch(/PortalCell key=\{c\.key\} className="sb-compact-empty"/);
    expect(read("../app/status-board/page.tsx")).toMatch(/PortalCell key=\{c\.id\} className="status-board-empty"/);
  });
});
