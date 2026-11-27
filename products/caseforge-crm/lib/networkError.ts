
export const NETWORK_FAILURE_MESSAGE =
  "Could not reach the server (it may have just been updated, or the connection dropped). Nothing was changed and your typing is kept. Wait a few seconds and try again; if it keeps happening, refresh the page.";

export function isNetworkFailure(err: unknown): boolean {
  if (!(err instanceof TypeError)) return false;
  return /failed to fetch|load failed|networkerror|network request failed|fetch failed/i.test(err.message);
}

export function describeFetchError(err: unknown, fallback: string): string {
  if (isNetworkFailure(err)) return NETWORK_FAILURE_MESSAGE;
  return err instanceof Error && err.message ? err.message : fallback;
}
