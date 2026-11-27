
const URL = "/api/form-drafts/backup";
const PUSH_DELAY_MS = 1500;
const timers = new Map<string, ReturnType<typeof setTimeout>>();

function timerKey(matterId: string, formId: string): string {
  return `${matterId}\u0000${formId}`;
}

export async function fetchServerDraft<T>(matterId: string, formId: string): Promise<{ savedAt: number; data: T } | null> {
  if (!matterId || !formId) return null;
  try {
    const res = await fetch(`${URL}?matter_id=${encodeURIComponent(matterId)}&form_id=${encodeURIComponent(formId)}`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { saved_at?: unknown; data?: unknown };
    if (typeof body.saved_at !== "number" || body.data === null || body.data === undefined) return null;
    return { savedAt: body.saved_at, data: body.data as T };
  } catch {
    return null;
  }
}

async function send(matterId: string, formId: string, savedAt: number | null, data: unknown): Promise<void> {
  try {
    await fetch(URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ matter_id: matterId, form_id: formId, saved_at: savedAt, data }),
    });
  } catch {

  }
}

export function scheduleServerDraft(matterId: string, formId: string, data: unknown, now = Date.now()): void {
  if (!matterId || !formId || typeof window === "undefined") return;
  const key = timerKey(matterId, formId);
  const pending = timers.get(key);
  if (pending) clearTimeout(pending);
  timers.set(
    key,
    setTimeout(() => {
      timers.delete(key);
      void send(matterId, formId, now, data);
    }, PUSH_DELAY_MS),
  );
}

export function removeServerDraft(matterId: string, formId: string): void {
  if (!matterId || !formId) return;
  const key = timerKey(matterId, formId);
  const pending = timers.get(key);
  if (pending) clearTimeout(pending);
  timers.delete(key);
  void send(matterId, formId, null, null);
}
