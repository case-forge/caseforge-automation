import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { NextRequest } from "next/server";
import * as route from "../app/api/today/route";
import {
  asOf,
  draftLinkText,
  isStepTile,
  itemLine,
  stepLine,
  scheduledLabel,
  safeLink,
  sectionHeading,
  showTodayBoard,
  tileLink,
  stepAge,
  visibleSections,
  type TodayBoardData,
  type TodaySection,
} from "./todayBoard";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const section = (key: string, count: number, patch: Partial<TodaySection> = {}): TodaySection => ({
  key,
  title: key,
  count,
  items: Array.from({ length: count }, (_, i) => ({ matter_id: String(i), client_name: `Client ${i}` })),
  error: false,
  ...patch,
});

const board = (sections: TodaySection[]): TodayBoardData => ({
  today: "2026-10-15",
  tomorrow: "2026-10-16",
  sections,
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("Today board", () => {
  it("hides empty sections and keeps a failed one, said so", () => {
    const shown = visibleSections(board([section("step_3", 0), section("drafts", 2), section("steps", 0, { error: true })]));
    expect(shown.map((s) => s.key)).toEqual(["drafts", "steps"]);
    expect(sectionHeading(shown[1])).toBe("steps: unavailable");
    expect(visibleSections(null)).toEqual([]);
  });

  it("describes a pit stop in plain words", () => {
    expect(itemLine("waiting_court", { matter_id: "1", client_name: "A", label: "WAITING FOR COURT" })).toBe("Waiting for court · nothing to do until they reply");
    expect(itemLine("waiting_counsel", { matter_id: "1", client_name: "A", label: "WAITING FOR COUNSEL" })).toBe("Waiting for counsel · nothing to do until they reply");
    expect(itemLine("reminders", { matter_id: "1", client_name: "A", subject: "X - update requested" })).toBe("X - update requested");
    expect(itemLine("drafts", { matter_id: "1", client_name: "A", subject: "Forms" })).toBe("Forms");
  });

  it("serves the flat sections in the hub's order: the steps, other drafts, then what we wait on others for", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const res = await route.GET(new NextRequest("http://localhost/api/today?person=Sam"));
    const keys = ((await res.json()) as TodayBoardData).sections.map((s) => s.key);
    expect(keys).toEqual(["step_3", "step_4", "step_5", "step_6", "step_7", "reminders", "drafts", "waiting_client", "waiting_court", "waiting_counsel"]);
  });

  it("counts in the heading, and says when a list was cut", () => {
    expect(sectionHeading(section("drafts", 2))).toBe("drafts (2)");
    expect(sectionHeading({ ...section("drafts", 2), count: 70 })).toBe("drafts (2 of 70)");
  });

  it("shows only before anything is searched, listed or open", () => {
    expect(showTodayBoard("", null, false)).toBe(true);
    expect(showTodayBoard("al", null, false)).toBe(false);
    expect(showTodayBoard("", "Flagged", false)).toBe(false);
    expect(showTodayBoard("", null, true)).toBe(false);
  });

  it("offers only https draft links and renders no HTML", () => {
    expect(safeLink("https://outlook.example/x")).toBe("https://outlook.example/x");
    expect(safeLink("javascript:alert(1)")).toBeNull();
    const source = readFileSync(fileURLToPath(new URL("../components/TodayBoard.tsx", import.meta.url)), "utf8");
    expect(source).not.toContain("dangerouslySetInnerHTML");
  });

  it("asks the hub's read-only route for everyone's clients, with no person or scope", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ sections: [] })));
    vi.stubGlobal("fetch", fetchMock);
    await route.GET(new NextRequest("http://localhost/api/today"));
    const first = new URL(String(fetchMock.mock.calls[0][0]));
    expect(first.pathname).toBe("/client-viewer/today");
    expect([...first.searchParams.keys()]).toEqual([]);
  });
});

describe("Today board heading", () => {
  it("is the plain Today board for everyone's clients: no dropdown, no assigned wording", () => {
    const board = readFileSync(fileURLToPath(new URL("../components/TodayBoard.tsx", import.meta.url)), "utf8");
    expect(board).toContain("<h2>Today</h2>");
    expect(board).not.toContain("<select");
    expect(board).not.toMatch(/assign|Whose clients|My clients/i);
    for (const gone of ["draggable", "today-grid", "today-tile", "Reset order", "moveSection"]) expect(board).not.toContain(gone);
  });
});

const rowItem = (patch: Record<string, unknown> = {}) => ({ matter_id: "1", client_name: "A", ...patch });

describe("Today board step sections", () => {
  it("knows the five step tiles and not the other sections", () => {
    for (const key of ["step_3", "step_4", "step_5", "step_6", "step_7"]) expect(isStepTile(key)).toBe(true);
    for (const key of ["step_2", "step_8", "hearings", "drafts", "step_3x"]) expect(isStepTile(key)).toBe(false);
  });

  it("says whose turn it is on a step row", () => {
    expect(itemLine("step_3", rowItem({ state: "yours", line: "The email is drafted." }))).toBe("Your turn · The email is drafted.");
    expect(itemLine("step_6", rowItem({ state: "flow", line: "Waiting for the forms." }))).toBe("Case flow · Waiting for the forms.");
  });

  it("opens the draft, the folder or the portal, only over https", () => {
    expect(tileLink(rowItem({ link: { kind: "draft", label: "Open the draft in Outlook", url: "https://outlook.example/d" } }))).toEqual({ kind: "draft", label: "Open the draft in Outlook", url: "https://outlook.example/d" });
    expect(tileLink(rowItem({ link: { kind: "portal", label: "", url: "https://portal.example/" } }))?.label).toBe("Open the portal");
    expect(tileLink(rowItem({ link: { kind: "draft", label: "x", url: "javascript:alert(1)" } }))).toBeNull();
    expect(tileLink(rowItem({ link: { kind: "other", label: "x", url: "https://a.example/" } }))).toBeNull();
    expect(tileLink(rowItem({ link: {} }))).toBeNull();
    expect(tileLink(rowItem())).toBeNull();
  });

  it("says where a client is now and for how long, and nothing for a row without it", () => {
    const p = stepAge(rowItem({ at_step: { current: "Application emailed to the court", days: 3, quiet: false } }));
    expect(p).toEqual({ current: "Application emailed to the court", days: 3, quiet: false });
    expect(stepLine(p!)).toBe("now at Application emailed to the court · 3 days here");
    expect(stepLine({ current: "", days: 1, quiet: true })).toBe("1 day here · quiet");
    expect(stepLine({ current: "", days: 0, quiet: false })).toBe("today");
    expect(stepLine({ current: "Court pack ready", days: null, quiet: false })).toBe("now at Court pack ready");
    expect(stepAge(rowItem())).toBeNull();
  });
});

describe("Today board as-of time", () => {
  const now = new Date("2026-11-03T15:00:00Z");

  it("says the time for today and the date for another day, in London time", () => {
    expect(asOf("2026-11-03T08:05:00Z", now)).toBe("as of 08:05");
    expect(asOf("2026-08-03T08:05:00Z", new Date("2026-08-03T15:00:00Z"))).toBe("as of 09:05");
    expect(asOf("2026-10-30T08:05:00Z", now)).toBe("as of 30 Oct");
  });

  it("says nothing for a time that does not read", () => {
    expect(asOf("", now)).toBe("");
    expect(asOf("not a date", now)).toBe("");
    expect(asOf(undefined, now)).toBe("");
  });
});

describe("scheduled drafts", () => {
  const item = (scheduled_utc?: string) => ({ matter_id: "1", client_name: "Test", ...(scheduled_utc ? { scheduled_utc } : {}) });

  it("says when a scheduled draft leaves, in London time", () => {
    expect(scheduledLabel("2026-11-04T09:45:00Z")).toBe("scheduled to leave 09:45 on 4 Nov");
    expect(scheduledLabel("2026-07-01T08:00:00Z")).toBe("scheduled to leave 09:00 on 1 Jul");
    expect(draftLinkText(item("2026-11-04T09:45:00Z"))).toBe("Open draft, scheduled to leave 09:45 on 4 Nov");
  });

  it("is a plain Open draft when nothing is scheduled", () => {
    expect(draftLinkText(item())).toBe("Open draft");
    expect(draftLinkText(item(""))).toBe("Open draft");
    expect(scheduledLabel("not a time")).toBe("");
    expect(scheduledLabel(undefined)).toBe("");
  });
});
