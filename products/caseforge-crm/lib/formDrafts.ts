
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchServerDraft, removeServerDraft, scheduleServerDraft } from "./formDraftBackup";

export const DRAFT_PREFIX = "caseforge-client-viewer:form-draft:";
export const DRAFT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

interface StoredDraft<T> {
  savedAt: number;
  data: T;
}

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage ?? null;
  } catch {
    return null;
  }
}

export function draftKey(matterId: string | number | null | undefined, formId: string): string {
  const matter = matterId == null || String(matterId).trim() === "" ? "none" : String(matterId).trim();
  return `${DRAFT_PREFIX}${matter}:${formId}`;
}

export function saveDraft<T>(matterId: string | number | null | undefined, formId: string, data: T, now = Date.now()): void {
  try {
    storage()?.setItem(draftKey(matterId, formId), JSON.stringify({ savedAt: now, data } satisfies StoredDraft<T>));
  } catch {

  }
}

export function loadDraft<T>(
  matterId: string | number | null | undefined,
  formId: string,
  now = Date.now(),
): StoredDraft<T> | null {
  const key = draftKey(matterId, formId);
  try {
    const raw = storage()?.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredDraft<T>>;
    if (typeof parsed.savedAt !== "number" || parsed.data === undefined || now - parsed.savedAt > DRAFT_MAX_AGE_MS) {
      storage()?.removeItem(key);
      return null;
    }
    return { savedAt: parsed.savedAt, data: parsed.data };
  } catch {
    return null;
  }
}

export function clearDraft(matterId: string | number | null | undefined, formId: string): void {
  try {
    storage()?.removeItem(draftKey(matterId, formId));
  } catch {

  }
}

export function pruneExpiredDrafts(now = Date.now()): void {
  const store = storage();
  if (!store) return;
  try {
    const keys: string[] = [];
    for (let i = 0; i < store.length; i++) {
      const key = store.key(i);
      if (key?.startsWith(DRAFT_PREFIX)) keys.push(key);
    }
    for (const key of keys) {
      try {
        const parsed = JSON.parse(store.getItem(key) ?? "") as Partial<StoredDraft<unknown>>;
        if (typeof parsed.savedAt !== "number" || now - parsed.savedAt > DRAFT_MAX_AGE_MS) store.removeItem(key);
      } catch {
        store.removeItem(key);
      }
    }
  } catch {

  }
}

export function changedValues<T extends object>(current: T, base: T): Partial<T> {
  const out: Partial<T> = {};
  for (const key of Object.keys(current) as (keyof T)[]) {
    if (JSON.stringify(current[key]) !== JSON.stringify(base[key])) out[key] = current[key];
  }
  return out;
}

export function draftTimeLabel(savedAt: number): string {
  const d = new Date(savedAt);
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });
  const day = d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "Europe/London" });
  return `${time} on ${day.replace(",", "")}`;
}

export function useFormDraft<T>({
  matterId,
  formId,
  dirty,
  data,
  restore,
  ready = true,
  server = false,
}: {
  matterId: string | number | null | undefined;
  formId: string;
  dirty: boolean;
  data: T;
  restore: (data: T) => boolean | void;
  ready?: boolean;
  server?: boolean;
}): { restoredAt: number | null; clear: () => void } {
  const [restoredAt, setRestoredAt] = useState<number | null>(null);
  const checked = useRef(false);
  const matterKey = matterId == null ? "" : String(matterId).trim();
  const serverOn = server && matterKey !== "";

  const serverPending = useRef(false);

  const everKept = useRef(false);
  const dirtyRef = useRef(dirty);
  const unmounted = useRef(false);
  useEffect(() => {
    dirtyRef.current = dirty;
  });
  useEffect(() => {
    unmounted.current = false;
    return () => {
      unmounted.current = true;
    };
  }, []);

  const skipNext = useRef(false);
  const restoreRef = useRef(restore);
  useEffect(() => {
    restoreRef.current = restore;
  });

  useEffect(() => {
    if (checked.current || !ready) return;
    checked.current = true;
    const found = loadDraft<T>(matterId, formId);
    if (!found) {
      if (!serverOn) return;
      serverPending.current = true;
      void fetchServerDraft<T>(matterKey, formId).then((remote) => {
        serverPending.current = false;

        if (!remote || unmounted.current || dirtyRef.current) return;
        if (restoreRef.current(remote.data) === false) {
          removeServerDraft(matterKey, formId);
          return;
        }
        everKept.current = true;
        saveDraft(matterId, formId, remote.data, remote.savedAt);
        skipNext.current = true;
        setRestoredAt(remote.savedAt);
      });
      return;
    }
    if (restoreRef.current(found.data) === false) {
      clearDraft(matterId, formId);
      if (serverOn) removeServerDraft(matterKey, formId);
      return;
    }
    everKept.current = true;
    skipNext.current = true;
    setRestoredAt(found.savedAt);
  }, [ready, matterId, formId, serverOn, matterKey]);

  const serialised = JSON.stringify(data);
  useEffect(() => {
    if (!checked.current) return;
    if (skipNext.current) {
      skipNext.current = false;
      return;
    }
    if (dirty) {
      everKept.current = true;
      const value = JSON.parse(serialised) as T;
      saveDraft(matterId, formId, value);
      if (serverOn) scheduleServerDraft(matterKey, formId, value);
    } else {
      clearDraft(matterId, formId);
      setRestoredAt(null);
      if (serverOn && everKept.current && !serverPending.current) {
        everKept.current = false;
        removeServerDraft(matterKey, formId);
      }
    }
  }, [dirty, serialised, matterId, formId, serverOn, matterKey]);

  const clear = useCallback(() => {
    clearDraft(matterId, formId);
    setRestoredAt(null);
    if (serverOn) removeServerDraft(matterKey, formId);
  }, [matterId, formId, serverOn, matterKey]);
  return { restoredAt, clear };
}
