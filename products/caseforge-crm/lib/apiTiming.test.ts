import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { logLine, routePattern, serverTimingValue } from "@/lib/apiTiming";

describe("apiTiming", () => {
  let info: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    info = vi.spyOn(console, "info").mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("collapses id segments and drops the query", () => {
    expect(routePattern("/api/clients/12345/notes?q=Smith")).toBe("/api/clients/:id/notes");
    expect(routePattern("/api/today")).toBe("/api/today");
  });

  it("formats the header with identity and hub as separate entries", () => {
    expect(serverTimingValue({ identityMs: 1.24, hubMs: 30, totalMs: 32 })).toBe(
      "identity;dur=1.2, hub;dur=30, total;dur=32",
    );
  });

  it("formats the log line with only route, status and milliseconds", () => {
    expect(logLine("/api/today", 200, { identityMs: 1, hubMs: 2, totalMs: 4 })).toBe(
      "[api-timing] route=/api/today status=200 total_ms=4 identity_ms=1 hub_ms=2",
    );
  });
});
