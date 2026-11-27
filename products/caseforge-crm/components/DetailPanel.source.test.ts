
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(fileURLToPath(new URL("./DetailPanel.tsx", import.meta.url)), "utf8");

describe("DetailPanel.tsx source", () => {
  it("never marks the NI Number field as C8-sensitive", () => {

    const legalAid = readFileSync(new URL("./LegalAidSection.tsx", import.meta.url), "utf8");
    const block = legalAid.slice(legalAid.indexOf("NI Number") - 200, legalAid.indexOf("NI Number") + 400);
    expect(legalAid).toContain("NI Number");
    expect(block).not.toContain("c8");
    expect(block).not.toContain("sensitive");
    expect(SOURCE).not.toContain('<Field label="NI Number"');
  });

  it("only phone, email and address carry a C8 control, each its own flag", () => {
    const c8Lines = SOURCE.split("\n").filter((line) => line.includes("c8={c8Control("));
    expect(c8Lines).toHaveLength(3);
    expect(c8Lines.some((line) => line.includes("Telephone") && line.includes('"c8_phone"'))).toBe(true);
    expect(c8Lines.some((line) => line.includes("Email") && line.includes('"c8_email"'))).toBe(true);
    expect(c8Lines.some((line) => line.includes("ClientAddressField") && line.includes('"c8_address"'))).toBe(true);
  });

  it("has Attendance Notes on the main page and Billing on the extra-details page, and only the first holds the note form", () => {
    const main = SOURCE.slice(SOURCE.indexOf("const MAIN_TABS"), SOURCE.indexOf("const EXTRA_TABS"));
    const extra = SOURCE.slice(SOURCE.indexOf("const EXTRA_TABS"), SOURCE.indexOf("interface CaseTab"));
    expect(main).toContain('["attendance", "Attendance Notes"]');
    expect(extra).toContain('["billing", "Billing"]');
    expect(SOURCE).toContain("<IconDrawer");
    const billing = SOURCE.slice(SOURCE.indexOf("function BillOfCostsSection"), SOURCE.indexOf("function C8Checkbox"));
    expect(billing).not.toContain("AttendanceNoteForm");
    expect(SOURCE.match(/<AttendanceNoteForm/g)).toHaveLength(1);
  });

  it("puts the case switcher in the header actions, ahead of Flag, Star and Attendance note, not inside a tab", () => {
    const actions = SOURCE.slice(SOURCE.indexOf('className="detail-title-actions'));
    expect(actions.indexOf('className="case-select"')).toBeGreaterThan(-1);
    expect(actions.indexOf('className="case-select"')).toBeLessThan(actions.indexOf("<HeaderFlagToggles"));
    expect(SOURCE).not.toContain("detail-case-switch");
  });

  it("has no Attendance note button in the header; Flag and Star close the row in the top-right corner", () => {
    const actions = SOURCE.slice(SOURCE.indexOf('className="detail-title-actions no-print"'), SOURCE.indexOf('<p className="detail-subtitle">'));
    expect(actions).not.toContain("an-launcher-top");
    expect(actions).not.toContain("Attendance note");
    expect(actions).toContain("<HeaderFlagToggles");
    expect(actions.indexOf("<HeaderFlagToggles")).toBeGreaterThan(actions.indexOf("case-select"));
    expect(actions.indexOf("<IconDrawer")).toBeGreaterThan(actions.indexOf("<HeaderFlagToggles"));
    const toggles = readFileSync(fileURLToPath(new URL("./HeaderFlagToggles.tsx", import.meta.url)), "utf8");
    expect(toggles).toContain('name: "flagged"');
    expect(toggles).toContain('name: "starred"');
  });

  it("shows the Letter of authority and 1st witness statement markers in the Details tab's Case section, not the Client tab", () => {
    const clientTab = SOURCE.slice(SOURCE.indexOf('detailTab === "client" && ('), SOURCE.indexOf('detailTab === "details" && ('));
    const caseSection = SOURCE.slice(SOURCE.indexOf('<h3 className="detail-section-title">Case</h3>'), SOURCE.indexOf("Property &amp; means"));
    expect(clientTab).not.toContain("<MatterMarkers");
    expect(caseSection).toContain("<MatterMarkers");
  });

  it("splits the tabs in two pages: the cards icon opens the extra-details page", () => {
    const main = SOURCE.slice(SOURCE.indexOf("const MAIN_TABS"), SOURCE.indexOf("const EXTRA_TABS"));
    const extra = SOURCE.slice(SOURCE.indexOf("const EXTRA_TABS"), SOURCE.indexOf("interface CaseTab"));
    for (const id of ["client", "details", "caseflow", "attendance", "todo"]) expect(main).toContain(`["${id}"`);
    for (const id of ["vergil", "scanner", "billing", "hearings", "updates", "case-review", "activity"]) expect(extra).toContain(`["${id}"`);
    for (const id of ["vergil", "scanner", "billing", "hearings", "updates", "case-review", "activity"]) expect(main).not.toContain(`["${id}"`);
    expect(extra).toMatch(/\["hearings", "Hearings"\],\s*\["updates", "Updates"\]/);
    expect(SOURCE).toContain("(onExtraPage ? EXTRA_TABS : MAIN_TABS).map(");
  });

  it("has Hearings and Updates as two tabs over the one list, each showing its own half", () => {
    const start = SOURCE.indexOf('{(detailTab === "hearings" || detailTab === "updates") && (');
    const block = SOURCE.slice(start, SOURCE.indexOf("{detailTab ===", start + 10));
    expect(block).toContain("<HearingsUpdatesTab");
    expect(block).toContain("view={detailTab}");
    expect(block).toContain("tasks={matterTasks}");
    expect(block).toContain("focusHearing={focusHearing}");
    expect(SOURCE).toContain("setFocusHearing(openTab.hearingId != null ? { hearingId: openTab.hearingId, nonce: openTab.nonce } : null);");
    expect(SOURCE).toContain('tabCount(label, upcomingHearings, "upcoming hearing", "upcoming hearings")');
    expect(SOURCE).toContain('tabCount(label, openUpdates, "open update", "open updates")');
    expect(SOURCE).toContain("setDetailTab(landingTab(openTab.tab));");
  });

  it("keeps every hearing action in the combined tab: add, open to edit, vacate and history via the drawer", () => {
    const hearings = readFileSync(fileURLToPath(new URL("./MatterHearings.tsx", import.meta.url)), "utf8");
    expect(hearings).toContain("Add hearing for this client");

    expect(hearings).toContain("hearingsHost.openEdit(h)");
    expect(hearings).toContain("hearingsHost.openCreate({");
    const tasks = readFileSync(fileURLToPath(new URL("./MatterTasks.tsx", import.meta.url)), "utf8");
    expect(tasks).toContain("Open email");
  });

  it("renders each tab as one list in timeline order, with Add hearing above it and each hearing labelled", () => {
    const hearings = readFileSync(fileURLToPath(new URL("./MatterHearings.tsx", import.meta.url)), "utf8");
    const tab = hearings.slice(hearings.indexOf("export function HearingsUpdatesTab"));
    expect(tab).toContain("const entries = hearingsAndUpdates(hearings, items).filter(");

    expect(tab.match(/<ul /g)).toHaveLength(1);
    expect(tab).toContain('entry.kind === "hearing" ? (');
    expect(tab).toContain("<HearingRow ");
    expect(tab).toContain("<UpdateRow ");
    expect(tab.indexOf("Add hearing for this client")).toBeLessThan(tab.indexOf("<ul "));

    expect(hearings).not.toContain("splitMatterHearings");
    expect(hearings).not.toContain("PAST_VISIBLE");

    const row = hearings.slice(hearings.indexOf("function HearingRow"), hearings.indexOf("export interface FocusHearing"));
    expect(row).toContain('<span className="matter-hearing-kind">Hearing</span>');
    expect(row).toContain("matter-hearing-court");
    expect(row).toContain("formatTime12(hearing.hearing_time)");
    expect(row).toContain("<HearingBadges hearing={hearing} />");
    expect(row).toContain("data-hearing-id={hearing.hearing_id}");
    expect(tab).toContain("scrollIntoView");
  });

  it("does not repeat the next hearing in the Case section, because the Hearings tab has it", () => {
    const caseSection = SOURCE.slice(SOURCE.indexOf('<h3 className="detail-section-title">Case</h3>'), SOURCE.indexOf("Property &amp; means"));
    expect(caseSection).not.toContain('label="Next hearing"');
  });

  it("names the markers in full", () => {
    const markers = readFileSync(fileURLToPath(new URL("./MatterMarkers.tsx", import.meta.url)), "utf8");
    expect(markers).toContain('label="Letter of authority"');
    expect(markers).toContain('label="1st witness statement"');
    expect(markers).not.toContain('label="LoA"');
    expect(markers).not.toContain('label="Initial WS"');
  });

  it("has Export CSV and Print on the Billing tab's top row, hidden when printing, and no folder write", () => {
    const start = SOURCE.indexOf("function BillOfCostsSection");
    const billing = SOURCE.slice(start, SOURCE.indexOf("\nfunction ", start + 10));
    expect(billing).toContain("Export CSV");
    expect(billing).not.toContain("Export PDF");
    expect(billing).toMatch(/billing-actions no-print/);
    expect(billing).toContain("/api/clients/bill-of-costs/export?matter_id=");
    expect(billing.indexOf("billing-actions")).toBeLessThan(billing.indexOf("billing-print-area"));
    expect(billing).not.toContain("Export bill to client folder");
    expect(billing).not.toContain("exportBill(");
  });

  it("prints A4 portrait", () => {
    const css = readFileSync(fileURLToPath(new URL("../app/globals.css", import.meta.url)), "utf8");
    expect(css).toMatch(/@page\s*\{\s*size: A4 portrait;\s*margin: 15mm;/);
  });

  it("shows the court and its email as two read-only fields", () => {
    expect(SOURCE).toContain('<Field label="Court" value={courtDetails.name} />');
    expect(SOURCE).toContain('<Field label="Court email" value={courtDetails.email} />');
  });
});

describe("billing lines that point at the same email", () => {
  it("link the line to its email or document and mark a possible double bill beside the description", () => {
    const panel = readFileSync(new URL("./DetailPanel.tsx", import.meta.url), "utf8");
    expect(panel).toContain("Open the email or note this line bills, in SharePoint");
    expect(panel).toContain("item.possible_double_bill ?");
    expect(panel).toContain("Possible double bill");
    expect(readFileSync(new URL("../lib/types.ts", import.meta.url), "utf8")).toContain("possible_double_bill?: boolean;");
  });
});
