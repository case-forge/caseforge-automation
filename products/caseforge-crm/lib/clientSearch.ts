
import { PROBE_INIT, classifyResponse } from "./sessionProbe";
import type { ClientSearchResponse } from "./types";

export const SESSION_EXPIRED_MESSAGE = "Your session has expired - please reload the page.";

export const UNREACHABLE_MESSAGE = "Could not reach the server. Wait a moment and try again.";

type FetchLike = (input: string, init?: { signal?: AbortSignal; redirect?: RequestRedirect }) => Promise<Response>;

export function clientSearchUrl(query: string, limit: number): string {
  return `/api/clients/search?q=${encodeURIComponent(query.trim())}&limit=${limit}`;
}

export async function fetchClientSearch(
  query: string,
  limit: number,
  signal?: AbortSignal,
  fetchImpl: FetchLike = fetch,
): Promise<ClientSearchResponse> {
  const res = await fetchImpl(clientSearchUrl(query, limit), { signal, ...PROBE_INIT });

  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const probe = await classifyResponse(res);
    throw new Error(probe === "access-expired" ? SESSION_EXPIRED_MESSAGE : UNREACHABLE_MESSAGE);
  }
  const body = (await res.json()) as ClientSearchResponse | { error: string };
  if (!res.ok) {
    throw new Error("error" in body ? body.error : "Search failed");
  }
  return body as ClientSearchResponse;
}

export function looksLikeStaleSession(err: unknown): boolean {
  return err instanceof Error && err.message === SESSION_EXPIRED_MESSAGE;
}

export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}
