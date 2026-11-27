
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (name: string) => readFileSync(fileURLToPath(new URL(`./${name}`, import.meta.url)), "utf8");
const strip = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

describe("header chrome", () => {
  it("has no Recently viewed clock in the header or the apps menu; it is a dropdown on the search row", () => {
    expect(read("Shell.tsx")).not.toContain("Recently viewed");
    expect(read("AppDrawer.tsx")).not.toContain("Recently viewed");
    expect(read("../components/Workspace.tsx")).toContain("<RecentlyViewedMenu");
  });

  it("puts the special sender's badge before the name, chosen by the firm's own list and not by anything in code", () => {
    const row = read("NotificationRow.tsx");
    expect(row).toContain("<SpecialSenderBadge sender={special.sender} />");
    expect(row.indexOf("<SpecialSenderBadge")).toBeLessThan(row.indexOf("{notificationTitle(n)}"));
    expect(row).toContain("useSpecialSenders()");
    for (const word of ["isThreeBcDomain", "ThreeBcBadge", "referralpartnerBadge"]) expect(row).not.toContain(word);
  });

  it("draws a sender's own logo when it has one and its initials until then", () => {
    const badge = read("SenderBadge.tsx");
    expect(badge).toContain("senderLogoSrc(sender)");
    expect(badge).toContain("senderInitials(sender.name)");
  });
});

describe("one bell", () => {
  it("has the smiley and frowny gone from the header, and one bell fed by the hub's notifications", () => {
    const shell = read("Shell.tsx");
    expect(shell).not.toContain("StatementReplyLists");
    expect(shell.match(/<AttentionBell/g)).toHaveLength(1);
    const bell = read("AttentionBell.tsx");
    expect(bell).toContain('href="/notification-board"');
    expect(bell).toContain("useNotifications()");
    expect(bell).not.toContain("useIntakeTray");
  });

  it("lists only what the hub put on the bell (the last 3 days) and points at the board for the rest", () => {
    const bell = strip(read("AttentionBell.tsx"));
    expect(bell).toContain("urgentOnly(view)");
    expect(bell).toContain("orderForBell(urgent.bell)");
    expect(bell).toContain("Notification board");
    expect(bell).toContain("BELL_DAYS");
  });

  it("gives every row a Done where the hub holds one, plus Dismiss / Hide that only change the person's own state", () => {
    const row = strip(read("NotificationRow.tsx"));
    expect(row).toContain("<DoneButton");
    expect(row).toContain("rowActions(n.status)");
    expect(row).toContain("onState(n.nid, action.state)");
  });

  it("announces a new client and offers no way to assign one", () => {
    const row = strip(read("NotificationRow.tsx"));
    expect(row).toContain('n.source === "new_matter"');
    expect(row).not.toContain("assign");
  });
});

describe("the Notification board", () => {
  const board = strip(read("NotificationBoard.tsx"));

  it("is reached from the apps menu and the bell, and is a page of its own", () => {
    expect(strip(read("AppDrawer.tsx"))).toContain("<span>Notification Board</span>");
    expect(strip(read("AppDrawer.tsx"))).toContain('href="/notification-board"');
    expect(strip(read("../app/notification-board/page.tsx"))).toContain("<NotificationBoardPage />");
    expect(strip(read("../components/Workspace.tsx"))).not.toContain("NotificationBoardView");
  });

  it("flips between Human and Automation", () => {
    expect(board).toContain('{ key: "human", label: "Human" }');
    expect(board).toContain('{ key: "robot", label: "Automation" }');
    expect(board).toContain("aria-pressed={side === s.key}");
  });

  it("has Active, Dismissed and Hidden lists, and reads on open and on Refresh, never on a timer", () => {
    expect(strip(read("../lib/notificationRules.ts"))).toContain('{ key: "active", label: "Active" }');
    expect(strip(read("../lib/notificationRules.ts"))).toContain('{ key: "dismissed", label: "Dismissed" }');
    expect(strip(read("../lib/notificationRules.ts"))).toContain('{ key: "hidden", label: "Hidden" }');
    expect(board).not.toContain("setInterval");
    expect(board).not.toContain("startVisiblePoll");
    expect(board).toContain("void load()");
  });

  it("makes no write of its own: dismiss, hide and put back go through one helper, and the automation side only dismisses through the automation notices hook", () => {
    expect(board).not.toMatch(/method:\s*["'](POST|PUT|PATCH|DELETE)/);
    expect(board).toContain("setNotificationState(nid, state");
    expect(board).toContain("useRobotNotices()");
  });

  it("covers the empty, loading, error and filtered states", () => {
    for (const text of ["Reading the Notification board", "No notification here matches.", 'role="alert"', "Nothing is hidden.", "Nothing has been dismissed."]) {
      expect(board).toContain(text);
    }
  });

  it("only answers for the newest read", () => {
    expect(board).toContain("mine === latest.current");
  });

  it("shows only Case flow blocks in the header, sends the rest to the board, and opens the same board", () => {
    const robot = read("RobotNotices.tsx");
    expect(robot).toContain("splitNotices(data.items)");
    expect(robot).toContain("Other Automation notices ({more}) are on the Notification board");
    expect(robot).toContain("<BlockedPopup blocked={shown}");
    expect(robot).toContain("A notice clears itself when the step is fixed");
    expect(robot).toContain('href="/notification-board"');
    expect(read("Shell.tsx")).toContain("<RobotNotices onOpenClient={onOpenClientByName} />");
  });
});

describe("bell row buttons and the court badge", () => {
  it("puts Open email before Open client, each with its Lucide icon in front of the label", () => {
    const row = read("NotificationRow.tsx");
    const email = row.indexOf("Open email");
    expect(email).toBeGreaterThan(0);
    for (let at = row.indexOf("Open client"); at >= 0; at = row.indexOf("Open client", at + 1)) {
      expect(email).toBeLessThan(at);
    }
    expect(row).toContain("<IconEnvelope aria-hidden=\"true\" /> Open email");
    expect(row.match(/<IconPerson aria-hidden="true" \/> Open client/g)?.length).toBe(3);
  });

  it("shows a courthouse badge for the court, beside the other sender badges", () => {
    const row = read("NotificationRow.tsx");
    expect(row).toContain("isCourtItem(n.item) && <CourtBadge />");
    expect(row.indexOf("<CourtBadge />")).toBeLessThan(row.indexOf("{notificationTitle(n)}"));
    const badge = read("SenderBadge.tsx");
    expect(badge).toContain("<IconLandmark");
    expect(badge).toContain('aria-label="Court"');
    expect(read("icons.tsx")).toContain('name="landmark"');
  });
});
