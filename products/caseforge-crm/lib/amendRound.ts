
import type { AmendFlagKind, AmendOpenRound, AmendParagraph, AmendRepeat, AmendStepInfo } from "./pipelineTypes";

export type AmendAction = "prepare" | "approve" | "discard";

export const AMEND_EMAIL_MAX = 60_000;
export const AMEND_ANSWERS_MAX = 5_000;

export const AMEND_KEEP_ID_MAX = 40;
export const AMEND_KEEP_MAX_COUNT = 500;
export const AMEND_CLIENT_QUESTIONS_MAX = 8;
export const AMEND_CLIENT_QUESTION_MAX = 800;

export const AMEND_EDIT_MAX = 4_000;

export type AmendHubBody =
  | { action: "prepare"; matter_id: string; by: string; email_text: string }
  | { action: "approve"; matter_id: string; by: string; round: number; answers: string; keep_original: string[]; client_questions?: string[]; edits?: Record<string, string> }
  | { action: "discard"; matter_id: string; by: string; round: number };

export const AMEND_HUB_PATHS: Record<AmendAction, string> = {
  prepare: "/client-viewer/pipeline/amend/prepare",
  approve: "/client-viewer/pipeline/amend/approve",
  discard: "/client-viewer/pipeline/amend/discard",
};

function positiveRound(value: unknown): number {
  const n = typeof value === "number" ? value : typeof value === "string" && /^\d+$/.test(value.trim()) ? Number(value.trim()) : NaN;
  return Number.isInteger(n) && n > 0 ? n : 0;
}

export function checkAmendRequest(payload: Record<string, unknown>): { body: AmendHubBody } | { error: string } {
  const action = String(payload.action ?? "").trim();
  if (action !== "prepare" && action !== "approve" && action !== "discard") return { error: "action must be prepare, approve or discard" };
  const matterId = String(payload.matter_id ?? "").trim();
  const by = String(payload.by ?? "").trim().slice(0, 60);
  if (!matterId) return { error: "matter_id is required" };
  if (!by) return { error: "type your name first" };

  if (action === "prepare") {
    const emailText = String(payload.email_text ?? "").trim().slice(0, AMEND_EMAIL_MAX);
    if (!emailText) return { error: "paste the client's email asking for changes first" };
    return { body: { action, matter_id: matterId, by, email_text: emailText } };
  }

  const round = positiveRound(payload.round);
  if (!round) return { error: "round must be a positive whole number" };
  if (action === "discard") return { body: { action, matter_id: matterId, by, round } };

  const answers = String(payload.answers ?? "").trim().slice(0, AMEND_ANSWERS_MAX);
  const keep = payload.keep_original ?? [];
  if (!Array.isArray(keep)) return { error: "keep_original must be a list of paragraph ids" };
  if (keep.length > AMEND_KEEP_MAX_COUNT) return { error: "keep_original has too many paragraph ids" };
  const keepOriginal: string[] = [];
  for (const item of keep) {
    if (typeof item !== "string") return { error: "keep_original must be a list of paragraph ids" };
    const id = item.trim();
    if (!id || id.length > AMEND_KEEP_ID_MAX) return { error: "keep_original has an id that is not a paragraph id" };
    if (!keepOriginal.includes(id)) keepOriginal.push(id);
  }

  const rawEdits = payload.edits ?? {};
  if (!rawEdits || typeof rawEdits !== "object" || Array.isArray(rawEdits)) return { error: "edits must be a map of paragraph id to text" };
  const edits: Record<string, string> = {};
  for (const [key, value] of Object.entries(rawEdits as Record<string, unknown>)) {
    const id = key.trim();
    if (!id || id.length > AMEND_KEEP_ID_MAX) return { error: "edits has an id that is not a paragraph id" };
    if (typeof value !== "string") return { error: `the text for ${id} must be text` };
    const text = value.replace(/\s*[\r\n]+\s*/g, " ").trim();
    if (!text) return { error: `the edited text for ${id} is empty: use Keep the original instead` };
    if (text.length > AMEND_EDIT_MAX) return { error: `the edited text for ${id} is too long (over ${AMEND_EDIT_MAX} characters)` };
    if (/^\s*\d{1,3}[.)]\s/.test(text)) return { error: `the edited text for ${id} starts with a paragraph number: the statement keeps its own numbering` };
    if (Object.keys(edits).length >= AMEND_KEEP_MAX_COUNT) return { error: "edits has too many paragraphs" };
    edits[id] = text;
  }
  const editsPart = Object.keys(edits).length ? { edits } : {};
  const asked = payload.client_questions;
  if (asked === undefined || asked === null) return { body: { action, matter_id: matterId, by, round, answers, keep_original: keepOriginal, ...editsPart } };
  if (!Array.isArray(asked) || asked.length > AMEND_CLIENT_QUESTIONS_MAX || asked.some((q) => typeof q !== "string")) return { error: "client_questions must be a short list of questions" };
  const clientQuestions = (asked as string[]).map((q) => q.trim().slice(0, AMEND_CLIENT_QUESTION_MAX)).filter((q) => q);
  return { body: { action, matter_id: matterId, by, round, answers, keep_original: keepOriginal, client_questions: clientQuestions, ...editsPart } };
}

export function hubBodyFor(body: AmendHubBody): Record<string, unknown> {
  const { action, ...rest } = body;
  void action;
  return rest;
}

export const AMEND_FLAG_LABELS: Record<AmendFlagKind, { badge: string; meaning: string }> = {
  review: { badge: "REVIEW", meaning: "Sentences in the old text are missing from the new text." },
  editorial: { badge: "Editorialising", meaning: "The new text adds opinion or comment rather than fact." },
  asked_again: { badge: "Asked again", meaning: "The client asked for this in an earlier round too." },
  changed_often: { badge: "Changed in 3+ rounds", meaning: "This paragraph has changed in three or more rounds." },
  merged: { badge: "Text from another paragraph", meaning: "The new text carries words from another paragraph." },
  facts_unread: { badge: "Facts not read", meaning: "The change relies on facts nobody has read in the client's papers." },
};

export function amendFlagLabel(kind: string): { badge: string; meaning: string } {
  return AMEND_FLAG_LABELS[kind as AmendFlagKind] ?? { badge: "Check", meaning: "Look at this before approving." };
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function paragraphsToCheck(round: Pick<AmendOpenRound, "paragraphs">): AmendParagraph[] {
  return round.paragraphs.filter((p) => p.flags.length > 0);
}

export function amendRoundSummary(round: Pick<AmendOpenRound, "paragraphs" | "questions">): string {
  const changed = round.paragraphs.filter((p) => p.para !== null).length;
  const added = round.paragraphs.length - changed;
  const check = paragraphsToCheck(round).length;
  const parts = [plural(changed, "paragraph changed", "paragraphs changed")];
  if (added) parts.push(plural(added, "new paragraph", "new paragraphs"));
  if (check) parts.push(`${check} to check`);
  if (round.questions.length) parts.push(plural(round.questions.length, "question to answer", "questions to answer"));
  return parts.join(", ");
}

export function paragraphHeading(p: Pick<AmendParagraph, "para">): string {
  return p.para === null ? "New paragraph (added at the end)" : `Paragraph ${p.para}`;
}

export function questionTypeLabel(type: string): string {
  return type === "asks_advice" ? "Asks for advice" : "Question to you";
}

export function repeatLine(r: Pick<AmendRepeat, "earlier_round" | "in_text_now">): string {
  return `Asked again: first asked in round ${r.earlier_round}; ${r.in_text_now ? "already in the text now" : "NOT in the text now"}.`;
}

export function flaggedLine(info: Pick<AmendStepInfo, "rounds" | "flagged" | "open">): string {
  if (!info.flagged) return "";
  return `Round ${info.open?.round ?? info.rounds}: this client is flagged (3 or more rounds).`;
}

export function approveLabel(status: AmendOpenRound["status"]): string {
  return status === "saved" ? "Draft email (the statement is already saved)" : "Approve: save the statement and draft the email";
}

export function prepareBlockedReason(opts: { canStart: boolean; startBlocked: string; locked: string; busy: boolean; hasEmail: boolean }): string {
  if (opts.locked) return opts.locked;
  if (opts.busy) return "A step is running.";
  if (!opts.canStart) return opts.startBlocked || "A new round cannot be prepared now.";
  if (!opts.hasEmail) return "Paste the client's email first.";
  return "";
}

export function decideBlockedReason(opts: { locked: string; busy: boolean }): string {
  if (opts.locked) return opts.locked;
  if (opts.busy) return "A step is running.";
  return "";
}

export function editProblem(text: string): string {
  const t = text.replace(/\s*[\r\n]+\s*/g, " ").trim();
  if (!t) return "The text is empty: use Keep the original, or discard the round, instead.";
  if (t.length > AMEND_EDIT_MAX) return `The text is too long (over ${AMEND_EDIT_MAX} characters).`;
  if (/^\d{1,3}[.)]\s/.test(t)) return "Leave out the paragraph number: the statement keeps its own numbering.";
  return "";
}

export interface DiffPart {
  kind: "same" | "del" | "ins";
  text: string;
}

const DIFF_CELL_LIMIT = 250_000;

function mergeParts(parts: DiffPart[]): DiffPart[] {
  const out: DiffPart[] = [];
  for (const part of parts) {
    const last = out[out.length - 1];
    if (last && last.kind === part.kind) last.text += part.text;
    else out.push({ ...part });
  }
  return out;
}

const DIFF_TOKEN = /[^\s.,;:!?]+\s*|[.,;:!?]+\s*|\s+/g;

export function wordDiff(before: string, after: string): DiffPart[] {
  const a = before.match(DIFF_TOKEN) ?? [];
  const b = after.match(DIFF_TOKEN) ?? [];
  if (a.length * b.length > DIFF_CELL_LIMIT) {
    return [...(before ? [{ kind: "del" as const, text: before }] : []), ...(after ? [{ kind: "ins" as const, text: after }] : [])];
  }
  const key = (w: string) => w.trim();
  const n = a.length;
  const m = b.length;
  const table: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      table[i][j] = key(a[i]) === key(b[j]) ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const parts: DiffPart[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (key(a[i]) === key(b[j])) {

      parts.push({ kind: "same", text: a[i] === b[j] ? a[i] : key(a[i]) });
      if (a[i] !== b[j]) {
        const tailA = a[i].slice(key(a[i]).length);
        const tailB = b[j].slice(key(b[j]).length);
        if (tailA) parts.push({ kind: "del", text: tailA });
        if (tailB) parts.push({ kind: "ins", text: tailB });
      }
      i++;
      j++;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      parts.push({ kind: "del", text: a[i++] });
    } else {
      parts.push({ kind: "ins", text: b[j++] });
    }
  }
  while (i < n) parts.push({ kind: "del", text: a[i++] });
  while (j < m) parts.push({ kind: "ins", text: b[j++] });
  return mergeParts(parts);
}
