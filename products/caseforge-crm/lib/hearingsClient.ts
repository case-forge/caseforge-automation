
import { hearingsQuery } from "./hearings";
import type {
  HearingEdits,
  HearingHistoryResponse,
  HearingLeadResponse,
  HearingLeadsResponse,
  HearingLinkResponse,
  MatterSuggestionsResponse,
  HearingResponse,
  HearingsResponse,
  HearingsReviewResponse,
  HearingStatus,
} from "./hearings";
import { vacateBody } from "./hearingActions";
import type { CourtRequestResponse, MoveInput, RequestKind, RequestOptions, VacateChoice, VacateResponse } from "./hearingActions";
import { markSessionStale } from "./sessionStale";
import { PROBE_INIT, classifyResponse } from "./sessionProbe";
import type { ClientSearchResponse } from "./types";

const UNREACHABLE_MESSAGE = "Could not reach the server. Wait a moment and try again; if it keeps happening, reload the page.";
const SESSION_MESSAGE = "Your session has expired - please reload the page.";

export function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

async function readJson<T>(res: Response): Promise<T> {
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    if ((await classifyResponse(res)) === "access-expired") {
      markSessionStale();
      throw new Error(SESSION_MESSAGE);
    }
    throw new Error(UNREACHABLE_MESSAGE);
  }
  const body = (await res.json()) as T | { error?: string };
  if (!res.ok) {
    const message = (body as { error?: string }).error;
    throw new Error(message || `Request failed (${res.status})`);
  }
  return body as T;
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, { ...init, ...PROBE_INIT });
  } catch (err) {
    if (isAbort(err)) throw err;

    throw new Error(UNREACHABLE_MESSAGE);
  }
  return readJson<T>(res);
}

function postJson<T>(url: string, body: unknown): Promise<T> {
  return call<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchHearings(from: string, to: string, signal?: AbortSignal, matterId?: string | number): Promise<HearingsResponse> {
  return call<HearingsResponse>(`/api/hearings?${hearingsQuery(from, to, matterId)}`, { signal });
}

export function fetchReviewQueue(signal?: AbortSignal): Promise<HearingsReviewResponse> {
  return call<HearingsReviewResponse>("/api/hearings/review", { signal });
}

export function fetchLeads(signal?: AbortSignal): Promise<HearingLeadsResponse> {
  return call<HearingLeadsResponse>("/api/hearings/leads", { signal });
}

export function resolveLead(leadId: number, action: "done" | "dismissed"): Promise<HearingLeadResponse> {
  return postJson<HearingLeadResponse>("/api/hearings/leads/resolve", { lead_id: leadId, action });
}

export function fetchHearingHistory(hearingId: number, signal?: AbortSignal): Promise<HearingHistoryResponse> {
  return call<HearingHistoryResponse>(`/api/hearings/history?hearing_id=${hearingId}`, { signal });
}

export function searchClients(query: string, signal?: AbortSignal): Promise<ClientSearchResponse> {
  return call<ClientSearchResponse>(`/api/clients/search?q=${encodeURIComponent(query)}&limit=8`, { signal });
}

export function fetchMatterSuggestions(hearingId: number, signal?: AbortSignal): Promise<MatterSuggestionsResponse> {
  return call<MatterSuggestionsResponse>(`/api/hearings/suggest-matters?hearing_id=${hearingId}`, { signal });
}

export function linkHearing(hearingId: number, matterId: number): Promise<HearingLinkResponse> {
  return postJson<HearingLinkResponse>("/api/hearings/link", { hearing_id: hearingId, matter_id: matterId });
}

export function unlinkHearing(hearingId: number): Promise<HearingResponse> {
  return postJson<HearingResponse>("/api/hearings/unlink", { hearing_id: hearingId });
}

export function createHearing(fields: HearingEdits): Promise<HearingResponse> {
  return postJson<HearingResponse>("/api/hearings", { ...fields });
}

export function updateHearing(hearingId: number, edits: HearingEdits, note?: string): Promise<HearingResponse> {
  return postJson<HearingResponse>("/api/hearings/update", {
    hearing_id: hearingId,
    edits,
    ...(note ? { note } : {}),
  });
}

export function setHearingStatus(hearingId: number, status: HearingStatus, note?: string): Promise<HearingResponse> {
  return postJson<HearingResponse>("/api/hearings/status", {
    hearing_id: hearingId,
    status,
    ...(note ? { note } : {}),
  });
}

export function vacateHearing(
  hearingId: number,
  kind: VacateChoice,
  reason: string,
  move?: MoveInput,
): Promise<VacateResponse> {
  return postJson<VacateResponse>("/api/hearings/vacate", vacateBody(hearingId, kind, reason, move));
}

export function fetchRequestOptions(hearingId: number, signal?: AbortSignal): Promise<RequestOptions> {
  return call<RequestOptions>(`/api/hearings/request-options?hearing_id=${hearingId}`, { signal });
}

export function requestFromCourt(
  hearingId: number,
  kind: RequestKind,
  reasons: string[],
  form: string,
): Promise<CourtRequestResponse> {
  return postJson<CourtRequestResponse>("/api/hearings/request", {
    hearing_id: hearingId,
    kind,
    reasons,
    ...(form ? { form } : {}),
  });
}

export function courtDecision(hearingId: number, agreed: boolean): Promise<HearingResponse> {
  return postJson<HearingResponse>("/api/hearings/court-decision", { hearing_id: hearingId, agreed });
}

export function resolveReview(
  hearingId: number,
  action: "confirm" | "dismiss",
  edits?: HearingEdits,
): Promise<HearingResponse> {
  return postJson<HearingResponse>("/api/hearings/review-resolve", {
    hearing_id: hearingId,
    action,
    ...(edits && Object.keys(edits).length ? { edits } : {}),
  });
}
