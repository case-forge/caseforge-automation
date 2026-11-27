
import type { OpsHealthAlert, OpsHealthResponse } from "./opsHealth";

export const STUB_OPS_HEALTH_COOKIE = "caseforge_stub_ops_health";
export const STUB_OPS_HEALTH_STATES = ["clear", "amber", "red", "stale", "none", "nonadmin"] as const;
export type StubOpsHealthState = (typeof STUB_OPS_HEALTH_STATES)[number];

const HOUSEKEEPING: OpsHealthAlert[] = [
  {
    severity: "amber",
    category: "housekeeping",
    title: "Hearings waiting for review",
    next_action: "Open Calendar in the client viewer, go to Needs review, and confirm, correct or dismiss them.",
    kind: "backlog",
    age_minutes: null,
  },
  {
    severity: "info",
    category: "housekeeping",
    title: "2 chase to-do(s) open: no reply from court 2",
    next_action: "Work through them from the Today screen.",
    kind: "state",
    age_minutes: null,
  },
];

const AMBER: OpsHealthAlert[] = [
  {
    severity: "amber",
    category: "health",
    title: "Tunnel health report is stale",
    next_action: "Check the tunnel health timer on this box has run recently.",
    kind: "state",
    age_minutes: 95,
  },
  {
    severity: "info",
    category: "health",
    title: "Mail intake has items waiting for a person",
    next_action: "Review the blocked queue by reason, then add rules only where the pattern is repeatable.",
    kind: "state",
    age_minutes: null,
  },
];

const RED: OpsHealthAlert = {
  severity: "red",
  category: "health",
  title: "Background workers are failing",
  next_action: "Check the worker service's log for the error and restart it once the cause is fixed.",
  kind: "state",
  age_minutes: 40,
};

function minutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

export function stubOpsHealth(state: string | undefined): OpsHealthResponse | null {
  const pick = (STUB_OPS_HEALTH_STATES as readonly string[]).includes(state ?? "") ? (state as StubOpsHealthState) : "amber";
  const base = { available: true, generated_at: minutesAgo(6), snapshot_age_minutes: 6, stale: false };
  switch (pick) {
    case "nonadmin":
      return null;
    case "none":
      return { available: false, generated_at: "", snapshot_age_minutes: null, stale: true, overall_severity: "unknown", housekeeping_severity: "unknown", alerts: [] };
    case "clear":
      return { ...base, overall_severity: "green", housekeeping_severity: "green", alerts: [] };
    case "red":
      return { ...base, overall_severity: "red", housekeeping_severity: "amber", alerts: [RED, ...AMBER, ...HOUSEKEEPING] };
    case "stale":
      return {
        ...base,
        generated_at: minutesAgo(190),
        snapshot_age_minutes: 190,
        stale: true,
        overall_severity: "green",
        housekeeping_severity: "amber",
        alerts: HOUSEKEEPING,
      };
    default:
      return { ...base, overall_severity: "amber", housekeeping_severity: "amber", alerts: [...AMBER, ...HOUSEKEEPING] };
  }
}
