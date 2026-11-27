
export type VergilRole = "context" | "user" | "vergil" | "error";

export interface VergilMessage {
  role: VergilRole;
  text: string;

  feedback?: "up" | "down";

  sources?: VergilSources;
}

export interface VergilSources {
  sources_checked: string[];
  gaps: string[];
}

export function sourcesSummary(sources: VergilSources | undefined): string {
  const n = sources?.sources_checked?.length ?? 0;
  if (!n) return "";
  return `Checked ${n} ${n === 1 ? "source" : "sources"}`;
}

export interface VergilConversation {
  sessionId: string;
  matterId: string;
  startedAt: string;
  updatedAt: string;

  firstQuestion: string;

  title?: string;
  messages: VergilMessage[];
}

export function conversationAsText(messages: VergilMessage[]): string {
  return messages
    .filter((m): m is VergilMessage & { role: "user" | "vergil" } => m.role === "user" || m.role === "vergil")
    .map((m) => `${m.role === "user" ? "You" : "Vergil"}: ${m.text}`)
    .join("\n\n");
}

const STORAGE_KEY_PREFIX = "caseforge-client-viewer:vergil-history:";
const MAX_CONVERSATIONS_PER_MATTER = 15;

const MAX_CONVERSATION_AGE_DAYS = 30;

function storageKey(matterId: string): string {
  return `${STORAGE_KEY_PREFIX}${matterId}`;
}

function isExpired(conversation: VergilConversation, now: number): boolean {
  const updated = new Date(conversation.updatedAt).getTime();
  if (Number.isNaN(updated)) return false;
  return now - updated > MAX_CONVERSATION_AGE_DAYS * 86_400_000;
}

export function loadVergilHistory(matterId: string): VergilConversation[] {
  if (typeof window === "undefined" || !matterId) return [];
  try {
    const raw = window.localStorage.getItem(storageKey(matterId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    const all = Array.isArray(parsed) ? (parsed as VergilConversation[]) : [];
    const now = Date.now();
    const fresh = all.filter((entry) => !isExpired(entry, now));
    if (fresh.length !== all.length) {

      try {
        window.localStorage.setItem(storageKey(matterId), JSON.stringify(fresh));
      } catch {

      }
    }
    return fresh;
  } catch {
    return [];
  }
}

export function saveVergilConversation(conversation: VergilConversation): void {
  if (typeof window === "undefined" || !conversation.matterId || !conversation.sessionId) return;
  try {
    const current = loadVergilHistory(conversation.matterId).filter(
      (entry) => entry.sessionId !== conversation.sessionId,
    );
    const next = [conversation, ...current].slice(0, MAX_CONVERSATIONS_PER_MATTER);
    window.localStorage.setItem(storageKey(conversation.matterId), JSON.stringify(next));
  } catch {

  }
}

export function setVergilConversationTitle(matterId: string, sessionId: string, title: string): void {
  if (typeof window === "undefined" || !matterId || !sessionId || !title) return;
  try {
    const all = loadVergilHistory(matterId);
    if (!all.some((entry) => entry.sessionId === sessionId)) return;
    const next = all.map((entry) => (entry.sessionId === sessionId ? { ...entry, title } : entry));
    window.localStorage.setItem(storageKey(matterId), JSON.stringify(next));
  } catch {

  }
}

export function latestVergilConversation(matterId: string): VergilConversation | undefined {
  return loadVergilHistory(matterId)[0];
}

export function deleteVergilConversation(matterId: string, sessionId: string): void {
  if (typeof window === "undefined" || !matterId) return;
  try {
    const next = loadVergilHistory(matterId).filter((entry) => entry.sessionId !== sessionId);
    window.localStorage.setItem(storageKey(matterId), JSON.stringify(next));
  } catch {

  }
}

export type VergilRecencyBucket = "Today" | "Yesterday" | "Previous 7 days" | "Older";

export const VERGIL_RECENCY_BUCKET_ORDER: VergilRecencyBucket[] = ["Today", "Yesterday", "Previous 7 days", "Older"];

export function vergilRecencyBucket(iso: string, now: Date = new Date()): VergilRecencyBucket {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "Today";
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const daysAgo = Math.round((startOfDay(now) - startOfDay(when)) / 86_400_000);
  if (daysAgo <= 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  if (daysAgo <= 7) return "Previous 7 days";
  return "Older";
}
