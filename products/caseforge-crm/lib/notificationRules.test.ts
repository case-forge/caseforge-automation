import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  AUTO_DISMISS_DAYS,
  BELL_DAYS,
  boardRows,
  categoryWords,
  complaintCount,
  daysOld,
  notificationsLabel,
  notificationTitle,
  notificationTone,
  orderForBell,
  ringsBell,
  rowActions,
  sortNotifications,
  specialSender,
  statusFor,
  statusLine,
  tabCount,
  urgentOnly,
  withoutNotification,
} from "./notificationRules";
import { hearingsAndUpdates } from "./hearingsTimeline";
import type { Notification, NotificationBoardData, NotificationsView } from "./notificationRules";
import { stubNotificationBoard, stubNotifications, stubSetNotificationState } from "./stubNotifications";
import type { SpecialSender } from "./specialSenderRules";
import type { AttentionItem } from "./types";

const NOW = new Date("2026-10-21T12:00:00Z");
const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString();
const HOUR = 3_600_000;
const DAY = 24 * HOUR;

function attention(over: Partial<AttentionItem> = {}): AttentionItem {
  return {
    task_id: "a:1", matter_id: "544", who: "Test Person", kind: "update", label: "UPDATE", complaint_domain: "", settlement_stage: "",
    subject: "", summary: "s", deadline: "", importance: "normal", created: "", web_link: "", ...over,
  };
}

function note(over: Partial<Notification> & { category?: string; item?: AttentionItem } = {}): Notification {
  const item = over.item ?? attention({ kind: over.category === "complaint" ? "complaint" : "update" });
  return {
    nid: "t:a:1", source: "attention", category: "task", created: ago(HOUR), matter_id: "544", client: "Test Person", status: "bell",
    auto_dismissed: false, state_by: "", state_utc: "", ...over, item,
  } as Notification;
}

function orderBellItemsIds(list: Notification[]): string[] {
  return orderForBell(list).map((n) => n.nid);
}

describe("the 3-day window and the 7-day automatic dismissal (mirrors the hub)", () => {
  it("keeps three days on the bell, the rest on the board, and dismisses at fourteen days", () => {
    expect(BELL_DAYS).toBe(3);
    expect(AUTO_DISMISS_DAYS).toBe(7);
    expect(statusFor(ago(5 * 60_000), "", NOW)).toEqual({ status: "bell", auto: false });
    expect(statusFor(ago(3 * DAY), "", NOW)).toEqual({ status: "bell", auto: false });
    expect(statusFor(ago(3 * DAY + 60_000), "", NOW)).toEqual({ status: "board", auto: false });
    expect(statusFor(ago(7 * DAY), "", NOW)).toEqual({ status: "board", auto: false });
    expect(statusFor(ago(7 * DAY + 60_000), "", NOW)).toEqual({ status: "dismissed", auto: true });
  });

  it("lets a person's dismissal or hide win over age, and a put-back stop the automatic dismissal", () => {
    expect(statusFor(ago(HOUR), "dismissed", NOW)).toEqual({ status: "dismissed", auto: false });
    expect(statusFor(ago(40 * DAY), "hidden", NOW)).toEqual({ status: "hidden", auto: false });
    expect(statusFor(ago(40 * DAY), "active", NOW)).toEqual({ status: "board", auto: false });
    expect(statusFor(ago(HOUR), "active", NOW)).toEqual({ status: "bell", auto: false });
  });

  it("counts a date that does not read as new, so nothing is lost", () => {
    expect(statusFor("not a date", "", NOW)).toEqual({ status: "bell", auto: false });
    expect(daysOld("nope", NOW)).toBeNull();
    expect(daysOld(ago(5 * DAY + HOUR), NOW)).toBe(5);
  });
});

describe("words, tones and order", () => {
  it("names every kind in words, never colour alone", () => {
    expect(categoryWords("complaint")).toBe("Complaint");
    expect(categoryWords("new_client")).toBe("New client");
    expect(categoryWords("assignment")).toBe("Notification");
    expect(categoryWords("statement_approved")).toBe("✓ Statement approved");
    expect(categoryWords("statement_amend")).toBe("✎ Wants changes");
    expect(categoryWords("counsel_rejected")).toBe("✕ Counsel declined");
    expect(categoryWords("something new")).toBe("Notification");
  });

  it("colours a complaint red, a new client green, an approved statement green, one wanting changes red", () => {
    expect(notificationTone(note({ category: "complaint", item: attention({ kind: "complaint" }) }))).toBe("red");
    expect(notificationTone(note({ category: "new_client", item: attention({ kind: "new_client" }) }))).toBe("green");
    const reply = (state: "approved" | "amend") =>
      ({ nid: "s", source: "statement", category: "x", created: "", matter_id: "1", client: "A", status: "bell", auto_dismissed: false, state_by: "", state_utc: "",
        item: { matter_id: "1", client_name: "A", state, note: "", by: "", recorded_utc: "" } }) as Notification;
    expect(notificationTone(reply("approved"))).toBe("green");
    expect(notificationTone(reply("amend"))).toBe("red");
  });

  it("titles a row by client, falling back to the subject and then the matter", () => {
    expect(notificationTitle(note({ item: attention({ who: "  ", subject: "Signing problem" }) }))).toBe("Signing problem");
    expect(notificationTitle(note({ item: attention({ who: "", subject: "" }) }))).toBe("Unknown sender");
    const arrival = { nid: "n", source: "new_matter", category: "new_client", created: "", matter_id: "7", client: "", status: "bell", auto_dismissed: false, state_by: "", state_utc: "",
      item: { matter_id: "7", client_name: "", created_utc: "" } } as Notification;
    expect(notificationTitle(arrival)).toBe("Matter 7");
  });

  it("lifts complaints above the rest and keeps the hub's order otherwise", () => {
    const list = [note({ nid: "1" }), note({ nid: "2", category: "complaint", item: attention({ kind: "complaint" }) }), note({ nid: "3" })];
    expect(orderForBell(list).map((n) => n.nid)).toEqual(["2", "1", "3"]);
    expect(complaintCount(list)).toBe(1);
    const withSoft = [
      note({ nid: "s", category: "soft_complaint", item: attention({ kind: "complaint", severity: "soft" }) }),
      ...list,
    ];
    expect(orderBellItemsIds(withSoft)).toEqual(["2", "1", "3", "s"]);
    expect(complaintCount(withSoft)).toBe(1);
    expect(notificationTone(withSoft[0])).toBe("amber");
  });

  it("puts the counts in the bell's accessible name", () => {
    expect(notificationsLabel(0, 0, 0)).toBe("Notifications, none open");
    expect(notificationsLabel(0, 0, 4)).toBe("Notifications, none new, 4 more on the board");
    expect(notificationsLabel(3, 1, 0)).toBe("Notifications, 3 new, 1 complaint");
    expect(notificationsLabel(5, 2, 7)).toBe("Notifications, 5 new, 2 complaints, 7 more on the board");
  });
});

describe("what was done to a row, and the buttons it offers", () => {
  it("says who dismissed or hid it, or that the system did", () => {
    expect(statusLine(note({ status: "dismissed", state_by: "Alex" }))).toBe("Dismissed by Alex");
    expect(statusLine(note({ status: "dismissed", auto_dismissed: true }))).toBe("Dismissed automatically after 7 days");
    expect(statusLine(note({ status: "hidden", state_by: "Sam" }))).toBe("Hidden by Sam");
    expect(statusLine(note({ status: "board" }))).toBe("");
  });

  it("offers Dismiss and Hide on a live row, Put back on a dismissed or hidden one", () => {
    expect(rowActions("bell").map((a) => a.state)).toEqual(["dismissed", "hidden"]);
    expect(rowActions("board").map((a) => a.state)).toEqual(["dismissed", "hidden"]);
    expect(rowActions("dismissed").map((a) => a.state)).toEqual(["active", "hidden"]);
    expect(rowActions("hidden").map((a) => a.state)).toEqual(["active", "dismissed"]);
  });

  it("takes a dismissed notification off the bell at once and moves its count, leaving others alone", () => {
    const view: NotificationsView = { now: "", bell_days: 3, auto_dismiss_days: 7, counts: { bell: 2, board: 1, dismissed: 0, hidden: 0 }, bell: [note({ nid: "x" }), note({ nid: "y" })] };
    const out = withoutNotification(view, "x", "dismissed");
    expect(out.bell.map((n) => n.nid)).toEqual(["y"]);
    expect(out.counts).toEqual({ bell: 1, board: 1, dismissed: 1, hidden: 0 });
    expect(withoutNotification(view, "x", "hidden").counts.hidden).toBe(1);
    expect(withoutNotification(view, "nope", "hidden")).toBe(view);
  });
});

describe("the board's lists", () => {
  const board: NotificationBoardData = {
    now: "", bell_days: 3, auto_dismiss_days: 7, counts: { bell: 1, board: 2, dismissed: 1, hidden: 1 },
    bell: [note({ nid: "b" })],
    board: [note({ nid: "o1", client: "Alpha Person", matter_id: "100", item: attention({ who: "Alpha Person" }) }), note({ nid: "o2", client: "Beta Person", matter_id: "200", item: attention({ who: "Beta Person" }) })],
    dismissed: [note({ nid: "d", status: "dismissed" })],
    hidden: [note({ nid: "h", status: "hidden" })],
  };

  it("returns each tab's rows and counts, and filters by name or matter number", () => {
    expect(boardRows(board, "active").map((n) => n.nid)).toEqual(["o1", "o2"]);
    expect(boardRows(board, "dismissed").map((n) => n.nid)).toEqual(["d"]);
    expect(boardRows(board, "hidden").map((n) => n.nid)).toEqual(["h"]);
    expect(boardRows(board, "active", "beta").map((n) => n.nid)).toEqual(["o2"]);
    expect(boardRows(board, "active", "100").map((n) => n.nid)).toEqual(["o1"]);
    expect(boardRows(null, "active")).toEqual([]);
    expect([tabCount(board, "active"), tabCount(board, "dismissed"), tabCount(board, "hidden")]).toEqual([2, 1, 1]);
  });
});

describe("the demo's stub follows the same rules", () => {
  it("puts recent items on the bell, older ones on the board and the oldest dismissed, and moves one when it is dismissed", () => {
    const board = stubNotificationBoard();
    const total = board.bell.length + board.board.length + board.dismissed.length + board.hidden.length;
    expect(total).toBeGreaterThan(0);
    expect(board.counts.bell).toBe(board.bell.length);
    const target = board.bell[0] ?? board.board[0];
    expect(target).toBeDefined();
    expect(stubSetNotificationState(target.nid, "hidden", "Sam")).toEqual({ nid: target.nid, state: "hidden" });
    const after = stubNotificationBoard();
    expect(after.hidden.map((n) => n.nid)).toContain(target.nid);
    expect(stubNotifications().counts.hidden).toBe(after.counts.hidden);
    expect(stubSetNotificationState("x", "deleted", "Sam")).toEqual({ error: "state must be one of dismissed, hidden, active" });
    stubSetNotificationState(target.nid, "active", "Sam");
  });
});

describe("wiring", () => {
  const read = (rel: string) => readFileSync(new URL(rel, import.meta.url), "utf8");

  it("sends a dismissal to the state route and the pulse carries the bell", () => {
    expect(read("./notifications.ts")).toContain('"/api/notifications/state"');
    expect(read("./pulse.ts")).toContain("notifications?: NotificationsView | null");
    expect(read("../app/api/pulse/route.ts")).toContain("notifications: stubNotifications()");
    expect(read("../app/api/notifications/state/route.ts")).toContain('"/client-viewer/notifications/state"');
    expect(read("../app/api/notifications/route.ts")).toContain('"/client-viewer/notifications"');
    expect(read("../app/api/notifications/robot/route.ts")).toContain('"/client-viewer/notifications/robot"');
  });
});

describe("sorting the Notification board", () => {

  const senders: SpecialSender[] = [
    { id: "s1", name: "Test Chambers", domains: ["chambers.example"], new_clients: false, logo: "", mark: null },
    { id: "s2", name: "Test Referrer", domains: [], new_clients: true, logo: "", mark: null },
  ];
  const counsel = note({ nid: "n1", created: ago(5 * DAY), item: attention({ sender_domain: "chambers.example" }) });
  const lookalike = note({ nid: "n2", created: ago(4 * DAY), item: attention({ sender_domain: "notchambers.example" }) });
  const referred = note({ nid: "n3", created: ago(6 * DAY), category: "new_client" });
  const plainNew = note({ nid: "n4", created: ago(3.5 * DAY) });
  const complaint = note({ nid: "n5", created: ago(4.5 * DAY), category: "complaint" });
  const all = [counsel, lookalike, referred, plainNew, complaint];
  const ids = (list: Notification[]) => list.map((n) => n.nid);

  it("knows a special sender by the firm's list: its domain (never a look-alike) or a referred new client", () => {
    expect(specialSender(counsel, senders)?.sender.name).toBe("Test Chambers");
    expect(specialSender(referred, senders)?.sender.name).toBe("Test Referrer");
    expect(specialSender(lookalike, senders)).toBeNull();
    expect(specialSender(plainNew, senders)).toBeNull();
  });

  it("has no special senders until the firm sets some", () => {
    expect(specialSender(counsel, [])).toBeNull();
    expect(ids(sortNotifications(all, "special", []))).toEqual(ids(sortNotifications(all, "newest")));
  });

  it("sorts newest first by default, whatever order the hub sent", () => {
    expect(ids(sortNotifications(all, "newest"))).toEqual(["n4", "n2", "n5", "n1", "n3"]);
  });

  it("puts the special senders first in the firm's order, newest first inside each group", () => {
    expect(ids(sortNotifications(all, "special", senders))).toEqual(["n1", "n3", "n4", "n2", "n5"]);
    const reversed = [senders[1], senders[0]];
    expect(ids(sortNotifications(all, "special", reversed))).toEqual(["n3", "n1", "n4", "n2", "n5"]);
  });

  it("groups by category in words, newest first inside each, and never changes the list it was given", () => {
    const before = ids(all);
    const sorted = sortNotifications(all, "category");
    expect(ids(all)).toEqual(before);
    const words = sorted.map((n) => categoryWords(n.category));
    expect(words).toEqual([...words].sort((a, b) => a.localeCompare(b, "en-GB")));
    expect(ids(sorted).indexOf("n4")).toBeLessThan(ids(sorted).indexOf("n2"));
  });

  it("applies to a board tab after the filter", () => {
    const data = { board: all, dismissed: [], hidden: [], counts: { bell: 0, board: 5, dismissed: 0, hidden: 0 }, now: "", bell_days: 3, auto_dismiss_days: 7, bell: [] } as NotificationBoardData;
    expect(ids(boardRows(data, "active", "", "special", senders)).slice(0, 2)).toEqual(["n1", "n3"]);
    expect(boardRows(data, "active", "nobody matches this", "special", senders)).toEqual([]);
  });
});

describe("switchboard", () => {
  it("has its own words and sorts last with the status chases", () => {
    expect(categoryWords("switchboard")).toBe("Switchboard");
  });
});

describe("only urgent notifications ring the bell", () => {
  const rows = (kind: string, over: Partial<AttentionItem> = {}) => note({ nid: `t:${over.task_id ?? kind}`, item: attention({ kind, ...over }) });

  it("rings for each always-urgent kind whatever its importance", () => {
    for (const kind of ["complaint", "settlement", "counsel_accepted", "counsel_rejected", "court_order", "court_rejected"]) {
      expect(ringsBell(rows(kind, { importance: "low" }))).toBe(true);
    }
  });

  it("does not ring for a routine or low update, a status chase or a switchboard question", () => {
    expect(ringsBell(rows("update", { importance: "normal" }))).toBe(false);
    expect(ringsBell(rows("update", { importance: "low" }))).toBe(false);
    expect(ringsBell(rows("complaint", { severity: "soft" }))).toBe(false);
    expect(ringsBell(rows("switchboard"))).toBe(false);
    expect(ringsBell(rows("scope_creep"))).toBe(false);
  });

  it("rings for any other kind marked high, and keeps new clients ringing", () => {
    expect(ringsBell(rows("update", { importance: "high" }))).toBe(true);
    expect(ringsBell(rows("complaint", { severity: "soft", importance: "high" }))).toBe(true);
    expect(ringsBell(rows("new_client"))).toBe(true);
  });

  it("rings for a new referral email even when routine, but not for an FYI note", () => {
    expect(ringsBell(rows("update", { importance: "normal", label: "NEW REFERRAL" }))).toBe(true);
    expect(ringsBell(rows("update", { importance: "normal", label: "FYI" }))).toBe(false);
  });

  it("takes a routine update out of the bell's list and count, and moves its count to the board", () => {
    const view: NotificationsView = {
      now: NOW.toISOString(), bell_days: 3, auto_dismiss_days: 7, counts: { bell: 3, board: 1, dismissed: 0, hidden: 0 },
      bell: [rows("update", { importance: "normal", task_id: "a:r" }), rows("update", { importance: "high", task_id: "a:h" }), rows("court_order")],
    };
    const out = urgentOnly(view);
    expect(out.bell.map((n) => n.nid)).toEqual(["t:a:h", "t:court_order"]);
    expect(out.bell.map((n) => (n.item as AttentionItem).importance)).toEqual(["high", "normal"]);
    expect(out.counts).toEqual({ bell: 2, board: 2, dismissed: 0, hidden: 0 });
    expect(urgentOnly(out)).toBe(out);
  });

  it("leaves a routine update in the client's Updates list", () => {
    const routine = { task_id: "a:r", kind: "update", importance: "normal", created: "2026-10-21T10:00:00Z", summary: "s" } as never;
    const entries = hearingsAndUpdates([], [routine]);
    expect(entries.map((e) => e.kind)).toEqual(["update"]);
  });
});
