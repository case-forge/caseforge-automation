
import type { ComponentType, SVGProps } from "react";
import { IconCalendar, IconFunnel, IconPlus, IconSparkles } from "@/components/icons";
import type { CornerId } from "./cornerPrompts";

export interface Launcher {
  id: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  window: CornerId;

  hint: string;
}

export const LAUNCHERS: Launcher[] = [
  { id: "hearings", label: "Hearings Panel", icon: IconCalendar, window: "hearings", hint: "Open the hearings panel" },
  { id: "whats-new", label: "What's New", icon: IconSparkles, window: "whats-new", hint: "Open the What's New card" },
  { id: "classifier", label: "Improve Classifier", icon: IconFunnel, window: "classifier", hint: "Open the email classifier question" },
  { id: "add-hearing", label: "Add a Hearing", icon: IconPlus, window: "add-hearing", hint: "Add a hearing: up to five tabs, one hearing each" },
];

export function visibleLaunchers(hidden: readonly string[], list: Launcher[] = LAUNCHERS): Launcher[] {
  return list.filter((l) => !hidden.includes(l.id));
}
