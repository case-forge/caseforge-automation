
import type { AttendanceCaller, AttendanceNoteKind } from "./types";

export const ATTENDANCE_FOLDERS = ["FLA", "CA"] as const;
export type AttendanceFolder = (typeof ATTENDANCE_FOLDERS)[number];

export const OTHER_FOLDER = "__other__";

export const CUSTOM_FOLDER_MAX = 60;

const FLA_WORDS = ["FLA", "NMO", "OO"];
const CA_WORDS = ["CA", "CAO", "PSO", "SIO"];

export function otherFolderKind(typed: string): AttendanceFolder | "custom" | "" {
  const words = typed.toUpperCase().match(/[A-Z]+/g) ?? [];
  const fla = words.some((w) => FLA_WORDS.includes(w));
  const ca = words.some((w) => CA_WORDS.includes(w));
  if (fla && ca) return "";
  const filler = ["AND", "OR", "ATTENDANCE", "NOTES", "NOTE"];
  if (fla && words.every((w) => FLA_WORDS.includes(w) || filler.includes(w))) return "FLA";
  if (ca && words.every((w) => CA_WORDS.includes(w) || filler.includes(w))) return "CA";
  return "custom";
}

export function folderValue(selected: string, otherText: string): string {
  if (selected === "") return "";
  if (selected !== OTHER_FOLDER) return selected;
  const text = otherText.replace(/\s+/g, " ").trim().slice(0, CUSTOM_FOLDER_MAX);
  return text !== "" && otherFolderKind(text) !== "" ? text : "";
}

export function offeredFolders(found: readonly { name: string; code: string }[]): AttendanceFolder[] {
  return ATTENDANCE_FOLDERS.filter((group) => found.some((f) => f.code === group));
}

export function extraFolders(found: readonly { name: string; code: string }[]): string[] {
  return found.filter((f) => f.code === "").map((f) => f.name);
}

export const DOC_KINDS: { value: string; label: string }[] = [
  { value: "application", label: "Application" },
  { value: "witness_statement", label: "Witness statement" },
  { value: "bundle", label: "Bundle" },
  { value: "order", label: "Order" },
  { value: "letter", label: "Letter" },
  { value: "other", label: "Other" },
];

export const DOC_OTHER_MAX = 60;

export function takesParty(kind: AttendanceNoteKind): boolean {
  return kind !== "perusal" && kind !== "preparation";
}

export function docOtherReady(docKind: string, docOther: string): boolean {
  return docKind !== "other" || docOther.trim() !== "";
}

export interface CreateBodyInput {
  matterId: string;
  kind: AttendanceNoteKind;
  caller: AttendanceCaller | "";
  callerOther: string;
  noteText: string;
  minutesSpent: number | null;
  pages: number;
  docKind: string;

  docOther?: string;

  folder: string;
}

export function buildCreateBody(input: CreateBodyInput): Record<string, unknown> {
  const hasPages = !takesParty(input.kind);
  return {
    matter_id: input.matterId,
    ...(hasPages ? {} : { caller: input.caller, caller_other: input.callerOther }),
    note_text: input.noteText,
    kind: input.kind,
    ...(input.minutesSpent !== null ? { time_minutes: input.minutesSpent } : {}),
    ...(hasPages && input.pages ? { pages: input.pages } : {}),
    ...(hasPages && input.docKind ? { doc_kind: input.docKind } : {}),
    ...(hasPages && input.docKind === "other" && input.docOther?.trim() ? { doc_other: input.docOther.replace(/\s+/g, " ").trim().slice(0, DOC_OTHER_MAX) } : {}),
    ...(input.folder ? { attendance_folder: input.folder } : {}),
  };
}

export function partyReady(kind: AttendanceNoteKind, caller: AttendanceCaller | "", callerOther: string): boolean {
  if (!takesParty(kind)) return true;
  return caller !== "" && (caller !== "other" || callerOther.trim() !== "");
}
