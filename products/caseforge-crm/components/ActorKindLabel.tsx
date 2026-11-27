
import type { ComponentType, SVGProps } from "react";
import { actorKindWord, isActorKind, type ActorKind } from "@/lib/actorKind";
import { IconAutomation, IconBot, IconPerson } from "./icons";

const ICONS: Record<ActorKind, ComponentType<SVGProps<SVGSVGElement>>> = {
  person: IconPerson,
  agent: IconBot,
  automation: IconAutomation,
};

export function ActorKindLabel({ kind, className = "" }: { kind: unknown; className?: string }) {
  if (!isActorKind(kind)) return null;
  const Icon = ICONS[kind];
  return (
    <span className={`actor-kind actor-kind--${kind}${className ? ` ${className}` : ""}`}>
      <Icon className="actor-kind-icon" />
      {actorKindWord(kind)}
    </span>
  );
}
