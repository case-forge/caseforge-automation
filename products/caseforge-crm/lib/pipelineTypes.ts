
import type { ActorKind } from "./actorKind";
import type { BoardSync } from "./syncMark";
export type PipelineMode = "manual" | "auto";

export type MatterModeSetting = "inherit" | PipelineMode;
export const MATTER_MODE_SETTINGS: MatterModeSetting[] = ["manual", "inherit", "auto"];
export type PipelineStepKey =
  | "record"
  | "folder"
  | "statement"
  | "email"
  | "amend"
  | "ws_sign"
  | "court_pack"
  | "court_email"
  | "court_reply"
  | "client_papers"
  | "serve"
  | "serve_other"
  | "sos_received"
  | "sos_to_court"
  | "bundle"
  | "ccl"
  | "brief"
  | "book_counsel"
  | "mid_letter"
  | "closing_letter";

export type PipelineActor = "you" | "case flow" | "";

export type PipelineStepStatus = "done" | "todo" | "attention" | "blocked" | "unknown" | "not_needed";

export interface PipelineLink {
  label: string;
  url: string;
}

export interface PipelineVariant {
  key: string;
  label: string;
}

export interface PipelineStep {
  key: PipelineStepKey;

  number?: number;
  label: string;
  status: PipelineStepStatus;
  summary: string;
  detail: string[];
  can_run: boolean;
  run_label: string;
  variants: PipelineVariant[];

  outside?: "by_hand" | "filed" | "found" | "";

  actor?: PipelineActor;

  court_suggestions?: CourtSuggestion[];

  links?: PipelineLink[];

  resettable?: boolean;

  auto_tries?: number;
  auto_max?: number;

  checked_utc?: string;

  game?: boolean;

  can_send?: boolean;
  send_label?: string;

  amend?: AmendStepInfo;
}

export type AmendFlagKind = "review" | "editorial" | "asked_again" | "changed_often" | "merged" | "facts_unread";

export interface AmendFlag {
  kind: AmendFlagKind;
  text: string;
}

export interface AmendParagraph {

  id: string;
  para: number | null;
  before: string;
  after: string;
  why: string;
  client_words: string;
  flags: AmendFlag[];

  edited?: boolean;

  model_after?: string;
}

export interface AmendQuestion {
  para: number | null;
  type: "question_to_solicitor" | "asks_advice";
  client_words: string;
}

export interface AmendAiQuestion {
  id: string;
  question: string;
  quote: string;
}

export interface AmendUnplaced {
  type: string;
  client_words: string;
  why: string;
}

export interface AmendDbUpdate {
  field: string;
  current: string;
  proposed: string;
  para: number | null;
  quote: string;
}

export interface AmendRepeat {
  para: number | null;
  client_words: string;
  earlier_round: number;
  in_text_now: boolean;
}

export interface AmendOpenRound {
  round: number;
  status: "prepared" | "saved";
  prepared_by: string;
  prepared_utc: string;
  paragraphs: AmendParagraph[];
  questions: AmendQuestion[];

  ai_questions?: AmendAiQuestion[];
  unplaced: AmendUnplaced[];
  db_updates: AmendDbUpdate[];
  repeats: AmendRepeat[];
  notes: string[];
}

export interface AmendStepInfo {

  rounds: number;

  flagged: boolean;

  can_start: boolean;

  start_blocked: string;

  email_hint: string;
  open: AmendOpenRound | null;
}

export interface CourtSuggestion {
  name: string;

  email: string;
}

export const SERVICE_RECIPIENT_KINDS = ["law firm", "hospital", "school", "other"] as const;

export interface ActivityViewer {
  who: string;
  at: string;
}

export interface PipelineEvent {
  event_id: string;
  step: string;

  status: "ok" | "failed" | "info" | "waiting" | "held" | "outside" | "reset";
  summary: string;
  by: string;

  mode: PipelineMode | "lexcel";
  created_utc: string;

  instance?: string;

  links?: PipelineLink[];

  actor_kind?: ActorKind | "";
}

export interface Pipeline {
  matter_id: string;
  client_name: string;

  mode: PipelineMode;

  mode_by?: string;
  mode_at?: string;

  matter_mode?: MatterModeSetting | "unreadable";

  matter_mode_by?: string;
  matter_mode_at?: string;

  effective_mode?: PipelineMode | "";

  auto_reason?: string;

  locked?: boolean;
  lock_reason?: string;

  sync?: BoardSync | null;
  steps: PipelineStep[];
  events: PipelineEvent[];

  waiting?: { state: string; label: string };
}

export interface MatterModeAnswer {
  matter_id: string;
  setting: MatterModeSetting | "unreadable";
  by: string;
  at: string;

  mode: PipelineMode;
  effective_mode: PipelineMode;
}

export interface PipelineRunResult {
  ok: boolean;
  message: string;
  links?: PipelineLink[];
  pipeline: Pipeline;
}

export const PIPELINE_STEP_KEYS: PipelineStepKey[] = [
  "record",
  "folder",
  "statement",
  "email",
  "amend",
  "ws_sign",
  "court_pack",
  "court_email",
  "court_reply",
  "client_papers",
  "serve",
  "book_counsel",
  "bundle",
  "serve_other",
  "sos_received",
  "sos_to_court",
  "ccl",
  "brief",
  "mid_letter",
  "closing_letter",
];

export const PIPELINE_STEP_NUMBERS = Object.fromEntries(PIPELINE_STEP_KEYS.map((key, index) => [key, index])) as Record<PipelineStepKey, number>;

export function stepRef(key: PipelineStepKey): string {
  return `step ${PIPELINE_STEP_NUMBERS[key]}`;
}

export function stepRefCap(key: PipelineStepKey): string {
  const text = stepRef(key);
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const PIPELINE_STEP_LABELS: Record<PipelineStepKey, string> = {
  record: "Client logged to database",
  folder: "Client folders generated",
  statement: "Witness statement drafted",
  email: "Witness statement sent to client",
  amend: "Client's changes to the statement, amended for approval",
  ws_sign: "Approved statement sent for signature, drafted",
  court_pack: "Court pack ready: Notice of Acting, draft orders, forms",
  court_email: "Application emailed to the court (drafted once)",
  court_reply: "Court's reply filed",
  client_papers: "Court's papers and hearing date to the client, drafted",
  serve: "Papers to referrer for service, drafted",
  serve_other: "Service on someone else (optional), drafted",
  sos_received: "Statement of service filed",
  sos_to_court: "Statement of service to the court, drafted",
  bundle: "Hearing bundle built (per hearing)",
  ccl: "Client care letter drafted, ready to send",
  brief: "Brief to Counsel drafted (per hearing)",
  book_counsel: "Counsel requested from chambers (per hearing)",
  mid_letter: "Court outcome letter drafted (per hearing)",
  closing_letter: "Closing client care letter drafted",
};

export const EMAIL_VARIANTS: PipelineVariant[] = [
  { key: "loa_signing", label: "Draft email" },
];

export const MODE_WARNING =
  "Auto: for clients opened after Auto was switched on, the steps run by themselves strictly in order, each only once the one before is done, and never twice. Drafts and envelopes are made, and the client's statement email (the first one, and an amended statement for signature) is armed to leave 15 minutes later unless its draft is changed first; every other email stays a draft. A step that needs a person stops the run until you act. Manual: nothing runs until you press a button, and nothing is armed or sent by itself.";
