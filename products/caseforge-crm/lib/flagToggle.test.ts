import { describe, expect, it } from "vitest";
import { runFlagToggle } from "./flagToggle";

function setup(post: () => Promise<{ flags?: Record<string, boolean>; reasons?: Record<string, string> }>, open = () => true) {
  const calls: Array<{ flags: Record<string, boolean>; settled: boolean }> = [];
  const run = () =>
    runFlagToggle({
      flags: { flagged: false },
      reasons: {},
      flagName: "starred",
      next: true,
      post,
      apply: (flags, _reasons, settled) => calls.push({ flags, settled }),
      getCurrent: () => ({ flags: calls.length ? calls[calls.length - 1].flags : { flagged: false }, reasons: {} }),
      isStillOpen: open,
    });
  return { calls, run };
}

describe("runFlagToggle", () => {
  it("shows the change before the server has answered", async () => {
    let release: (v: { flags: Record<string, boolean> }) => void = () => {};
    const { calls, run } = setup(() => new Promise((resolve) => (release = resolve)));
    const pending = run();
    expect(calls).toEqual([{ flags: { flagged: false, starred: true }, settled: false }]);
    release({ flags: { flagged: false, starred: true } });
    expect(await pending).toBeNull();
    expect(calls[1]).toEqual({ flags: { flagged: false, starred: true }, settled: true });
  });

  it("puts the old state back and reports the error when the server refuses", async () => {
    const { calls, run } = setup(() => Promise.reject(new Error("Could not update that flag")));
    expect(await run()).toBe("Could not update that flag");
    expect(calls.at(-1)).toEqual({ flags: { flagged: false, starred: false }, settled: true });
  });

  it("does not write a late answer onto a different matter", async () => {
    const { calls, run } = setup(() => Promise.resolve({ flags: { starred: true } }), () => false);
    await run();
    expect(calls).toHaveLength(1);
  });

  it("rolls back only its own flag when another toggle has changed meanwhile", async () => {
    const state = { flags: { flagged: false, starred: false } as Record<string, boolean> };
    const apply = (flags: Record<string, boolean>) => {
      state.flags = flags;
    };
    const getCurrent = () => ({ flags: state.flags, reasons: {} });
    let failFlag: (e: Error) => void = () => {};
    const flagRun = runFlagToggle({
      flags: { ...state.flags },
      reasons: {},
      flagName: "flagged",
      next: true,
      post: () => new Promise((_, reject) => (failFlag = reject)),
      apply,
      getCurrent,
      isStillOpen: () => true,
    });
    const starRun = runFlagToggle({
      flags: { ...state.flags },
      reasons: {},
      flagName: "starred",
      next: true,
      post: async () => ({ flags: { flagged: false, starred: true } }),
      apply,
      getCurrent,
      isStillOpen: () => true,
    });
    await starRun;
    failFlag(new Error("down"));
    await flagRun;
    expect(state.flags).toEqual({ flagged: false, starred: true });
  });

  it("restores both flags when both fail, whichever fails first", async () => {
    const state = { flags: { flagged: false, starred: false } as Record<string, boolean> };
    const apply = (flags: Record<string, boolean>) => {
      state.flags = flags;
    };
    const getCurrent = () => ({ flags: state.flags, reasons: {} });
    const rejecters: Record<string, (e: Error) => void> = {};
    const start = (flagName: string) =>
      runFlagToggle({
        flags: { ...state.flags },
        reasons: {},
        flagName,
        next: true,
        post: () => new Promise((_, reject) => (rejecters[flagName] = reject)),
        apply,
        getCurrent,
        isStillOpen: () => true,
      });
    const a = start("flagged");
    const b = start("starred");
    rejecters.flagged(new Error("down"));
    await a;
    rejecters.starred(new Error("down"));
    await b;
    expect(state.flags).toEqual({ flagged: false, starred: false });
  });
});
