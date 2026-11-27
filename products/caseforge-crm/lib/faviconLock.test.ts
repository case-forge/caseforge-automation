import { describe, expect, it } from "vitest";
import { readStoredFaviconLock } from "./faviconLock";

describe("favicon lock", () => {
  it("is a lock only for a colour we ship", () => {
    expect(readStoredFaviconLock("white")).toBe("white");
    expect(readStoredFaviconLock("black")).toBe("black");
    expect(readStoredFaviconLock("red")).toBeNull();
    expect(readStoredFaviconLock(null)).toBeNull();
  });
});
