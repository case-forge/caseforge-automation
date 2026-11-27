
export type ActorKind = "person" | "agent" | "automation";

export const ACTOR_KINDS: readonly ActorKind[] = ["person", "agent", "automation"];

const WORDS: Record<ActorKind, string> = { person: "Person", agent: "Agent", automation: "Automation" };

export function isActorKind(value: unknown): value is ActorKind {
  return typeof value === "string" && (ACTOR_KINDS as readonly string[]).includes(value);
}

export function actorKindWord(kind: unknown): string {
  return isActorKind(kind) ? WORDS[kind] : "";
}
