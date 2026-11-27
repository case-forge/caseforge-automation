
import type { PendingNewClient, PendingNewClientsList, ResumedNewClient } from "./pendingNewClients";
import { OVERDUE_MINUTES } from "./pendingWait";

function entry(id: number, name: string, email: string, minutesAgo: number, extra: Partial<PendingNewClient> = {}): PendingNewClient {
  return {
    pending_id: id,
    created_utc: new Date(Date.now() - minutesAgo * 60_000).toISOString(),
    created_by: "CO",
    full_name: name,
    email,
    category_label: "Immigration",
    folder_path: `stub/${name}`,
    extra_forms: [],
    draft_web_link: "https://outlook.office.com/mail/drafts",
    status: "pending",
    email_state: "draft",
    email_sent_utc: "",
    note: "",
    forms_back: [],
    stage: "done",
    ...extra,
  };
}

type StubState = { waiting: PendingNewClient[]; nextId: number };
const state: StubState = ((globalThis as { __valStubPendingNewClients?: StubState }).__valStubPendingNewClients ??= {
  waiting: [

    entry(3, "Halfa Madetest", "halfa.madetest@example.com", 5, {
      stage: "pack",
      draft_web_link: "",
      email_state: "unknown",
      note: "Not finished: the forms and the Outlook draft could not be made (Boom). Press Finish to carry on.",
    }),
    entry(2, "Stubbie Waitingtest", "stubbie.waitingtest@example.com", 90, { extra_forms: ["respondent"], forms_back: ["rif"] }),
    entry(1, "Testa Pendingname", "testa.pendingname@example.com", 34),
  ],
  nextId: 4,
});
const waiting = state.waiting;

export function stubPendingNewClients(): PendingNewClientsList {
  const now = Date.now();
  const items = waiting.map((i) => {
    const waited = Math.max(0, Math.floor((now - new Date(i.created_utc).getTime()) / 60_000));
    const unsent = i.email_state !== "sent" || i.stage !== "done";
    return { ...i, waiting_minutes: waited, overdue: unsent && waited >= OVERDUE_MINUTES };
  });
  return {
    items,
    unsent: items.filter((i) => i.email_state !== "sent").length,
    overdue: items.filter((i) => i.overdue).length,
    waiting: items.length,
  };
}

export function stubPendingCounts(): { unsent: number; overdue: number; waiting: number } {
  const { unsent, overdue, waiting: count } = stubPendingNewClients();
  return { unsent, overdue: overdue ?? 0, waiting: count };
}

export function stubCancelPendingNewClient(pendingId: number): PendingNewClientsList | null {
  const index = waiting.findIndex((i) => i.pending_id === pendingId);
  if (index < 0) return null;
  waiting.splice(index, 1);
  return stubPendingNewClients();
}

export function stubResumePendingNewClient(pendingId: number): ResumedNewClient | null {
  const item = waiting.find((i) => i.pending_id === pendingId);
  if (!item) return null;
  const unfinished = item.stage !== "done";
  item.stage = "done";
  item.note = "";
  item.draft_web_link = "https://outlook.office.com/mail/drafts";
  item.email_state = "draft";
  return {
    pending_id: item.pending_id,
    folder: item.folder_path,
    category: item.category_label,
    drafts: [{ documents: "New Client Form + Letter of Authority", web_link: item.draft_web_link }],
    resumed: true,
    resumed_notes: unfinished
      ? ["New Client Form + Letter of Authority envelope: the one the earlier press made was used.", "Outlook draft: made now."]
      : ["Nothing was left to do: the folder, the forms and the Outlook draft were already made."],
  };
}

export function stubAddPendingNewClient(name: string, email: string, category: string, extraForms: string[]): number {
  const id = state.nextId++;
  waiting.unshift(entry(id, name, email, 0, { category_label: category, extra_forms: extraForms }));
  return id;
}
