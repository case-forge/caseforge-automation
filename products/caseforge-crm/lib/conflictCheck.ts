"use client";

import { useEffect, useState } from "react";
import type { CaseReviewAnswer } from "./caseReviewTypes";

export type MatchStrength = "strong" | "possible" | "weak";

export interface ConflictMatch {
  direction: "client_is_opponent" | "opponent_is_client";
  strength: MatchStrength;
  reasons: string[];
  this_is: string;
  that_is: string;
  other_name: string;
  other_matter_id: string;
  other_reference: string;
  other_client: string;
  other_closed: boolean;
}

export interface ConflictCheck {
  matter_id: string;
  run: boolean;
  run_utc: string;
  run_by: string;
  stale: boolean;
  verdict: "review" | "weak" | "clear" | "";
  matches: ConflictMatch[];
  held_back: number;
  parties_checked: number;
  compared: Record<string, number>;
  gaps: string[];
}

export const CONFLICT_ROWS = ["r_opening_conflict", "s_conflict"] as const;

export type NoticeLevel = "alert" | "warn" | "info";

export interface ConflictNotice {
  level: NoticeLevel;
  headline: string;
  lines: string[];
}

export function markedCleared(answers: Record<string, CaseReviewAnswer>): boolean {
  return CONFLICT_ROWS.some((key) => answers[key]?.value === "yes");
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function conflictNotice(check: ConflictCheck | null, answers: Record<string, CaseReviewAnswer>): ConflictNotice | null {
  if (!check) return null;
  const cleared = markedCleared(answers);
  if (!check.run) {
    return {
      level: cleared ? "alert" : "warn",
      headline: "No conflict check has been run for this client.",
      lines: cleared ? ["The forms already say the conflict check is cleared. Run the check so that answer has something behind it."] : [],
    };
  }
  const lines: string[] = [];
  const reviewable = check.matches.filter((m) => m.strength !== "weak").length;
  if (check.stale) lines.push("The people recorded on this matter have changed since this check was run. Run it again.");
  if (check.verdict === "review") {
    if (cleared) lines.push("The forms say the conflict check is cleared while possible matches are listed. Read each one, or change the answer.");
    return {
      level: "alert",
      headline: `${plural(reviewable, "possible match", "possible matches")} to read before the conflict row is answered.`,
      lines: [...lines, ...check.gaps],
    };
  }
  if (check.stale) return { level: "warn", headline: "This check is out of date.", lines: [...lines, ...check.gaps] };
  if (check.verdict === "weak") {
    return {
      level: "info",
      headline: `${plural(check.matches.length, "weak match", "weak matches")}: a similar name only. Probably someone else, worth a look.`,
      lines: check.gaps,
    };
  }
  return { level: check.gaps.length ? "warn" : "info", headline: "No matches found.", lines: check.gaps };
}

async function readError(res: Response, fallback: string): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(typeof body?.error === "string" && body.error ? body.error : fallback);
}

export async function fetchConflictCheck(matterId: string): Promise<ConflictCheck> {
  const res = await fetch(`/api/conflict-check?${new URLSearchParams({ matter_id: matterId })}`, { cache: "no-store" });
  if (!res.ok) return readError(res, "Could not load the conflict check.");
  return res.json();
}

export async function runConflictCheck(matterId: string): Promise<ConflictCheck> {
  const res = await fetch("/api/conflict-check/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId }),
  });
  if (!res.ok) return readError(res, "The conflict check could not be run.");
  return res.json();
}

export function useConflictCheck(matterId: string): {
  check: ConflictCheck | null;
  error: string;
  setCheck: (c: ConflictCheck) => void;
  setError: (e: string) => void;
} {
  const [check, setCheck] = useState<ConflictCheck | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchConflictCheck(matterId)
      .then((c) => {
        if (!cancelled) {
          setCheck(c);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the conflict check.");
      });
    return () => {
      cancelled = true;
    };
  }, [matterId]);

  return { check, error, setCheck, setError };
}
