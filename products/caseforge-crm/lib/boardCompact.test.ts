import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { COMPACT_ROWS, awaitingSignature, boardAge, boardRows, daysWaiting, finishState, formatBoardDay, isNewReferral, recentItems, waitingLabel } from "./boardCompact";
import type { StatusBoardItem } from "./matterMilestones";
import { stubStatusBoard } from "./stubMilestones";
import { summariseStatusBoard } from "./frontPageTeasers";
import { StatusBoardTable } from "../components/StatusBoardCompact";

const item = (id: string, name: string, joined: string, over: Partial<StatusBoardItem["milestones"]> = {}): StatusBoardItem => ({
  matter_id: id,
  client_name: name,
  date_joined: joined,
  loa: "",
  initial_ws: "",
  order_codes: [],
  book: "",
  milestones: { contacted: "", filed: "", laa_final_cert: "", ...over } as StatusBoardItem["milestones"],
});

describe("formatBoardDay (matches export-board dayLabel)", () => {
  it("writes 06 Nov (Fri)", () => {
    expect(formatBoardDay("2026-11-06")).toBe("06 Nov (Fri)");
    expect(formatBoardDay("2026-09-01")).toBe("01 Sep (Tue)");
  });
  it("uses the London date of a timestamp, not the UTC one", () => {
    expect(formatBoardDay("2026-06-05T23:30:00Z")).toBe("06 Jun (Sat)");
    expect(formatBoardDay("2026-11-06T23:30:00Z")).toBe("06 Nov (Fri)");
  });
  it("is empty for nothing", () => {
    expect(formatBoardDay("")).toBe("");
    expect(formatBoardDay("nonsense")).toBe("");
  });
});

describe("recentItems and New", () => {
  it("keeps the newest seven, latest referral first", () => {
    const many = Array.from({ length: 10 }, (_, i) => item(String(i), `Client ${i}`, `2026-10-${String(10 + i).padStart(2, "0")}`));
    const got = recentItems(many);
    expect(got).toHaveLength(COMPACT_ROWS);
    expect(got[0].client_name).toBe("Client 9");
  });
  it("tags only a referral from the last three days", () => {
    const now = new Date("2026-11-09T10:00:00Z");
    expect(isNewReferral(item("1", "A", "2026-11-06"), now)).toBe(true);
    expect(isNewReferral(item("1", "A", "2026-11-05"), now)).toBe(false);
    expect(isNewReferral(item("1", "A", ""), now)).toBe(false);
  });
});

describe("the status board panel on the front page", () => {
  it("carries the newest rows from the board's own default view", () => {
    const summary = summariseStatusBoard(stubStatusBoard().items);
    expect(summary.rows?.length).toBeGreaterThan(0);
    expect(summary.rows!.length).toBeLessThanOrEqual(COMPACT_ROWS);
  });
  it("draws the six headings, the rows, dates and the New tag", () => {
    const html = renderToStaticMarkup(createElement(StatusBoardTable, { items: stubStatusBoard().items, now: new Date() }));
    for (const h of ["Client", "Referred", "Contacted", "WS Signed", "Filed to Court", "LAA Final Cert"]) expect(html).toContain(`>${h}<`);
    expect(html).toContain("Stub client 9001");
    expect(html).toMatch(/\d{2} [A-Z][a-z]{2} \([A-Z][a-z]{2}\)/);
    expect(html).toContain("New");
    expect(html).toContain("–");
  });
  it("opens the full page from a clear control, and has loading, error and empty states", () => {
    const comp = readFileSync(fileURLToPath(new URL("../components/StatusBoardBody.tsx", import.meta.url)), "utf8");
    expect(comp).toContain("Open Full Status Board");
    expect(comp).toContain("Loading…");
    expect(comp).toContain("FAILURE_LINE");
    expect(comp).toContain("No open matters yet.");
    expect(readFileSync(fileURLToPath(new URL("../components/FrontPageTeasers.tsx", import.meta.url)), "utf8")).toContain("aria-expanded={active}");
  });
});

describe("recentItems across month lengths", () => {
  const row = (id: string, joined: string) => ({ matter_id: id, client_name: `Client ${id}`, date_joined: joined }) as never;
  it("puts November before October before September, whatever the number of digits in the month", () => {
    const out = recentItems([row("1", "2026-09-30"), row("2", "2026-11-10"), row("3", "2026-10-30"), row("4", "2026-09-07"), row("5", "2026-11-02")], 5);
    expect(out.map((i) => i.matter_id)).toEqual(["2", "5", "3", "1", "4"]);
  });
});

describe("finished clients stay five London days, then are gone", () => {

  const finished = (id: string, last: string, joined = "2026-08-01") =>
    ({
      ...item(id, `Client ${id}`, joined, { contacted: "2026-08-20", filed: "2026-09-05", laa_final_cert: last }),
      initial_ws: "2026-08-25",
    });
  const now = new Date("2026-11-02T12:00:00Z");

  it("takes the latest of the five dates as the finish day", () => {
    const c = finished("1", "2026-10-31");
    const today = (n: Date) => finishState(c, n);
    expect(today(new Date("2026-10-31T12:00:00Z"))).toBe("leaving");
    expect(today(new Date("2026-11-05T12:00:00Z"))).toBe("leaving");
    expect(today(new Date("2026-11-06T12:00:00Z"))).toBe("gone");
  });
  it("a client finished 3 days ago stays, across a month boundary", () => {
    expect(finishState(finished("1", "2026-10-30"), now)).toBe("leaving");
    expect(finishState(finished("2", "2026-09-29"), new Date("2026-10-02T12:00:00Z"))).toBe("leaving");
  });
  it("a client finished 6 days ago is gone, across a month boundary", () => {
    expect(finishState(finished("1", "2026-10-27"), now)).toBe("gone");
    expect(finishState(finished("2", "2026-09-24"), new Date("2026-09-30T12:00:00Z"))).toBe("gone");
    expect(finishState(finished("3", "2026-10-28"), new Date("2026-11-03T12:00:00Z"))).toBe("gone");
  });
  it("uses the London day of a timestamp", () => {
    expect(finishState(finished("1", "2026-09-26T23:30:00Z"), new Date("2026-10-02T12:00:00Z"))).toBe("leaving");
    expect(finishState(finished("1", "2026-09-26T23:30:00Z"), new Date("2026-10-03T12:00:00Z"))).toBe("gone");
  });
  it("a client with four dates stays with no tag", () => {
    const c = item("1", "Four", "2026-08-01", { contacted: "2026-08-20", filed: "2026-09-05", laa_final_cert: "" });
    expect(finishState({ ...c, initial_ws: "2026-08-25" }, now)).toBe("");
    expect(boardRows([{ ...c, initial_ws: "2026-08-25" }], new Date("2026-09-10T12:00:00Z"))).toHaveLength(1);
  });
  it("chooses the rows after dropping: the newest of those still on the board", () => {
    const gone = finished("old", "2026-10-01", "2026-10-01");
    const rest = Array.from({ length: 9 }, (_, i) => item(String(i), `Client ${i}`, `2026-09-${String(10 + i).padStart(2, "0")}`));
    const rows = boardRows([gone, ...rest], new Date("2026-10-08T12:00:00Z"));
    expect(rows).toHaveLength(COMPACT_ROWS);
    expect(rows.map((r) => r.matter_id)).not.toContain("old");
    expect(rows[0].matter_id).toBe("8");
  });
  it("carries no Leaving tag, and draws the WeTransfer button in Contacted", () => {
    const leaving = finished("1", "2026-10-30");
    const pending = { ...item("2", "Pending", "2026-11-01"), wetransfer_pending: true };
    const html = renderToStaticMarkup(createElement(StatusBoardTable, { items: [leaving, pending], now }));
    expect(html).not.toContain("Leaving");
    expect(html).toContain("Client 1");
    expect(html).toContain('aria-label="WeTransfer: download permission needed"');
    expect(html).toContain(">WeTransfer<");
  });
  it("the demo board has a WeTransfer client, one finished 2 days ago (stays) and one dropped", () => {
    const items = stubStatusBoard().items;
    expect(items.some((i) => i.wetransfer_pending)).toBe(true);
    expect(finishState(items.find((i) => i.matter_id === "9010")!)).toBe("leaving");
    expect(finishState(items.find((i) => i.matter_id === "9011")!)).toBe("gone");
  });
});

describe("the WeTransfer dialog", () => {
  const src = readFileSync(fileURLToPath(new URL("../components/StatusBoardCompact.tsx", import.meta.url)), "utf8");
  const css = readFileSync(fileURLToPath(new URL("../app/statusboard.css", import.meta.url)), "utf8");
  it("unmounts on No, Escape and the backdrop (open state, not hidden) and leaves the button", () => {
    expect(src).toContain("{open && (");
    expect(src).toContain("setOpen(false)");

    const confirm = readFileSync(fileURLToPath(new URL("../components/BoardConfirm.tsx", import.meta.url)), "utf8");
    expect(src).toContain("<BoardConfirm");
    expect(confirm).toContain('event.key === "Escape"');
    expect(confirm).toContain("event.stopPropagation()");
    expect(confirm).toContain("createPortal(");
  });
  it("is a sensible width, wraps its question and does not clip it", () => {
    expect(css).toMatch(/\.sb-wetransfer-dialog \{[^}]*width: min\(28rem, calc\(100vw - 2rem\)\)/);
    expect(css).toMatch(/\.sb-wetransfer-dialog \{[^}]*white-space: pre-line/);
    expect(css).not.toMatch(/\.sb-wetransfer-dialog[^}]*overflow:\s*hidden/);
  });
  it("the WeTransfer cell button is plain words, not a pill", () => {
    expect(src).not.toMatch(/className="cf-btn[^"]*sb-wetransfer"/);
    const rule = css.match(/\.sb-wetransfer \{([^}]*)\}/)![1];
    expect(rule).toContain("background: none");
    expect(rule).toContain("border: 0");
    expect(rule).toContain("color: inherit");
    expect(rule).toContain("cursor: pointer");
    expect(css).toMatch(/\.sb-wetransfer:hover \{ text-decoration: underline/);
    expect(css).toMatch(/\.sb-wetransfer:focus-visible \{ outline:/);
    expect(src).toContain('aria-label="WeTransfer: download permission needed"');
  });
  it("the WeTransfer button is exactly the dash colour: it inherits from a cell that carries the dash's class", () => {
    expect(css).toMatch(/\.sb-compact-empty \{ color: var\(--[a-z-]+\); \}/);
    expect(src).toMatch(/<td key=\{c\.key\} className="sb-compact-empty">\s*<WetransferGate/);
    expect(css.match(/\.sb-wetransfer \{([^}]*)\}/)![1]).not.toMatch(/color: var\(/);
  });
});

describe("a client who has not signed is carried forward until they sign", () => {
  const now = new Date("2026-11-16T12:00:00Z");
  const newest = Array.from({ length: COMPACT_ROWS }, (_, n) => item(`n${n}`, `New ${n}`, `2026-11-${String(10 + n).padStart(2, "0")}`));
  const waiting = item("w1", "Waiting One", "2026-09-01", { contacted: "2026-09-03T10:00:00Z" });
  const signed = { ...item("s1", "Signed One", "2026-09-02", { contacted: "2026-09-03T10:00:00Z" }), initial_ws: "2026-09-10T10:00:00Z" };
  const notContacted = item("c0", "Not Contacted", "2026-09-04");

  it("waits only between Contacted and WS Signed", () => {
    expect(awaitingSignature(waiting)).toBe(true);
    expect(awaitingSignature(signed)).toBe(false);
    expect(awaitingSignature(notContacted)).toBe(false);
  });
  const recent = item("w2", "Waiting Two", "2026-10-18", { contacted: "2026-10-20T10:00:00Z" });
  it("keeps an unsigned client past the newest seven for 30 days, and drops them once they sign", () => {
    const rows = boardRows([...newest, recent, signed, notContacted], now);
    expect(rows.map((r) => r.matter_id)).toContain("w2");
    expect(rows.map((r) => r.matter_id)).not.toContain("s1");
    expect(rows.map((r) => r.matter_id)).not.toContain("c0");
    expect(rows).toHaveLength(COMPACT_ROWS + 1);

    expect(rows[rows.length - 1].matter_id).toBe("w2");
    const afterSigning = boardRows([...newest, { ...recent, initial_ws: "2026-11-15T09:00:00Z" }], now);
    expect(afterSigning.map((r) => r.matter_id)).not.toContain("w2");
  });
  it("drops a client 31 days after contact, signed or not: they are on the full Status board only", () => {
    expect(boardRows([...newest, waiting], now).map((r) => r.matter_id)).not.toContain("w1");
    expect(boardAge(recent, now)).toBe(27);
    expect(boardRows([recent], new Date("2026-11-19T12:00:00Z"))).toHaveLength(1);
    expect(boardRows([recent], new Date("2026-11-20T12:00:00Z"))).toHaveLength(0);
    expect(boardAge(item("r", "Referred Only", "2026-11-01"), now)).toBe(15);
  });
  it("counts the days waiting in London days since Contacted", () => {
    expect(daysWaiting(waiting, now)).toBe(74);
    expect(daysWaiting(signed, now)).toBeNull();
    expect(daysWaiting(item("t", "Today", "2026-11-16", { contacted: "2026-11-16T08:00:00Z" }), now)).toBe(0);

    expect(daysWaiting(item("b", "Boundary", "2026-10-30", { contacted: "2026-10-31T23:30:00Z" }), now)).toBe(16);
    expect(waitingLabel(0)).toBe("Waiting since today");
    expect(waitingLabel(1)).toBe("Waiting 1 day");
    expect(waitingLabel(74)).toBe("Waiting 74 days");
  });
  it("draws the days waiting beside the name, and no tick mark anywhere", () => {
    const html = renderToStaticMarkup(createElement(StatusBoardTable, { items: [waiting, signed], now }));
    expect(html).toContain("Waiting 74 days");
    expect(html.match(/sb-waiting-tag/g)).toHaveLength(1);
    const page = readFileSync(fileURLToPath(new URL("../app/status-board/page.tsx", import.meta.url)), "utf8");
    expect(page).not.toContain("IconCheck");
    expect(page).toContain("<WaitingTag days={daysWaiting(r)} />");
  });
});
