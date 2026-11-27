
import { useEffect, useSyncExternalStore } from "react";

let cached = "";
let pending: Promise<string> | null = null;
const listeners = new Set<(name: string) => void>();

export function loadEditorName(fetcher: typeof fetch = fetch): Promise<string> {
  if (cached) return Promise.resolve(cached);
  if (!pending) {
    pending = fetcher("/api/me", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : { name: "" }))
      .then((body: { name?: unknown }) => {
        cached = typeof body?.name === "string" ? body.name.trim() : "";
        for (const listener of listeners) listener(cached);
        return cached;
      })
      .catch(() => "")
      .finally(() => {
        pending = null;
      });
  }
  return pending;
}

export function currentEditorName(): string {
  return cached;
}

export function useSignedInName(): string {
  const name = useSyncExternalStore(
    (onChange) => {
      const listener = () => onChange();
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    () => cached,
    () => "",
  );
  useEffect(() => {
    if (!cached) void loadEditorName();
  }, []);
  return name;
}

export function resetEditorNameForTests(): void {
  cached = "";
  pending = null;
  listeners.clear();
}
