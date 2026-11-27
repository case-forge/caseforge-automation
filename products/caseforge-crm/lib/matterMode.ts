
import type { MatterModeSetting, PipelineMode } from "./pipelineTypes";

type Picture = { mode: PipelineMode; matter_mode?: string; effective_mode?: string; auto_reason?: string };

function word(mode: PipelineMode): string {
  return mode === "auto" ? "Auto" : "Manual";
}

export function matterSetting(picture: Picture): MatterModeSetting | "unreadable" {
  const own = picture.matter_mode;
  if (own === undefined || own === "" || own === "inherit") return "inherit";
  return own === "auto" || own === "manual" ? own : "unreadable";
}

export function effectiveMode(picture: Picture): PipelineMode {
  if (picture.effective_mode === "auto" || picture.effective_mode === "manual") return picture.effective_mode;
  const own = matterSetting(picture);
  if (own === "unreadable") return "manual";
  return own === "inherit" ? picture.mode : own;
}

export function autoStalledReason(picture: Picture): string {
  return effectiveMode(picture) === "auto" ? (picture.auto_reason ?? "").trim() : "";
}

export function matterChoiceLabel(choice: MatterModeSetting, firmMode: PipelineMode): string {
  if (choice === "inherit") return `Default (${word(firmMode)})`;
  return choice === "auto" ? "Auto for this client" : "Manual for this client";
}

export function matterModeSentence(picture: Picture): string {
  const own = matterSetting(picture);
  const firm = word(picture.mode);
  if (own === "unreadable") {
    return "This client's own setting could not be read, so this client is treated as Manual: nothing runs until you press a button.";
  }
  if (own === "inherit") {
    return picture.mode === "auto"
      ? "This client follows the firm, which is on Auto. Auto acts only on clients opened after it was switched on; an older client waits for a person."
      : "This client follows the firm, which is on Manual: nothing runs until you press a button.";
  }
  if (own === "auto") {
    const rest = picture.mode === "auto" ? "The firm is on Auto as well." : `The rest of the firm stays on ${firm}.`;
    return `Auto is on for this client, whenever the client was opened: the steps run by themselves in order, and the client's statement email is armed to leave 15 minutes later. ${rest}`;
  }
  const rest = picture.mode === "auto" ? "The firm is on Auto, and this client is left out of it." : "The firm is on Manual as well.";
  return `Manual is on for this client: nothing runs until you press a button. ${rest}`;
}

function stamp(by: string | undefined, at: string | undefined): string {
  const who = (by ?? "").trim();
  if (!who) return "";
  const when = new Date(at ?? "");
  const text = Number.isNaN(when.getTime())
    ? ""
    : when.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });
  return `Set by ${who}${text ? `, ${text}` : ""}.`;
}

export function matterModeSetBy(picture: Picture & { matter_mode_by?: string; matter_mode_at?: string }): string {
  const own = matterSetting(picture);
  if (own === "inherit" || own === "unreadable") return "";
  return stamp(picture.matter_mode_by, picture.matter_mode_at);
}

export function firmModeSetBy(picture: { mode_by?: string; mode_at?: string }): string {
  return stamp(picture.mode_by, picture.mode_at);
}

export function matterModeBlockedReason(opts: { locked: string; busy: boolean }): string {
  if (opts.locked) return opts.locked;
  if (opts.busy) return "Saving...";
  return "";
}
