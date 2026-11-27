
import { canConfirmCourt, canMarkDone, canResetStep, confirmCourtCheck, markDoneQuestion, recipientKind, resetStepQuestion, serviceRecipientCheck } from "./pipelineDisplay";
import { SERVICE_RECIPIENT_KINDS, stepRefCap } from "./pipelineTypes";
import type { CourtSuggestion } from "./pipelineTypes";

export type StepFormKind = "mark-done" | "confirm-court" | "add-recipient" | "require-service" | "reset";

export const FIELD_LIMITS = { note: 300, court: 200, email: 200, recipient: 120 } as const;

export interface StepFormValues {
  note: string;
  court: string;
  email: string;
  kind: string;
  recipient: string;
}
export type StepFormField = keyof StepFormValues;
export type StepFormErrors = Partial<Record<StepFormField, string>>;

export type StepFormRequest =
  | { kind: "mark-done"; note?: string }
  | { kind: "confirm-court"; court: string; email?: string }
  | { kind: "add-recipient"; recipientKind: string; name: string; email: string }
  | { kind: "require-service" }
  | { kind: "reset" };

interface FormStep {
  key: string;
  number?: number;
  label: string;
  status: string;
  summary?: string;
  resettable?: boolean;
  court_suggestions?: CourtSuggestion[];
}

export function blankStepForm(kind: StepFormKind, step: { court_suggestions?: CourtSuggestion[] }): StepFormValues {
  return {
    note: "",
    court: kind === "confirm-court" ? (step.court_suggestions?.[0]?.name ?? "") : "",
    email: "",
    kind: SERVICE_RECIPIENT_KINDS[0],
    recipient: "",
  };
}

export function stepFormOffered(step: FormStep, kind: StepFormKind): boolean {
  if (kind === "mark-done") return canMarkDone(step);
  if (kind === "confirm-court") return canConfirmCourt(step);
  if (kind === "add-recipient") return step.key === "serve_other";
  if (kind === "require-service") return step.key === "serve" && step.status === "not_needed";
  return canResetStep(step);
}

export function shownStepForm(open: Record<string, StepFormKind>, step: FormStep, locked: string): StepFormKind | undefined {
  const kind = open[step.key];
  return kind && !locked && stepFormOffered(step, kind) ? kind : undefined;
}

export function toggleStepForm(open: Record<string, StepFormKind>, stepKey: string, kind: StepFormKind): Record<string, StepFormKind> {
  if (open[stepKey] === kind) return closeStepForm(open, stepKey);
  return { ...open, [stepKey]: kind };
}

export function closeStepForm(open: Record<string, StepFormKind>, stepKey: string): Record<string, StepFormKind> {
  if (!(stepKey in open)) return open;
  const rest = { ...open };
  delete rest[stepKey];
  return rest;
}

function tooLong(what: string, limit: number): string {
  return `Keep ${what} to ${limit} characters or fewer.`;
}

export function checkStepForm(kind: StepFormKind, values: StepFormValues): { request: StepFormRequest } | { errors: StepFormErrors } {
  const errors: StepFormErrors = {};

  if (kind === "mark-done") {
    const note = values.note.trim();
    if (note.length > FIELD_LIMITS.note) errors.note = tooLong("the note", FIELD_LIMITS.note);
    if (Object.keys(errors).length) return { errors };
    return { request: { kind, ...(note ? { note } : {}) } };
  }

  if (kind === "confirm-court") {
    const court = values.court.trim();
    const email = values.email.trim();
    if (!court && !email) errors.court = "Choose the court, or type its email.";
    if (court.length > FIELD_LIMITS.court) errors.court = tooLong("the court's name", FIELD_LIMITS.court);
    if (email.length > FIELD_LIMITS.email) errors.email = tooLong("the email", FIELD_LIMITS.email);
    if (Object.keys(errors).length) return { errors };
    return { request: { kind, court, ...(email ? { email } : {}) } };
  }

  if (kind === "add-recipient") {
    const exact = recipientKind(values.kind);
    const name = values.recipient.trim();
    const email = values.email.trim();
    if (!exact) errors.kind = "Say law firm, hospital, school or other.";
    if (!name) errors.recipient = "Type their name.";
    else if (name.length > FIELD_LIMITS.recipient) errors.recipient = tooLong("the name", FIELD_LIMITS.recipient);
    if (!email) errors.email = "Type their email address.";
    else if (email.length > FIELD_LIMITS.email) errors.email = tooLong("the email", FIELD_LIMITS.email);
    if (Object.keys(errors).length) return { errors };
    return { request: { kind, recipientKind: exact, name, email } };
  }

  return { request: { kind } };
}

export interface StepFormCopy {
  title: string;

  explain: string;
  submit: string;
  busy: string;
}

export function stepFormCopy(kind: StepFormKind, step: { number?: number; label: string }, values: StepFormValues, who: string): StepFormCopy {
  const by = who.trim() || "you";
  if (kind === "mark-done") return { title: "Mark done", explain: markDoneQuestion(step, by), submit: "Mark done", busy: "Saving..." };
  if (kind === "confirm-court") {
    const court = values.court.trim();
    const email = values.email.trim();
    const explain = court || email ? confirmCourtCheck(court, email) : "Choose one of the suggested courts, or type the court's email. Nothing is drafted or sent.";
    return { title: "Confirm court", explain, submit: "Confirm court", busy: "Saving..." };
  }
  if (kind === "add-recipient") {
    const name = values.recipient.trim();
    const email = values.email.trim();
    const exact = recipientKind(values.kind);
    const explain =
      exact && name && email
        ? serviceRecipientCheck(exact, name, email, by)
        : "Add a law firm, hospital, school or someone else to serve. Case flow then drafts their service email; nothing is sent.";
    return { title: "Add service recipient", explain, submit: "Add recipient", busy: "Saving..." };
  }
  if (kind === "require-service") {
    return {
      title: "Personal service needed",
      explain: `Record, as ${by}, that the respondent is to be served personally. Case flow then drafts the email to referrer; nothing is sent.`,
      submit: "Mark service needed",
      busy: "Saving...",
    };
  }
  return { title: "Reset", explain: resetStepQuestion(step), submit: "Reset this step", busy: "Resetting..." };
}

export function stepFormDoneMessage(request: StepFormRequest): string {
  if (request.kind === "mark-done") return "Marked done outside Case flow.";
  if (request.kind === "confirm-court") return "Court confirmed. The court email can now be drafted.";
  if (request.kind === "add-recipient") return `${request.name} added. ${stepRefCap("serve_other")} can now draft their email.`;
  if (request.kind === "require-service") return "Personal service is marked needed. The email to referrer can now be drafted.";
  return "This step's mark is forgotten and the step was checked again. Nothing was deleted.";
}

export function stepFormFailedMessage(kind: StepFormKind): string {
  if (kind === "mark-done") return "Could not mark the step done.";
  if (kind === "confirm-court") return "Could not confirm the court.";
  if (kind === "add-recipient") return "Could not add the recipient.";
  if (kind === "require-service") return "Could not mark personal service as needed.";
  return "Could not reset the step.";
}

export function stepFormBlockedReason(opts: { running: string; busy: boolean }): string {
  return opts.running !== "" && !opts.busy ? "A step is running." : "";
}
