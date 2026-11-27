import { describe, expect, it } from "vitest";
import { NETWORK_FAILURE_MESSAGE, describeFetchError, isNetworkFailure } from "./networkError";

describe("networkError", () => {
  it("recognises the browsers' dropped-call errors", () => {
    expect(isNetworkFailure(new TypeError("Failed to fetch"))).toBe(true);
    expect(isNetworkFailure(new TypeError("Load failed"))).toBe(true);
    expect(isNetworkFailure(new TypeError("NetworkError when attempting to fetch resource."))).toBe(true);
  });
  it("does not treat the hub's own reasons as network failures", () => {
    expect(isNetworkFailure(new Error("Failed to fetch"))).toBe(false);
    expect(describeFetchError(new Error("Name is required"), "x")).toBe("Name is required");
  });
  it("explains a dropped call in plain words and falls back otherwise", () => {
    expect(describeFetchError(new TypeError("Failed to fetch"), "x")).toBe(NETWORK_FAILURE_MESSAGE);
    expect(describeFetchError("odd", "Could not apply the changes")).toBe("Could not apply the changes");
  });
});
