
import { createContext, useContext, useEffect } from "react";

export interface UnsavedSource {
  id: string;

  label: string;
  matterId?: string;

  clientName?: string;

  place?: string;

  persistent?: boolean;
}

export interface CurrentClient {
  matterId: string;
  clientName: string;

  tab: string;
}
export const CurrentClientContext = createContext<CurrentClient | null>(null);
export function useCurrentClient(): CurrentClient | null {
  return useContext(CurrentClientContext);
}

const sources = new Map<string, UnsavedSource>();
let listening = false;

function onBeforeUnload(event: { preventDefault: () => void; returnValue?: unknown }) {
  if (sources.size === 0) return;
  event.preventDefault();
  event.returnValue = "";
}

export function describeUnsaved(source: Omit<UnsavedSource, "id">): string {
  const who = source.clientName?.trim() || (source.matterId ? `matter ${source.matterId}` : "");
  const place = source.place?.trim();
  return `${source.label}${who ? ` for ${who}` : ""}${place ? ` (${place})` : ""}`;
}

export function setUnsaved(id: string, source: string | Omit<UnsavedSource, "id"> | null): void {
  if (source === null) sources.delete(id);
  else sources.set(id, typeof source === "string" ? { id, label: source } : { ...source, id });
  if (!listening && sources.size > 0 && typeof window !== "undefined") {
    window.addEventListener("beforeunload", onBeforeUnload);
    listening = true;
  }
}

export function unsavedSources(): UnsavedSource[] {
  return [...sources.values()];
}

export function unsavedLabels(): string[] {
  return unsavedSources().map(describeUnsaved);
}

export function confirmLeaveUnsaved(only?: string[]): boolean {
  const entries = [...sources.values()].filter((s) => (only ? only.includes(s.id) : !s.persistent));
  if (entries.length === 0) return true;
  const agreed = window.confirm(
    `You have unsaved changes: ${entries.map(describeUnsaved).join("; ")}.\n\nLeave them for now? They are kept as a draft on this computer and come back when you open that form again.`,
  );
  if (agreed) for (const s of entries) sources.delete(s.id);
  return agreed;
}

export function confirmDiscardUnsaved(only: string[]): boolean {
  const entries = [...sources.values()].filter((s) => only.includes(s.id));
  if (entries.length === 0) return true;
  const agreed = window.confirm(`Discard your unsaved changes: ${entries.map(describeUnsaved).join("; ")}?`);
  if (agreed) for (const s of entries) sources.delete(s.id);
  return agreed;
}

export function reloadKeepingDrafts(): void {
  if (typeof window === "undefined") return;
  window.removeEventListener("beforeunload", onBeforeUnload);
  listening = false;
  window.location.reload();
}

export function useReportUnsaved(id: string, source: string | Omit<UnsavedSource, "id">, dirty: boolean): void {
  useEffect(() => {
    setUnsaved(id, dirty ? source : null);
    return () => setUnsaved(id, null);
  });
}
