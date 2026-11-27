import { describe, expect, it } from "vitest";
import {
  availableTeasers,
  findTeaser,
  openId,
  parseChoice,
  serialiseChoice,
  summariseStatusBoard,
  toggleOpen,
  toggleShown,
  visibleTeasers,
} from "./frontPageTeasers";

const row = (id: string, name: string, joined: string, contacted: string, filed: string, book = "Book A - NMO-CAO", codes = ["NMO"]) => ({
  matter_id: id,
  client_name: name,
  date_joined: joined,
  loa: "",
  initial_ws: "",
  order_codes: codes,
  book,
  milestones: { contacted, papers_signed: "", filed, service_requested: "", served: "", legal_aid_done: "", invoice_paid: "", laa_interim_cert: "", laa_final_cert: "" },
});

describe("registry", () => {
  it("offers the Status board and Auto Send; the Producer is registered but unavailable", () => {
    expect(availableTeasers().map((t) => t.id)).toEqual(["status-board", "auto-sent", "court-prep"]);
    expect(findTeaser("producer")?.available).toBe(false);
    expect(findTeaser("nope")).toBeUndefined();
  });
  it("never shows the Producer even if nothing is hidden", () => {
    expect(visibleTeasers({ hidden: [], open: "" }).map((t) => t.id)).toEqual(["status-board", "auto-sent", "court-prep"]);
  });
});

describe("saved choice", () => {
  it("reads bad or missing storage as the defaults", () => {
    expect(parseChoice(null)).toEqual({ hidden: [], open: "" });
    expect(parseChoice("{oops")).toEqual({ hidden: [], open: "" });
    expect(parseChoice('{"hidden":[1,"a"],"open":5}')).toEqual({ hidden: ["a"], open: "" });
  });
  it("round-trips", () => {
    const c = { hidden: ["x"], open: "status-board" };
    expect(parseChoice(serialiseChoice(c))).toEqual(c);
  });
  it("hides a hidden teaser, so the row can be empty", () => {
    expect(visibleTeasers({ hidden: ["status-board", "auto-sent", "court-prep"], open: "" })).toEqual([]);
  });
  it("opens one at a time, closes on a second press, and ignores a hidden or unavailable open id", () => {
    const opened = toggleOpen({ hidden: [], open: "" }, "status-board");
    expect(openId(opened)).toBe("status-board");
    expect(toggleOpen(opened, "status-board").open).toBe("");
    expect(openId({ hidden: ["status-board"], open: "status-board" })).toBe("");
    expect(openId({ hidden: [], open: "producer" })).toBe("");
  });
  it("hiding the open teaser closes it", () => {
    expect(toggleShown({ hidden: [], open: "status-board" }, "status-board")).toEqual({ hidden: ["status-board"], open: "" });
    expect(toggleShown({ hidden: ["status-board"], open: "" }, "status-board").hidden).toEqual([]);
  });
});

describe("Status board summary", () => {
  const items = [
    row("1", "Stub One", "2026-10-01", "2026-10-02T09:00:00Z", ""),
    row("2", "Stub Two", "2026-10-20", "", "2026-10-21T09:00:00Z"),
    row("3", "Stub Three", "2026-10-10", "", ""),
    row("4", "Stub Four", "2026-10-15", "2026-10-16T09:00:00Z", "2026-10-17T09:00:00Z", "Book A - NMO-CAO", ["CAO"]),
    row("5", "Stub Five", "2026-10-25", "", "", "Other folder"),
    row("6", "Stub Six", "2026-10-26", "", "", "Book A - NMO-CAO", ["PSO"]),
  ];
  it("counts the default view and lists the three newest joiners as client links", () => {
    const s = summariseStatusBoard(items);
    expect(s.stats).toEqual([
      { label: "Matters shown", value: 4 },
      { label: "No contacted time", value: 2 },
      { label: "No filed time", value: 2 },
    ]);
    expect(s.links.map((l) => l.label)).toEqual(["Stub Two", "Stub Four", "Stub Three"]);
    expect(s.links[0].href).toContain("/clients/2?");
  });
  it("falls back to everything, and says so, when there is no NMO-CAO folder", () => {
    const s = summariseStatusBoard([row("1", "Stub One", "2026-10-01", "", "", "Other")]);
    expect(s.stats[0].value).toBe(1);
    expect(s.note).toContain("No NMO-CAO folder");
  });
});

describe("the Status Board panel's two buttons", () => {
  it("Full Status Board on the left, Export Board (the registry address, new tab) on the right", async () => {
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const { EXPORT_BOARD_URL } = await import("./firmLinks");
    const src = readFileSync(fileURLToPath(new URL("../components/StatusBoardBody.tsx", import.meta.url)), "utf8");
    expect(src.indexOf("Open Full Status Board")).toBeLessThan(src.indexOf("Open Export Board"));
    const refresh = src.indexOf("<IconRefresh aria-hidden");
    expect(refresh).toBeGreaterThan(src.indexOf("Open Full Status Board"));
    expect(refresh).toBeLessThan(src.indexOf("Open Export Board"));
    expect(src).toContain("href={EXPORT_BOARD_URL}");
    expect(src).not.toMatch(/https:\/\/status\./);
    expect(src).toMatch(/EXPORT_BOARD_URL\}\s+target="_blank" rel="noopener noreferrer"/);
    expect(EXPORT_BOARD_URL).toMatch(/^https:\/\//);
  });
});
