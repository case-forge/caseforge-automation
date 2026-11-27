
import type { StatusBoardItem } from "./matterMilestones";

export type NudgeDoc = "client_docs" | "witness_statement";

export type NudgeColumn = "ws" | "loa";

const DOC_OF_COLUMN: Record<NudgeColumn, NudgeDoc> = { ws: "witness_statement", loa: "client_docs" };

export function nudgeDocFor(item: Pick<StatusBoardItem, "nudge"> & { milestones?: { contacted?: string } }, column: string, cellValue: string): NudgeDoc | null {
  if (cellValue) return null;

  if (!item.milestones?.contacted) return null;
  const doc = DOC_OF_COLUMN[column as NudgeColumn];
  return doc && item.nudge?.[doc] ? doc : null;
}

const DOC_WORDS: Record<NudgeDoc, string> = { client_docs: "their documents", witness_statement: "their witness statement" };

export const nudgeLabel = (clientName: string, doc: NudgeDoc): string => `Nudge ${clientName} to sign ${DOC_WORDS[doc]}`;
export const nudgeQuestion = (clientName: string): string => `Send a reminder to ${clientName}?`;
export const NUDGE_NOTE = "This makes the reminder email. If Case flow is on Auto for this client it sends itself after a short wait; otherwise it waits in Drafts for you to send.";
export const NUDGE_FAILED_LINE = "The reminder could not be made.";
