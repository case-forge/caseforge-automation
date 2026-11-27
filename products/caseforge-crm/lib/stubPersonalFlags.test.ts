import { describe, expect, it } from "vitest";
import { stubFlagCounts, stubFlagKinds, stubFlaggedMatters, stubListFlags, stubSetFlag, stubRaiseAutomaticFlag, STUB_DRAFT_REASON } from "./stub";
import { DEFAULT_STUB_USER, stubUserFor } from "./stubUser";
import { flagButtonLabel, NO_KINDS } from "../components/HeaderFlagToggles";

const tick = (user: string, matterId: string, flagName: string, isSet: boolean, extra: { reason?: string; onlyIfReason?: string; scope?: string } = {}) =>
  stubSetFlag({ matterId, flagName, isSet, setBy: "Typed", user, ...extra });

describe("stub Flag and Star are personal", () => {
  it("keeps one person's star out of another's flags, counts and lists", () => {
    tick("anna@example.test", "9001", "starred", true);
    expect(stubListFlags("9001", "anna@example.test").starred).toBe(true);
    expect(stubListFlags("9001", "ben@example.test").starred).toBeUndefined();
    expect(stubFlagCounts(["starred"], "anna@example.test").starred).toBeGreaterThanOrEqual(1);
    expect(stubFlagCounts(["starred"], "ben@example.test").starred).toBe(0);
    expect(stubFlaggedMatters(["starred"], "ben@example.test").results).toEqual([]);
    expect(Object.keys(stubFlaggedMatters(["starred"], "anna@example.test").flags_by_matter)).toContain("9001");
  });

  it("keeps an own flag's reason private and beside the shared automatic flag", () => {
    stubRaiseAutomaticFlag("9002", "Client complaint to deal with");
    expect(stubFlagKinds("9002", "ben@example.test").shared).toEqual({ flagged: true });
    tick("anna@example.test", "9002", "flagged", true, { reason: "Chase the court" });
    expect(stubFlagKinds("9002", "anna@example.test")).toMatchObject({ shared: { flagged: true }, personal: { flagged: true }, personal_reasons: { flagged: "Chase the court" } });
    expect(stubFlagKinds("9002", "ben@example.test").personal).toEqual({});

    tick("ben@example.test", "9002", "flagged", false, { scope: "shared" });
    expect(stubFlagKinds("9002", "anna@example.test")).toMatchObject({ shared: {}, personal: { flagged: true } });
    tick("anna@example.test", "9002", "flagged", false);
    expect(stubFlagKinds("9002", "anna@example.test").personal).toEqual({});
  });

  it("allows an own flag with no reason, and it is not an automatic one", () => {
    tick("anna@example.test", "9005", "flagged", true);
    expect(stubFlagKinds("9005", "anna@example.test")).toMatchObject({ shared: {}, personal: { flagged: true }, personal_reasons: {} });
    expect(stubFlagKinds("9005", "ben@example.test").shared).toEqual({});
  });

  it("makes the draft flag the person's own and clears only that", () => {
    tick("anna@example.test", "9003", "flagged", true, { reason: STUB_DRAFT_REASON });
    expect(stubFlagKinds("9003", "ben@example.test").personal).toEqual({});
    tick("anna@example.test", "9003", "flagged", false, { onlyIfReason: STUB_DRAFT_REASON });
    expect(stubFlagKinds("9003", "anna@example.test").personal).toEqual({});
  });

  it("names the stub person from a cookie, else the default", () => {
    const req = (cookie?: string) => ({ headers: new Headers(cookie ? { cookie } : {}) });
    expect(stubUserFor(req("a=1; stub_user=Ben%40Example.test"), null)).toBe("ben@example.test");
    expect(stubUserFor(req(), null)).toBe(DEFAULT_STUB_USER);
    expect(stubUserFor(req("stub_user=ben"), "Anna@Example.test")).toBe("anna@example.test");
  });
});

describe("the flag button's accessible name", () => {
  it("says which kind is set", () => {
    expect(flagButtonLabel(NO_KINDS, "")).toBe("Flag this client");
    expect(flagButtonLabel({ shared: { flagged: true }, personal: {}, personalReasons: {} }, "Client complaint")).toBe(
      "Automatic flag: Client complaint. Press to clear it for everyone",
    );
    expect(flagButtonLabel({ shared: {}, personal: { flagged: true }, personalReasons: { flagged: "Chase" } }, "")).toBe("Your flag: Chase");
    expect(flagButtonLabel({ shared: {}, personal: { flagged: true }, personalReasons: {} }, "")).toBe("Your flag");
    expect(flagButtonLabel({ shared: { flagged: true }, personal: { flagged: true }, personalReasons: { flagged: "Chase" } }, "Complaint")).toBe(
      "Automatic flag: Complaint. Your flag: Chase",
    );
  });
});
