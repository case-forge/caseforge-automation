import { describe, expect, it } from "vitest";
import { effectiveMode, matterChoiceLabel, matterModeBlockedReason, matterModeSentence, matterModeSetBy, matterSetting } from "./matterMode";
import { MATTER_MODE_SETTINGS } from "./pipelineTypes";
import { stubPipeline, stubSetMatterMode, stubSetMode } from "./stubPipeline";

describe("a client's own setting", () => {
  it("follows the firm when the hub sends none (an older hub) or says inherit", () => {
    expect(matterSetting({ mode: "manual" })).toBe("inherit");
    expect(matterSetting({ mode: "auto", matter_mode: "" })).toBe("inherit");
    expect(matterSetting({ mode: "auto", matter_mode: "inherit" })).toBe("inherit");
  });
  it("is auto or manual when the hub says so, and unreadable for anything else", () => {
    expect(matterSetting({ mode: "manual", matter_mode: "auto" })).toBe("auto");
    expect(matterSetting({ mode: "auto", matter_mode: "manual" })).toBe("manual");
    expect(matterSetting({ mode: "auto", matter_mode: "unreadable" })).toBe("unreadable");
    expect(matterSetting({ mode: "auto", matter_mode: "AUTO!" })).toBe("unreadable");
  });
});

describe("the mode a client is in", () => {
  it("is the hub's own answer when it gives one", () => {
    expect(effectiveMode({ mode: "manual", matter_mode: "inherit", effective_mode: "auto" })).toBe("auto");
    expect(effectiveMode({ mode: "auto", matter_mode: "auto", effective_mode: "manual" })).toBe("manual");
  });
  it("is the client's setting, else the firm-wide mode, when the hub gives none", () => {
    expect(effectiveMode({ mode: "manual" })).toBe("manual");
    expect(effectiveMode({ mode: "auto" })).toBe("auto");
    expect(effectiveMode({ mode: "manual", matter_mode: "auto" })).toBe("auto");
    expect(effectiveMode({ mode: "auto", matter_mode: "manual", effective_mode: "" })).toBe("manual");
  });
  it("is Manual when the setting could not be read, whatever the firm is on", () => {
    expect(effectiveMode({ mode: "auto", matter_mode: "unreadable" })).toBe("manual");
    expect(effectiveMode({ mode: "auto", matter_mode: "something else" })).toBe("manual");
  });
});

describe("the words", () => {
  it("names the three choices, left to right, the middle one with the firm-wide mode it follows", () => {
    expect(MATTER_MODE_SETTINGS).toEqual(["manual", "inherit", "auto"]);
    expect(matterChoiceLabel("inherit", "manual")).toBe("Default (Manual)");
    expect(matterChoiceLabel("inherit", "auto")).toBe("Default (Auto)");
    expect(matterChoiceLabel("auto", "manual")).toBe("Auto for this client");
    expect(matterChoiceLabel("manual", "auto")).toBe("Manual for this client");
  });
  it("says which is in effect and where the rest of the firm stands", () => {
    expect(matterModeSentence({ mode: "manual" })).toMatch(/follows the firm, which is on Manual/);
    expect(matterModeSentence({ mode: "auto", matter_mode: "inherit" })).toMatch(/follows the firm, which is on Auto/);
    expect(matterModeSentence({ mode: "manual", matter_mode: "auto" })).toMatch(/^Auto is on for this client.*armed to leave 15 minutes later.*rest of the firm stays on Manual/);
    expect(matterModeSentence({ mode: "auto", matter_mode: "manual" })).toMatch(/^Manual is on for this client.*firm is on Auto, and this client is left out/);
    expect(matterModeSentence({ mode: "auto", matter_mode: "unreadable" })).toMatch(/could not be read.*treated as Manual/);
  });
  it("says who chose the setting and when, in London time, and nothing while the client follows the firm", () => {
    expect(matterModeSetBy({ mode: "manual", matter_mode: "auto", matter_mode_by: "Morgan", matter_mode_at: "2026-09-25T14:30:00Z" })).toMatch(/^Set by Morgan, 25 Sept?, 15:30\.$/);
    expect(matterModeSetBy({ mode: "manual", matter_mode: "auto", matter_mode_by: "Morgan", matter_mode_at: "nonsense" })).toBe("Set by Morgan.");
    expect(matterModeSetBy({ mode: "manual", matter_mode: "inherit", matter_mode_by: "Morgan", matter_mode_at: "2026-09-25T14:30:00Z" })).toBe("");
    expect(matterModeSetBy({ mode: "manual", matter_mode: "auto" })).toBe("");
  });
  it("says why the setting cannot be changed, the lock first", () => {
    expect(matterModeBlockedReason({ locked: "Locked", busy: true })).toBe("Locked");
    expect(matterModeBlockedReason({ locked: "", busy: true })).toMatch(/Saving/);
    expect(matterModeBlockedReason({ locked: "", busy: false })).toBe("");
  });
});

describe("stub mode", () => {
  it("keeps each client's own setting apart from the firm-wide mode and from other clients", () => {
    expect(stubPipeline("mm-1")).toMatchObject({ mode: "manual", matter_mode: "inherit", effective_mode: "manual" });
    const set = stubSetMatterMode("mm-1", "auto", " Morgan ");
    expect(set).toMatchObject({ matter_id: "mm-1", setting: "auto", by: "Morgan", mode: "manual", effective_mode: "auto" });
    const one = stubPipeline("mm-1");
    expect(one).toMatchObject({ mode: "manual", matter_mode: "auto", matter_mode_by: "Morgan", effective_mode: "auto" });
    expect(one.events.at(-1)).toMatchObject({ step: "mode", status: "info", by: "Morgan", summary: "This client is on Auto, set by Morgan." });
    expect(stubPipeline("mm-2")).toMatchObject({ matter_mode: "inherit", effective_mode: "manual" });

    stubSetMode("auto");
    stubSetMatterMode("mm-1", "manual", "Morgan");
    expect(stubPipeline("mm-1")).toMatchObject({ mode: "auto", matter_mode: "manual", effective_mode: "manual" });
    expect(stubPipeline("mm-2")).toMatchObject({ mode: "auto", effective_mode: "auto" });
    stubSetMatterMode("mm-1", "inherit", "Morgan");
    expect(stubPipeline("mm-1")).toMatchObject({ matter_mode: "inherit", effective_mode: "auto" });
    stubSetMode("manual");
  });
  it("refuses a choice it does not know and a missing name", () => {
    expect(stubSetMatterMode("mm-3", "sometimes", "Morgan")).toHaveProperty("error");
    expect(stubSetMatterMode("mm-3", "auto", "  ")).toHaveProperty("error");
    expect(stubPipeline("mm-3").matter_mode).toBe("inherit");
  });
});

import { autoStalledReason } from "./matterMode";

describe("autoStalledReason", () => {
  it("is the hub's reason only for a client that is on Auto, so the page can say it is in effect Manual", () => {
    expect(autoStalledReason({ mode: "auto", effective_mode: "auto", auto_reason: " the sync scan flags something " })).toBe("the sync scan flags something");
    expect(autoStalledReason({ mode: "auto", effective_mode: "auto", auto_reason: "" })).toBe("");
    expect(autoStalledReason({ mode: "auto", effective_mode: "manual", auto_reason: "stale text" })).toBe("");
    expect(autoStalledReason({ mode: "manual" })).toBe("");
  });
});
