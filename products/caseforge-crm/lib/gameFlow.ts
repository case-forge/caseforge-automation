
import { PIPELINE_STEP_KEYS, PIPELINE_STEP_LABELS, PIPELINE_STEP_NUMBERS, stepRef } from "./pipelineTypes";
import type { MatterModeSetting, Pipeline, PipelineEvent, PipelineMode, PipelineStep, PipelineStepKey, PipelineStepStatus } from "./pipelineTypes";

export interface DemoCard {
  id: string;
  name: string;
  column: string;
  waiting: boolean;
  assignedTo: number | null;
  assignedName: string | null;
  closedAs: string | null;
  active: boolean;

  step: string | null;

  draft: { type: string; subject: string; to: string } | null;
  round: number;
  rounds: number;

  revision: number;
  matterId?: string;
}

export interface DemoEvent {
  at: string;
  step: string;
  kind: string;
  label: string;
}

export const GAME_FIRST_MATTER_ID = 9100;

export function isGameClientId(matterId: string): boolean {
  return /^\d+$/.test(matterId) && Number(matterId) >= GAME_FIRST_MATTER_ID;
}

export const ONCE_STEPS = [
  "assign-case",
  "create-folder",
  "print-intro",
  "extract-zip",
  "file-laa",
  "client-email",
  "save-client-docs",
  "print-client-response",
  "court-email",
  "save-court-docs",
  "print-court-response",
  "order-client",
  "process-server-request",
  "process-server-response",
  "process-server-invoice",
  "save-process-server-invoice",
  "print-process-server-invoice",
  "counsel-request",
  "print-counsel-offer",
];

export const EACH_STEPS = [
  "brief-counsel",
  "court-bundle",
  "build-bundle",
  "save-counsel-hearing-docs",
  "save-post-hearing-order",
  "counsel-fee-note",
  "save-counsel-fee-note",
  "print-counsel-fee-note",
  "post-order-client",
  "post-process-server",
  "post-process-server-response",
  "post-process-server-invoice",
  "save-post-process-server-invoice",
  "print-post-process-server-invoice",
  "advance-hearing",
];

export function stepPosition(step: string): number {
  const once = ONCE_STEPS.indexOf(step);
  if (once >= 0) return once;
  const each = EACH_STEPS.indexOf(step);
  return each >= 0 ? ONCE_STEPS.length + each : -1;
}

interface HubMap {

  keys: string[];

  phase?: "make" | "send";

  perHearing?: boolean;

  notNeeded?: string;

  atOnboarding?: boolean;
}

export const HUB_MAP: Record<PipelineStepKey, HubMap> = {
  record: { keys: [], atOnboarding: true },
  folder: { keys: ["create-folder", "print-intro", "extract-zip", "file-laa"] },
  statement: { keys: ["client-email"], phase: "make" },
  amend: { keys: [], notNeeded: `Not needed: in the demo, changes to the statement are drafted at ${stepRef("email")}.` },
  ws_sign: { keys: [], notNeeded: `Not needed: in the demo, the client signs the statement through the email at ${stepRef("email")}.` },
  email: { keys: ["client-email", "save-client-docs", "print-client-response"], phase: "send" },
  court_pack: { keys: ["court-email"], phase: "make" },
  court_email: { keys: ["court-email"], phase: "send" },
  court_reply: { keys: ["save-court-docs", "print-court-response"] },
  client_papers: { keys: ["order-client"] },
  book_counsel: { keys: ["counsel-request", "print-counsel-offer"] },
  bundle: { keys: ["court-bundle", "build-bundle"], perHearing: true },
  serve: { keys: ["process-server-request"] },
  serve_other: { keys: [], notNeeded: "Not needed: nobody else is to be served in this demo." },
  sos_received: {
    keys: [
      "process-server-response",
      "process-server-invoice",
      "save-process-server-invoice",
      "print-process-server-invoice",
      "post-process-server",
      "post-process-server-response",
      "post-process-server-invoice",
      "save-post-process-server-invoice",
      "print-post-process-server-invoice",
    ],
    perHearing: true,
  },
  sos_to_court: { keys: [], notNeeded: "Not needed: the demo sends no statement of service to the court." },
  ccl: { keys: [], notNeeded: "Not needed: the demo makes no client care letter." },
  brief: { keys: ["brief-counsel"], perHearing: true },
  mid_letter: {
    keys: ["save-counsel-hearing-docs", "save-post-hearing-order", "counsel-fee-note", "save-counsel-fee-note", "print-counsel-fee-note", "post-order-client"],
    perHearing: true,
  },
  closing_letter: { keys: ["advance-hearing"] },
};

export function hubStepFor(gameStep: string): PipelineStepKey | "" {

  const shared: Record<string, PipelineStepKey> = { "client-email": "email", "court-email": "court_email", "advance-hearing": "closing_letter" };
  if (shared[gameStep]) return shared[gameStep];
  for (const key of PIPELINE_STEP_KEYS) {
    if (HUB_MAP[key].keys.includes(gameStep)) return key;
  }
  return gameStep === "assign-case" ? "record" : "";
}

const RUN_LABELS: Record<PipelineStepKey, string> = {
  record: "Check record",
  folder: "Create the folders, file the referral and unpack the zip",
  statement: "Make statement and draft the email",
  amend: "Prepare the amended statement",
  ws_sign: "Draft email for signature",
  email: "Run the next job",
  court_pack: "Make court pack and draft the email",
  court_email: "Run the next job",
  court_reply: "File court's reply",
  client_papers: "Draft email to the client",
  serve: "Draft email to referrer",
  serve_other: "Draft service email",
  sos_received: "File statement of service",
  sos_to_court: "Draft email to court",
  bundle: "Build bundle",
  ccl: "Make letter",
  brief: "Draft brief",
  book_counsel: "Draft request for counsel",
  mid_letter: "File order and draft the letter",
  closing_letter: "Finish the case",
};

const DONE_DETAIL: Record<PipelineStepKey, string[]> = {
  record: ["The client was logged when the case was made."],
  folder: [
    "The client's folder and its standard subfolders are made.",
    "The referral email is filed as a PDF in Preliminary-Docs.",
    "The zip is unpacked in Preliminary-Docs.",
    "The means evidence the referral names is filed in LAA-Evidence.",
  ],
  statement: ["The Letter of Authority and the witness statement are made in the client's folders."],
  amend: [],
  ws_sign: [],
  email: ["The email went to the client and the signed documents came back and are filed."],
  court_pack: ["The Notice of Acting, the draft orders and the forms are made and attached."],
  court_email: ["The application email went to the court and is filed."],
  court_reply: ["The court's reply and its documents are filed."],
  client_papers: ["The court's papers and the hearing date went to the client."],
  serve: ["The papers went to referrer for personal service."],
  serve_other: [],
  sos_received: ["The statement of service and the process server's invoice are filed."],
  sos_to_court: [],
  bundle: ["The hearing bundle is built in the hearing folder."],
  ccl: [],
  brief: ["The brief to counsel is drafted and filed."],
  book_counsel: ["Counsel was asked, and the offer is filed."],
  mid_letter: ["Counsel's papers, the sealed order and the fee note are filed, and the outcome went to the client."],
  closing_letter: ["The final hearing's order is on file and the case is finished."],
};

const TODO_SUMMARY: Record<PipelineStepKey, string> = {
  record: "Done when the client is made.",
  folder: "Case flow makes the client's folder with its standard subfolders, files the referral email and the zip, unpacks the zip, then files the evidence the referral email describes.",
  statement: "Case flow makes the Letter of Authority and the witness statement and drafts the email to the client with both attached.",
  amend: "",
  ws_sign: "",
  email: "Case flow sends the email to the client automatically, in Auto or Manual. The client then signs, or asks for changes to the statement.",
  court_pack: "Case flow makes the Notice of Acting and the draft order for each order type, and drafts the application email to the court.",
  court_email: "The application email to the court waits for you to send it.",
  court_reply: "Case flow files the court's reply and its documents.",
  client_papers: "Case flow drafts the email sending the order and the notice of hearing to the client. It waits for you to send it.",
  serve: "Case flow drafts the email sending the court papers to the process server. It waits for you to send it.",
  serve_other: "",
  sos_received: "Case flow files the statement of service and the invoice.",
  sos_to_court: "",
  bundle: "Case flow drafts the bundle request to the court and builds the hearing bundle.",
  ccl: "",
  brief: "Case flow drafts the brief to counsel. It waits for you to send it.",
  book_counsel: "Case flow drafts the request for counsel's availability. It waits for you to send it.",
  mid_letter: "Case flow files counsel's papers, the sealed order and the fee note, and drafts the outcome email to the client.",
  closing_letter: "Case flow moves to the next hearing, or finishes the case after the final order.",
};

export interface GameFlowInput {
  card: DemoCard;
  events: DemoEvent[];

  mode: PipelineMode;
  setting: MatterModeSetting;
  setBy?: string;
  setAt?: string;
}

export const GAME_NOT_ASSIGNED = "Assign the client to a caseworker in the New clients tray. Case flow starts then.";
export const GAME_NOT_OPEN = "Open the demo windows (the DEMO button) to run this client's Case Flow.";

export const AUTO_SEND_DRAFT_KINDS: readonly string[] = ["client", "docusign", "revision"];

export function draftAutoSends(draft: { type: string } | null): boolean {
  return Boolean(draft) && AUTO_SEND_DRAFT_KINDS.includes(String(draft!.type).replace(/-\d+$/, ""));
}

export function isRevisionDraft(card: DemoCard): boolean {
  return Boolean(card.draft && /^revision/.test(card.draft.type));
}

export function draftMade(card: DemoCard, events: DemoEvent[]): boolean {
  if (card.draft) return true;
  return events.some((e) => e.step === card.step && e.kind === "auto" && /drafted|nothing has been sent/i.test(e.label));
}

function hearingNote(card: DemoCard): string {
  return card.rounds > 1 ? ` (hearing ${Math.min(card.round, card.rounds)} of ${card.rounds})` : "";
}

export function hubStepState(key: PipelineStepKey, card: DemoCard, events: DemoEvent[]): { status: PipelineStepStatus; owner: boolean } {
  const map = HUB_MAP[key];
  if (map.notNeeded) return { status: "not_needed", owner: false };
  if (map.atOnboarding) return { status: "done", owner: false };
  if (card.step === null) return { status: "done", owner: false };
  const cur = stepPosition(card.step);
  if (cur < 0) return { status: "blocked", owner: false };

  if (key === "closing_letter") {

    const here = cur === stepPosition("advance-hearing");
    return { status: here ? "todo" : "blocked", owner: here };
  }

  const clusters = [map.keys.filter((k) => ONCE_STEPS.includes(k)), map.keys.filter((k) => EACH_STEPS.includes(k))].filter((c) => c.length);
  const positionsOf = (keys: string[]) => keys.map(stepPosition).filter((p) => p >= 0);
  const cluster = clusters.find((c) => cur <= Math.max(...positionsOf(c)));
  if (!cluster) return { status: "done", owner: false };
  const first = Math.min(...positionsOf(cluster));
  if (cur < first) return { status: "blocked", owner: false };

  if (map.phase) {
    const sharedKey = map.keys[0];
    if (card.step === sharedKey) {
      const made = draftMade(card, events);
      if (map.phase === "make") return { status: made ? "done" : "todo", owner: !made };
      return { status: made ? (card.draft ? "attention" : "todo") : "blocked", owner: made };
    }
    if (map.phase === "make") return { status: "done", owner: false };
  }
  if (card.draft) return { status: "attention", owner: true };
  return { status: "todo", owner: true };
}

function summaryFor(key: PipelineStepKey, status: PipelineStepStatus, card: DemoCard, firstPending: number | null): string {
  const map = HUB_MAP[key];
  if (map.notNeeded) return map.notNeeded;
  if (status === "done") return "Done.";
  if (status === "blocked") return firstPending !== null ? `Waiting for step ${firstPending}.` : "Waiting for the step before.";
  if (card.draft && (status === "attention" || (map.phase === "send" && card.step === map.keys[0]))) {
    if (isRevisionDraft(card)) return `The client asked for changes to the statement. The revised statement is drafted: "${card.draft.subject}". Sent automatically, in Auto or Manual.`;
    if (draftAutoSends(card.draft)) return `Drafted: "${card.draft.subject}" to ${card.draft.to}. Sent automatically, in Auto or Manual.`;
    return `Drafted: "${card.draft.subject}" to ${card.draft.to}. Waiting for you to send it: nothing is sent until you press Send.`;
  }
  if (key === "email" && card.revision > 0) {
    return `The client has asked for changes ${card.revision === 1 ? "once" : `${card.revision} times`}. Case flow revises the statement, drafts it again and sends it automatically.`;
  }
  return TODO_SUMMARY[key];
}

export function gamePipeline(input: GameFlowInput): Pipeline {
  const { card, events, mode, setting } = input;
  const effective: PipelineMode = setting === "inherit" ? mode : setting;
  const closed = card.closedAs ? `This case is closed (${card.closedAs.replace("-", " ")}).` : "";
  const unassigned = !card.assignedTo;
  const lockReason = closed || (unassigned ? GAME_NOT_ASSIGNED : "");

  const states = PIPELINE_STEP_KEYS.map((key) => ({ key, ...hubStepState(key, card, events) }));

  const firstPendingNumber = (() => {
    const pending = states.find((s) => s.status !== "done" && s.status !== "not_needed");
    return pending ? PIPELINE_STEP_NUMBERS[pending.key] : null;
  })();

  const steps: PipelineStep[] = states.map((s) => {
    const map = HUB_MAP[s.key];
    const label = PIPELINE_STEP_LABELS[s.key] + (map.perHearing && s.status !== "done" ? hearingNote(card) : "");
    const waitingForSend = Boolean(card.draft) && s.status === "attention";
    const isNext = s.owner && !waitingForSend && s.status !== "done" && s.status !== "blocked" && s.status !== "not_needed";
    const canRun = isNext && !lockReason;
    const canSend = waitingForSend && !lockReason;
    const revisionLoop = s.key === "email" && (card.revision > 0 || isRevisionDraft(card));
    return {
      key: s.key,
      number: PIPELINE_STEP_NUMBERS[s.key],
      label,
      status: s.status,
      summary: summaryFor(s.key, s.status, card, s.status === "blocked" ? firstPendingNumber : null),
      detail: s.status === "done" ? DONE_DETAIL[s.key] : revisionLoop ? [`Statement changes asked for so far: ${card.revision}.`, "Case flow stops after the third draft."] : [],
      can_run: canRun,
      run_label: RUN_LABELS[s.key],
      variants: [],
      outside: "",
      actor: waitingForSend ? "you" : s.status === "done" || s.status === "not_needed" || s.status === "blocked" ? "" : effective === "auto" ? "case flow" : "you",
      links: [],
      resettable: false,
      game: true,
      can_send: canSend,
      send_label: canSend ? (draftAutoSends(card.draft) ? "Send now (sent automatically)" : "Send email") : undefined,
    };
  });

  return {
    matter_id: card.matterId ?? "",
    client_name: card.name,
    mode,
    matter_mode: setting,
    matter_mode_by: input.setBy ?? "",
    matter_mode_at: input.setAt ?? "",
    effective_mode: effective,
    ...(lockReason ? { locked: true, lock_reason: lockReason } : {}),
    steps,
    events: gameEvents(card, events, effective),
  };
}

export function lockedGamePipeline(matterId: string, clientName: string, reason: string, mode: PipelineMode, setting: MatterModeSetting): Pipeline {
  return {
    matter_id: matterId,
    client_name: clientName,
    mode,
    matter_mode: setting,
    matter_mode_by: "",
    matter_mode_at: "",
    effective_mode: setting === "inherit" ? mode : setting,
    locked: true,
    lock_reason: reason,
    steps: PIPELINE_STEP_KEYS.map((key) => ({
      key,
      number: PIPELINE_STEP_NUMBERS[key],
      label: PIPELINE_STEP_LABELS[key],
      status: "blocked" as const,
      summary: reason,
      detail: [],
      can_run: false,
      run_label: RUN_LABELS[key],
      variants: [],
      outside: "",
      actor: "" as const,
      links: [],
      resettable: false,
      game: true,
    })),
    events: [],
  };
}

export function gameEvents(card: DemoCard, events: DemoEvent[], effective: PipelineMode): PipelineEvent[] {
  return events.map((e, i) => {
    const human = e.kind === "human";
    const status: PipelineEvent["status"] = e.kind === "auto" ? "ok" : human ? "waiting" : e.kind === "stuck" ? "failed" : "info";
    return {
      event_id: `game-${card.id}-${i}`,
      step: hubStepFor(e.step) || e.step,
      status,
      summary: e.label,
      by: human ? card.assignedName ?? "A caseworker" : "Case flow",
      mode: effective,
      created_utc: e.at,
    };
  });
}
