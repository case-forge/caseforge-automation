import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  BODY_HEAD_CHARS,
  answerReady,
  expiryLabel,
  safeOutlookLink,
  splitBody,
  startingItem,
  summaryLines,
  type MailReviewOverview,
} from "./mailReview";

const overview = (patch: Partial<MailReviewOverview> = {}): MailReviewOverview => ({
  total: 4,
  answered: 2,
  routes: ["route_a", "route_b"],
  counts: { route_a: 1, route_b: 0 },
  no_clean_answer: 1,
  first_unanswered: 3,
  items: [],
  expires_utc: "2026-11-13T12:34:00Z",
  expired: false,
  ...patch,
});

describe("Improve mail classifier", () => {
  it("opens on the first unanswered email, else the last", () => {
    expect(startingItem(overview())).toBe(3);
    expect(startingItem(overview({ first_unanswered: null }))).toBe(4);
  });

  it("summarises answered N of M and the routes used", () => {
    expect(summaryLines(overview())).toEqual(["Answered 2 of 4", "route_a: 1", "No clean answer: 1"]);
  });

  it("offers only an https Outlook link", () => {
    expect(safeOutlookLink("https://outlook.example/x")).toBe("https://outlook.example/x");
    expect(safeOutlookLink("javascript:alert(1)")).toBeNull();
    expect(safeOutlookLink("http://outlook.example/x")).toBeNull();
    expect(safeOutlookLink("")).toBeNull();
  });

  it("splits a long body like the earlier form and needs some answer", () => {
    const { head, rest } = splitBody("x".repeat(BODY_HEAD_CHARS + 5));
    expect([head.length, rest.length]).toEqual([BODY_HEAD_CHARS, 5]);
    expect(splitBody("").head).toBe("(no text body)");
    expect(answerReady("", false, "  ")).toBe(false);
    expect(answerReady("", true, "")).toBe(true);
  });

  it("shows the expiry, and says read only once expired", () => {
    expect(expiryLabel("2026-11-13T12:34:00Z", false)).toBe("Open until 13 Nov 2026, 12:34 UTC");
    expect(expiryLabel("2026-11-13T12:34:00Z", true)).toContain("read only");
  });

  it("never renders email content as HTML", () => {
    const page = readFileSync(fileURLToPath(new URL("../app/review-mail/page.tsx", import.meta.url)), "utf8");
    expect(page).not.toContain("dangerouslySetInnerHTML");
    expect(page).not.toContain("innerHTML");
    const card = readFileSync(fileURLToPath(new URL("../components/MailEmailCard.tsx", import.meta.url)), "utf8");
    expect(card).not.toContain("innerHTML");
    expect(card).toContain("safeOutlookLink(");
  });
});

describe("the eight destinations", () => {
  it("shows the destination word and, for Other, the text that says where", async () => {
    const { shownDestination, controlSentence, promptQuestion } = await import("./mailReview");
    expect(shownDestination({ applied_route: "Legal Aid Confirmation", applied_destination: "Legal Aid" })).toBe("Legal Aid");
    expect(shownDestination({ applied_route: "Review", applied_destination: "Other", applied_other_text: "From the respondent" })).toBe("Other (From the respondent)");
    expect(shownDestination({ applied_route: "Other Side", applied_destination: "Other Side", applied_other_text: "GP" })).toBe("Other Side (GP)");
    expect(shownDestination({ applied_route: "Court" })).toBe("Court");
    expect(controlSentence({ applied_route: "GP", applied_destination: "Other", applied_other_text: "GP" })).toBe("The classifier thinks this goes to Other (GP). Do you agree?");
    expect(promptQuestion({ applied_route: "Court" }).lead).toContain("\u201cCourt\u201d");
  });

  it("offers Other with a typed destination in every route picker and never offers Review, GP or School", () => {
    const picker = readFileSync(fileURLToPath(new URL("../components/MailRoutePicker.tsx", import.meta.url)), "utf8");
    expect(picker).toContain('value === "Other"');
    expect(picker).toContain("onOtherText");
    for (const file of ["MailReviewTab", "MailControlTab", "ClassifierPrompt"]) {
      const source = readFileSync(fileURLToPath(new URL(`../components/${file}.tsx`, import.meta.url)), "utf8");
      expect(source).toContain("other_text");
    }
    const stub = readFileSync(fileURLToPath(new URL("./stubMailReview.ts", import.meta.url)), "utf8");
    expect(stub).toContain('"Client", "Counsel", "Court", "Legal Aid", "Other Side", "Process Server", "Junk", "Other"');
    expect(stub).not.toMatch(/const ROUTES = [^;]*"(Review|GP|School)"/);
  });
});
