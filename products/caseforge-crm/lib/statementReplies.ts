"use client";

import { usePolledStore } from "./polledStore";
import { createPulseSlice } from "./pulse";
import type { ReplyState, StatementReplies } from "./statementRepliesTypes";
import { backgroundFetch } from "./loadingBar";

export type { ReplyState, StatementReplies, StatementReply } from "./statementRepliesTypes";

export const STATEMENT_REPLIES_CHANGED_EVENT = "caseforge:statement-replies-changed";

export const LIST_WORDS: Record<ReplyState, { title: string; empty: string; note: string }> = {
  approved: {
    title: "Statement approved",
    empty: "No client has approved a statement yet.",
    note: "Clients who said they are happy with their witness statement. An entry leaves by itself once the statement has gone to the court; Hide / Done removes it now. Nothing is sent.",
  },
  amend: {
    title: "Wants changes",
    empty: "No client is asking for changes.",
    note: "Clients who want their witness statement changed, with what they asked for. Hide / Done removes an entry once it is dealt with. Nothing is sent.",
  },
};

export function replyButtonLabel(state: ReplyState, count: number): string {
  const title = LIST_WORDS[state].title;
  return count > 0 ? `${title}, ${count} client${count === 1 ? "" : "s"}` : `${title}, none`;
}

export async function setStatementReply(matterId: string, state: ReplyState | "", note: string): Promise<void> {
  const res = await fetch("/api/statement-replies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, state, note }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body?.error === "string" && body.error ? body.error : "Could not record the reply.");
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(STATEMENT_REPLIES_CHANGED_EVENT));
}

export async function hideStatementReply(matterId: string): Promise<void> {
  const res = await fetch("/api/statement-replies/hide", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body?.error === "string" && body.error ? body.error : "Could not hide the reply.");
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(STATEMENT_REPLIES_CHANGED_EVENT));
}

const repliesStore = createPulseSlice<StatementReplies>((pulse) => pulse.statement_replies);

export function useStatementReplies(): { data: StatementReplies | null; refresh: () => void } {
  return usePolledStore(repliesStore);
}
