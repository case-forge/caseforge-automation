
import type { HearingFormValues, HearingMode } from "./hearings";
import { HEARING_MODES } from "./hearings";
import type { DetectedHearing } from "./hearingDetection";

export interface HearingExtract {
  court: string;
  hearing_type: string;
  counsel: string;
  chambers: string;
  mode: HearingMode;
  time: string | null;
  without_notice: boolean;
  notes: string;
}

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

function str(value: unknown, limit = 200): string {
  return typeof value === "string" ? value.trim().slice(0, limit) : "";
}

export function cleanExtract(raw: unknown): HearingExtract {
  const r = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const mode = str(r.mode, 20) as HearingMode;
  const time = typeof r.time === "string" && TIME_RE.test(r.time) ? r.time : null;
  return {
    court: str(r.court),
    hearing_type: str(r.hearing_type),
    counsel: str(r.counsel),
    chambers: str(r.chambers),
    mode: HEARING_MODES.some((m) => m.value === mode) ? mode : "",
    time,
    without_notice: r.without_notice === true,
    notes: str(r.notes, 500),
  };
}

export function hearingDefaults(
  found: DetectedHearing,
  extract: HearingExtract | null,
  client: { matterId: string; caseRef: string; name: string; role: string },
): Partial<HearingFormValues> {
  const e = extract ?? cleanExtract(null);
  return {
    matter_id: client.matterId,
    case_ref: client.caseRef,
    hearing_date: found.date,
    hearing_time: found.time ?? e.time ?? "",
    court: e.court || found.court,
    hearing_type: e.hearing_type,
    notice: e.without_notice ? "without notice" : "",
    counsel: e.counsel,
    chambers: e.chambers,
    mode: e.mode,
    notes: e.notes,
    applicant: client.role === "Applicant" ? client.name : "",
    respondent: client.role === "Respondent" ? client.name : "",
  };
}
