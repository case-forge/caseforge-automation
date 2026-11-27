import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { GROUP_TABS, LEGAL_AID_RATE_PREFIX, fieldForError, loadAppSettings, readDraft, readPeople, sameDraft, saveSettings, type AppSetting } from "./appSettings";
import { resetStubAppSettings, stubAppSettings, stubSave, stubSetOperation } from "./stubAppSettings";

const field = (over: Partial<AppSetting>): AppSetting => ({ ...stubAppSettings(true).settings[0], ...over });

describe("reading a draft", () => {
  it("keeps on and off, and sends a blank as blank so the hub restores the default", () => {
    expect(readDraft(field({ type: "bool" }), true)).toEqual({ ok: true, value: true });
    expect(readDraft(field({ type: "string" }), "  ")).toEqual({ ok: true, value: "" });
    expect(readDraft(field({ type: "string" }), " Leeds ")).toEqual({ ok: true, value: "Leeds" });
  });

  it("checks numbers, emails and folders before anything is sent, in plain words", () => {
    const n = field({ type: "int", label: "Minutes per page", minimum: 1, maximum: 60 });
    expect(readDraft(n, "5")).toEqual({ ok: true, value: 5 });
    expect(readDraft(n, "")).toEqual({ ok: true, value: "" });
    for (const bad of ["0", "61", "2.5", "two", "-1"]) expect(readDraft(n, bad)).toMatchObject({ ok: false });
    expect(readDraft(field({ type: "email", label: "Email" }), "not an email")).toEqual({ ok: false, error: "Email must be an email address." });
    const p = field({ type: "path", label: "Folder" });
    expect(readDraft(p, "/Company_Data/post-room/")).toEqual({ ok: true, value: "/Company_Data/post-room/" });
    for (const bad of ["a/../b", "a//b", "a\\b", "./a"]) expect(readDraft(p, bad)).toMatchObject({ ok: false });
    expect(readDraft(field({ type: "string", max_length: 5, label: "Town" }), "Sampletown")).toEqual({ ok: false, error: "Town is too long." });
  });

  it("finds the field a refusal is about", () => {
    const settings = stubAppSettings(true).settings;
    expect(fieldForError("Minutes per page must be at most 60", settings)).toBe("minutes_per_page");
    expect(fieldForError("Something else entirely", settings)).toBeNull();
  });
});

describe("the calls", () => {
  it("loads, treats an odd answer as an error, and returns the hub's words on a refusal", async () => {
    expect((await loadAppSettings(vi.fn().mockResolvedValue(new Response(JSON.stringify({ nope: 1 }))))).state).toBe("error");
    expect((await loadAppSettings(vi.fn().mockRejectedValue(new Error("x")))).state).toBe("error");
    const view = stubAppSettings(true);
    expect((await loadAppSettings(vi.fn().mockResolvedValue(new Response(JSON.stringify(view))))).state).toBe("ok");
    const refused = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "Minutes per page must be at least 1" }), { status: 422 }));
    expect(await saveSettings({ minutes_per_page: 0 }, refused)).toEqual({ ok: false, message: "Minutes per page must be at least 1" });
    expect(JSON.parse(refused.mock.calls[0][1].body)).toEqual({ values: { minutes_per_page: 0 } });
    expect(refused.mock.calls[0][1].method).toBe("PATCH");
  });

});

describe("the demo settings", () => {
  it("cover every tab, hold no secret, and are read-only for a non-admin", () => {
    resetStubAppSettings();
    const view = stubAppSettings(false);
    expect(view.can_edit).toBe(false);
    for (const g of GROUP_TABS) expect(view.groups.map((x) => x.key)).toContain(g);
    const text = JSON.stringify({ ...view, secrets_note: "" }).toLowerCase();
    expect(text).not.toMatch(/client_secret|api_key|password|token/);
    expect(view.settings.some((s) => s.locked && s.env.startsWith("CASEFORGE_SETTING_"))).toBe(true);
  });

  it("saves in memory, refuses a pinned or bad value, and keeps all or nothing", () => {
    resetStubAppSettings();
    expect(stubSave({ office_town: "Leeds" }, true)).toEqual({ ok: true });
    const view = stubAppSettings(true);
    expect(view.settings.find((s) => s.key === "office_town")).toMatchObject({ value: "Leeds", source: "database" });
    expect(stubSave({ office_town: "York", minutes_per_page: 99 }, true)).toMatchObject({ ok: false, status: 422 });
    expect(stubAppSettings(true).settings.find((s) => s.key === "office_town")?.value).toBe("Leeds");
    expect(stubSave({ email_heading: "Other" }, true)).toMatchObject({ ok: false, status: 409 });
    expect(stubSave({ logo_hash: "x" }, true)).toMatchObject({ ok: false, status: 404 });
    expect(stubSave({ office_town: "York" }, false)).toMatchObject({ ok: false, status: 403 });
    resetStubAppSettings();
  });
});

describe("the legal aid rates", () => {
  const rates = () => stubAppSettings(true).settings.filter((s) => s.key.startsWith(LEGAL_AID_RATE_PREFIX));
  it("lists the standard schedule, takes an edit, and a blank restores the standard rate", () => {
    resetStubAppSettings();
    expect(rates().map((s) => s.value)).toEqual(["5.40", "2.70", "5.40", "59.40", "32.40", "59.40", "28.80"]);
    expect(stubSave({ legal_aid_rate_telephone: "6.10" }, true)).toEqual({ ok: true });
    expect(rates().find((s) => s.key === "legal_aid_rate_telephone")).toMatchObject({ value: "6.10", source: "database" });
    expect(stubSave(Object.fromEntries(rates().map((s) => [s.key, ""])), true)).toEqual({ ok: true });
    expect(rates().every((s) => s.source === "default" && s.value === s.default)).toBe(true);
    resetStubAppSettings();
  });
  it("refuses a rate that is not an amount in pounds", () => {
    expect(readDraft(rates()[0], "free")).toMatchObject({ ok: false });
    expect(readDraft(rates()[0], "£6.1")).toEqual({ ok: true, value: "6.10" });
  });
  it("has one restore button in the settings panel", () => {
    const panel = readFileSync(fileURLToPath(new URL("../components/SettingsGroupPanel.tsx", import.meta.url)), "utf8");
    expect(panel.match(/Restore standard rates/g)).toHaveLength(1);
  });
});

describe("the instructing solicitors", () => {
  const people = () => stubAppSettings(true).settings.find((s) => s.key === "solicitors")!;
  const ada = { name: "A. Sample", email: "solicitor@example.test", role: "Solicitor" };
  const bea = { name: "B. Second", email: "b@example.test", role: "Partner" };

  it("cleans a list and refuses an empty, nameless, badly addressed or repeated one", () => {
    expect(readPeople(people(), [{ ...ada, name: "  A.   Sample " }, bea])).toEqual({ ok: true, value: [ada, bea] });
    for (const bad of [[], [{ ...ada, name: "" }], [{ ...ada, email: "nope" }], [ada, { ...bea, name: "a. sample" }], [{ ...ada, role: "x".repeat(81) }]]) {
      expect(readPeople(people(), bad)).toMatchObject({ ok: false });
    }
    expect(readDraft(people(), "text")).toMatchObject({ ok: false });
  });

  it("compares lists by value", () => {
    expect(sameDraft([ada], [{ ...ada }])).toBe(true);
    expect(sameDraft([ada], [ada, bea])).toBe(false);
    expect(sameDraft("a", "a")).toBe(true);
  });

  it("offers the list's names as the choice, and the demo adds a solicitor then switches to them", () => {
    resetStubAppSettings();
    expect(stubAppSettings(true).settings.find((s) => s.key === "current_solicitor")?.choices).toEqual(["A. Sample"]);
    expect(stubSave({ current_solicitor: "B. Second" }, true)).toMatchObject({ ok: false, status: 422 });
    expect(stubSave({ solicitors: [ada, bea], current_solicitor: "B. Second" }, true)).toEqual({ ok: true });
    const view = stubAppSettings(true);
    expect(view.settings.find((s) => s.key === "current_solicitor")).toMatchObject({ value: "B. Second", choices: ["A. Sample", "B. Second"] });
    expect(stubSave({ solicitors: [ada] }, true)).toMatchObject({ ok: false, status: 422 });
    expect(stubSave({ solicitors: [{ ...ada, email: "bad" }] }, true)).toMatchObject({ ok: false, status: 422 });
    resetStubAppSettings();
  });
});

describe("the operations switches", () => {
  it("hold and release in the stub, refuse a non-administrator and an unknown key", () => {
    resetStubAppSettings();
    const held = () => Object.fromEntries(stubAppSettings(true).status.map((s) => [s.key, s.held]));
    expect(held()).toEqual({ auto_draft_hold: true, email_filing_hold: true });
    expect(stubSetOperation("auto_draft_hold", false, true)).toEqual({ ok: true });
    expect(held()).toEqual({ auto_draft_hold: false, email_filing_hold: true });
    expect(stubSetOperation("auto_draft_hold", false, false)).toMatchObject({ ok: false, status: 403 });
    expect(stubSetOperation("nonsense", true, true)).toMatchObject({ ok: false, status: 404 });
    resetStubAppSettings();
  });
});
