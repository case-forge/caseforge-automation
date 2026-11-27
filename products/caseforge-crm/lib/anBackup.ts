import type { AnDraft, AnFormState } from "./anDrafts";
import { isBlankAnForm, isWorkingFromDraft, kindOf, loadDrafts, loadWorkingCopy, saveDrafts, saveWorkingCopy } from "./anDrafts";

export interface AnBackup {
  working: AnFormState | null;
  drafts: AnDraft[];
}

const URL = "/api/attendance-notes/backup";

function localIsEmpty(matterId: string): boolean {
  const working = loadWorkingCopy(matterId);
  return isBlankAnForm(working) && kindOf(working) === "call" && loadDrafts(matterId).length === 0 && !isWorkingFromDraft(matterId);
}

export async function restoreIfLocalEmpty(matterId: string): Promise<AnBackup | null> {
  if (!matterId || !localIsEmpty(matterId)) return null;
  try {
    const res = await fetch(`${URL}?matter_id=${encodeURIComponent(matterId)}`, { cache: "no-store" });
    if (!res.ok) return null;
    const body = (await res.json()) as Partial<AnBackup>;
    const working = body.working ?? null;
    const drafts = Array.isArray(body.drafts) ? body.drafts : [];
    if (!working && drafts.length === 0) return null;

    if (!localIsEmpty(matterId)) return null;
    if (working) saveWorkingCopy(matterId, working);
    saveDrafts(matterId, drafts);
    return { working, drafts };
  } catch {
    return null;
  }
}

export async function pushBackup(matterId: string): Promise<void> {
  if (!matterId) return;
  const working = loadWorkingCopy(matterId);
  const keepWorking = !(isBlankAnForm(working) && kindOf(working) === "call");
  try {
    await fetch(URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ matter_id: matterId, working: keepWorking ? working : null, drafts: loadDrafts(matterId) }),
    });
  } catch {

  }
}

const PUSH_DELAY_MS = 1500;
const timers = new Map<string, ReturnType<typeof setTimeout>>();

export function schedulePush(matterId: string): void {
  if (!matterId || typeof window === "undefined") return;
  const pending = timers.get(matterId);
  if (pending) clearTimeout(pending);
  timers.set(
    matterId,
    setTimeout(() => {
      timers.delete(matterId);
      void pushBackup(matterId);
    }, PUSH_DELAY_MS),
  );
}

export function flushPush(matterId: string): void {
  const pending = timers.get(matterId);
  if (!pending) return;
  clearTimeout(pending);
  timers.delete(matterId);
  void pushBackup(matterId);
}
