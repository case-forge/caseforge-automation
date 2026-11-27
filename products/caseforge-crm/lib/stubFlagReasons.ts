
const reasons = new Map<string, Record<string, string>>();

export function stubFlagReasons(matterId: string): Record<string, string> {
  return { ...(reasons.get(matterId) ?? {}) };
}

export function applyStubFlagRule(
  matterId: string,
  flagName: string,
  isSet: boolean,
  wasSet: boolean,
  reason: string,
  onlyIfReason: string,
): boolean {
  const current = reasons.get(matterId)?.[flagName] ?? "";
  if (reason && isSet && wasSet) return false;
  if (onlyIfReason && !isSet && (!wasSet || current !== onlyIfReason)) return false;
  const next = { ...(reasons.get(matterId) ?? {}) };
  if (isSet && reason) next[flagName] = reason;
  else delete next[flagName];
  reasons.set(matterId, next);
  return true;
}
