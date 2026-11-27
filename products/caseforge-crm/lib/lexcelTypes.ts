
import type { PipelineLink, PipelineVariant } from "./pipelineTypes";

export type LexcelKind = "opening" | "mid" | "closing";
export const LEXCEL_KINDS: LexcelKind[] = ["opening", "mid", "closing"];

export interface LexcelLetter {
  kind: LexcelKind;
  label: string;
  button: string;

  made: boolean;
  made_utc: string;
  made_by: string;

  made_via: string;
  times: number;
  summary: string;
  links: PipelineLink[];

  can_make?: boolean;

  note?: string;

  checklist?: LexcelCheck[];

  file_present?: boolean;

  hearings?: { key: string; date: string; label: string }[];

  auto?: LexcelAuto | null;

  locked?: string;
}

export interface LexcelCheck {
  key: string;
  label: string;
  ok: boolean;

  note: string;
}

export interface Lexcel {
  matter_id: string;
  letters: LexcelLetter[];
}

export interface LexcelMakeResult {
  ok: boolean;
  message: string;

  offers: PipelineVariant[];
  links: PipelineLink[];
  lexcel: Lexcel;
}

const LONDON_LONG = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/London" });
const LONDON_SHORT = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Europe/London" });

export function madeLine(letter: Pick<LexcelLetter, "made" | "made_utc" | "made_by" | "made_via" | "times">): string {
  if (!letter.made) return "Not recorded as made.";
  const d = new Date(letter.made_utc);
  const day = Number.isNaN(d.getTime()) ? "an unknown date" : LONDON_LONG.format(d);
  const who = letter.made_by.trim() ? ` by ${letter.made_by.trim()}` : "";
  const where = letter.made_via === "Lexcel" ? ", with a Lexcel button" : letter.made_via ? `, by ${letter.made_via}` : "";
  const more = letter.times > 1 ? ` (${letter.times} made; this is the newest)` : "";
  return `Made on ${day}${who}${where}${more}.`;
}

export function closingLetterDate(lexcel: Pick<Lexcel, "letters"> | null | undefined): string {
  const letter = lexcel?.letters.find((l) => l.kind === "closing");
  if (!letter?.made) return "";
  const d = new Date(letter.made_utc);
  return Number.isNaN(d.getTime()) ? "Made, date not recorded" : LONDON_LONG.format(d);
}

export function canGenerate(_letter?: Pick<LexcelLetter, "made" | "can_make">): boolean {
  return true;
}

export function generateLabel(letter: Pick<LexcelLetter, "made" | "file_present"> | undefined): "Generate" | "Regenerate" {
  return letter && (letter.made || letter.file_present === true) ? "Regenerate" : "Generate";
}

export function checklistGaps(letter: Pick<LexcelLetter, "checklist"> | undefined): LexcelCheck[] {
  return (letter?.checklist ?? []).filter((c) => !c.ok);
}

export type LexcelRowState = "received" | "missing" | "unknown" | "loading";

export function lexcelRow(
  letter: LexcelLetter | undefined,
  failed: boolean,
): { state: LexcelRowState; text: string; url: string; title: string; more: PipelineLink[]; canGenerate: boolean; note: string } {
  const none = { url: "", title: "", more: [], canGenerate: false, note: "" };
  if (failed) return { state: "unknown", text: "Couldn't check", ...none };
  if (!letter) return { state: "loading", text: "Checking…", ...none };
  const note = (letter.note ?? "").trim();

  if (!letter.made) return { state: "missing", text: "", ...none, canGenerate: true, note };
  const links = (letter.links ?? []).filter((l) => typeof l?.url === "string" && l.url.startsWith("https://"));
  const d = new Date(letter.made_utc);
  const day = Number.isNaN(d.getTime()) ? "Made" : LONDON_SHORT.format(d);
  return {
    state: "received",
    text: letter.times > 1 ? `${day} (${letter.times} made)` : day,
    url: links[0]?.url ?? "",
    title: madeLine(letter),
    more: links.slice(1),
    canGenerate: canGenerate(letter),
    note,
  };
}

export function generateBlockedReason(opts: { canGenerate: boolean; running: boolean; made: boolean }): string {
  if (opts.running) return "A letter is being made.";
  if (!opts.canGenerate) return "Not available just now.";
  return "";
}

export const REGENERATE_QUESTION =
  "Make a new opening client care letter for this client? It is saved as a new draft beside the old one, with its own Documenso envelope and email draft. Nothing is sent and nothing is deleted.";

export type RegenerateState = "available" | "confirming" | "running" | "done" | "refused";

export function openingRegenerate(
  letter: Pick<LexcelLetter, "kind" | "made" | "file_present" | "locked"> | undefined,
  opts: { confirming: boolean; running: boolean; outcome?: { ok: boolean } | null },
): { state: RegenerateState; disabled: boolean; title: string } | null {
  if (!letter || letter.kind !== "opening" || generateLabel(letter) !== "Regenerate") return null;
  const locked = (letter.locked ?? "").trim();
  if (locked) return { state: "refused", disabled: true, title: locked };
  if (opts.running) return { state: "running", disabled: true, title: "A letter is being made." };
  if (opts.confirming) return { state: "confirming", disabled: true, title: "Answer the question below first." };
  const title = "Make a new letter beside the old one, as a draft. Nothing is sent and nothing is deleted.";
  return { state: opts.outcome?.ok ? "done" : "available", disabled: false, title };
}

export interface LexcelAuto {
  state: "counting" | "due" | "waiting";
  days_left?: number;
  due_on?: string;
  why?: string;
  held?: boolean;
  held_why?: string;
  cancelled?: boolean;
  cancelled_by?: string;
}

export function autoLine(letter: Pick<LexcelLetter, "made" | "auto"> | undefined): string {
  const auto = letter?.auto;
  if (!auto || letter?.made) return "";
  if (auto.cancelled) return `Automatic letter cancelled${auto.cancelled_by ? ` by ${auto.cancelled_by}` : ""}. Make now still makes it.`;
  if (auto.state === "waiting") return "Generates by itself 3 working days after the application goes to the court.";
  const when =
    auto.state === "due" ? "Generating now: on Case flow's next pass" : `Generating in ${auto.days_left ?? 1} day${(auto.days_left ?? 1) === 1 ? "" : "s"}`;
  const what = "the letter, its Documenso envelope and the email draft. Nothing is sent.";
  if (auto.held) return `${when}, but paused: automatic drafting is on hold. Make now still makes it.`;
  return `${when}: ${what}`;
}
