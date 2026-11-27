
import { FIRM } from "./firm";

export const TAILNET_EDITOR = "tailnet";

export const MAX_EDITOR_LENGTH = 60;

export function displayNameFor(email: string, workers: readonly string[] = FIRM.workers): string {
  const clean = email.split(/\s+/).filter(Boolean).join(" ");
  if (!clean) return "";
  const first = (clean.split("@", 1)[0].split(/[._+-]/, 1)[0] ?? "").toLowerCase();
  const worker = first ? workers.find((w) => w.trim().toLowerCase() === first) : undefined;
  return worker ? worker.trim() : clean.slice(0, MAX_EDITOR_LENGTH);
}

export function editorFor(remoteUser: string | null | undefined, workers: readonly string[] = FIRM.workers): string {
  const email = (remoteUser ?? "").trim();
  return email ? displayNameFor(email, workers) : TAILNET_EDITOR;
}
