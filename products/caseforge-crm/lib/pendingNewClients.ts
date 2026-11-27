"use client";

import { createPulseSlice } from "./pulse";
import { backgroundFetch } from "./loadingBar";
import { LATE_MINUTES, OVERDUE_MINUTES, waitedLabel, waitLine, waitTone, type WaitTone } from "./pendingWait";

export { LATE_MINUTES, OVERDUE_MINUTES, waitedLabel, waitLine, waitTone, type WaitTone };

export type EmailState = "sent" | "draft" | "draft_gone" | "unknown";

export interface PendingNewClient {
  pending_id: number;
  created_utc: string;
  created_by: string;
  full_name: string;
  email: string;

  phone?: string;
  category_label: string;
  folder_path: string;
  extra_forms: string[];
  draft_web_link: string;
  status: string;
  email_state: EmailState;
  email_sent_utc: string;
  note: string;
  forms_back: string[];

  stage: PressStage;

  waiting_minutes?: number;

  overdue?: boolean;
}
export type PressStage = "folder" | "pack" | "done";

export interface ResumedNewClient {
  pending_id?: number;
  folder: string;
  category: string;
  drafts: { documents: string; web_link?: string }[];
  resumed?: boolean;
  resumed_notes?: string[];
}

export function isUnfinished(item: Pick<PendingNewClient, "stage">): boolean {
  return item.stage === "folder" || item.stage === "pack";
}

export function unfinishedLabel(stage: PressStage | undefined): string {
  switch (stage) {
    case "folder":
      return "Not finished: the press stopped while making the folder. Finish carries on from there and makes nothing twice.";
    case "pack":
      return "Not finished: the folder is made, the forms and the Outlook draft are not. Finish carries on from there and makes nothing twice.";
    default:
      return "";
  }
}

export function resumedLines(made: Pick<ResumedNewClient, "resumed" | "resumed_notes">): string[] {
  if (!made.resumed) return [];
  return ["Carried on from the earlier press that stopped part-way. Nothing was made twice.", ...(made.resumed_notes ?? [])];
}

export function newPressId(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  return uuid ?? `press-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export async function resumePendingNewClient(pendingId: number): Promise<ResumedNewClient> {
  const res = await fetch("/api/new-client/pending/resume", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pending_id: pendingId }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(String(body.error ?? "The new client could not be finished. Nothing was made twice."));
  pendingCountsStore.refresh();
  return body as ResumedNewClient;
}

export interface PendingNewClientsList {
  items: PendingNewClient[];
  unsent: number;

  overdue?: number;
  waiting: number;
}

export interface PendingNewClientsCounts {
  unsent: number;
  overdue?: number;
  waiting: number;
}

export const pendingCountsStore = createPulseSlice<PendingNewClientsCounts>((pulse) => pulse.pending_new_clients);

export function pendingBadgeLabel(waiting: number, unsent = 0, overdue = 0): string {
  if (waiting <= 0) return "New client";
  const base = `New client, ${waiting} waiting for their New Client Form`;
  const sent = unsent > 0 ? `${base}, ${unsent} pack ${unsent === 1 ? "email" : "emails"} not sent yet` : base;
  return overdue > 0 ? `${sent}, ${overdue} overdue` : sent;
}

export function emailStateLabel(state: EmailState): string {
  switch (state) {
    case "sent":
      return "Sent";
    case "draft":
      return "Not sent: the draft is in Outlook";
    case "draft_gone":
      return "Not sent: the draft is no longer in Drafts";
    default:
      return "Not known: Outlook could not be checked";
  }
}

const FORM_NAMES: Record<string, string> = {
  ncf: "New Client Form",
  rif: "Opponent Info Form",
  laif: "Legal Aid Info Form",
};

export function formsBackLabel(kinds: string[]): string {
  const names = kinds.map((k) => FORM_NAMES[k] ?? k).filter(Boolean);
  return names.length ? names.join(", ") : "None yet";
}

export async function fetchPendingNewClients(): Promise<PendingNewClientsList> {
  const res = await backgroundFetch("/api/new-client/pending", { cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(String(body.error ?? "The list of waiting new clients could not be read."));
  return body as PendingNewClientsList;
}

export async function cancelPendingNewClient(pendingId: number): Promise<PendingNewClientsList> {
  const res = await fetch("/api/new-client/pending/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pending_id: pendingId }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(String(body.error ?? "The new client could not be cancelled."));
  const list = body as PendingNewClientsList;
  pendingCountsStore.set({ unsent: list.unsent, overdue: list.overdue ?? 0, waiting: list.waiting });
  return list;
}
