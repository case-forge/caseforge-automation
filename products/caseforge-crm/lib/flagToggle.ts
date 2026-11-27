export type Flags = Record<string, boolean>;
export type Reasons = Record<string, string>;

export interface FlagToggleDeps {
  flags: Flags;
  reasons: Reasons;
  flagName: string;
  next: boolean;

  post: () => Promise<{ flags?: Flags; reasons?: Reasons }>;

  apply: (flags: Flags, reasons: Reasons, settled: boolean) => void;

  getCurrent: () => { flags: Flags; reasons: Reasons };

  isStillOpen: () => boolean;
}

export async function runFlagToggle(deps: FlagToggleDeps): Promise<string | null> {
  const { flags, reasons, flagName, next, post, apply, getCurrent, isStillOpen } = deps;
  apply({ ...flags, [flagName]: next }, reasons, false);
  try {
    const body = await post();
    if (isStillOpen()) apply(body.flags ?? {}, body.reasons ?? {}, true);
    return null;
  } catch (err) {
    if (isStillOpen()) {
      const current = getCurrent();
      apply({ ...current.flags, [flagName]: flags[flagName] ?? false }, current.reasons, true);
    }
    return err instanceof Error ? err.message : "Could not update that flag";
  }
}
