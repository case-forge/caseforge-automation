"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AnimationEvent, ReactNode } from "react";

export const EXIT_MS = 220;

export type Phase = "open" | "closing" | "closed";
export type PresenceEvent = "show" | "hide" | "done";

export function presenceStep(phase: Phase, event: PresenceEvent): Phase {
  if (event === "show") return "open";
  if (event === "hide") return phase === "open" ? "closing" : phase;
  return phase === "closing" ? "closed" : phase;
}

export function effectivePhase(show: boolean, phase: Phase): Phase {
  if (show) return "open";
  return phase === "open" ? "closing" : phase;
}

export function exitDuration(reducedMotion: boolean, ms: number = EXIT_MS): number {
  return reducedMotion ? 0 : ms;
}

export function endsExit(phase: Phase, target: unknown, currentTarget: unknown): boolean {
  return phase === "closing" && target === currentTarget;
}

export function usePresence(show: boolean, ms: number = EXIT_MS): { mounted: boolean; phase: Phase; onAnimationEnd: (event: AnimationEvent<HTMLElement>) => void } {
  const [phase, setPhase] = useState<Phase>(show ? "open" : "closed");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shown = effectivePhase(show, phase);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (show) {
      setPhase((p) => presenceStep(p, "show"));
      return;
    }
    setPhase((p) => presenceStep(p, "hide"));
    const reduced = typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    timer.current = setTimeout(() => setPhase((p) => presenceStep(p, "done")), exitDuration(reduced, ms));
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [show, ms]);

  const onAnimationEnd = useCallback(
    (event: AnimationEvent<HTMLElement>) => {
      if (endsExit(shown, event.target, event.currentTarget)) setPhase((p) => presenceStep(p, "done"));
    },
    [shown],
  );
  return { mounted: shown !== "closed", phase: shown, onAnimationEnd };
}

export function usePresentNode(show: boolean, build: (phase: Phase, onAnimationEnd: (event: AnimationEvent<HTMLElement>) => void) => ReactNode): ReactNode {
  const { mounted, phase, onAnimationEnd } = usePresence(show);
  const last = useRef(build);
  if (show) last.current = build;
  return mounted ? last.current(phase, onAnimationEnd) : null;
}
