
export const REFRESH_AFTER_MS = 12 * 60 * 60_000;

export const IDLE_BEFORE_REFRESH_MS = 10 * 60_000;

export const REFRESH_CHECK_MS = 5 * 60_000;

export interface RefreshFacts {

  ageMs: number;

  idleMs: number;

  unsaved: number;

  newBuild: boolean;
}

export function shouldRefresh(facts: RefreshFacts): boolean {
  if (facts.unsaved > 0) return false;
  if (facts.idleMs < IDLE_BEFORE_REFRESH_MS) return false;
  return facts.newBuild || facts.ageMs >= REFRESH_AFTER_MS;
}
