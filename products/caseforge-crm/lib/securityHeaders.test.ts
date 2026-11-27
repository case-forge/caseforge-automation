import { describe, expect, it } from "vitest";
import { baseHeaders, contentSecurityPolicy } from "./securityHeaders";

describe("contentSecurityPolicy", () => {
  const csp = contentSecurityPolicy({ dev: false });

  it("allows only this origin by default and forbids plugins and foreign framing", () => {
    for (const part of ["default-src 'self'", "object-src 'none'", "frame-ancestors 'self'", "base-uri 'self'", "form-action 'self'"]) {
      expect(csp).toContain(part);
    }
    expect(csp).not.toMatch(/https?:\/\//);
    expect(csp).not.toContain("unsafe-eval");
  });

  it("allows eval only in development, and needs no external origin for error reports (they go through /api/glitchtip-tunnel)", () => {
    expect(contentSecurityPolicy({ dev: true })).toContain("'unsafe-eval'");
    expect(csp).toContain("connect-src 'self';");
  });

  it("adds the analytics origin, and only that, when it is configured", () => {
    const withAnalytics = contentSecurityPolicy({ dev: false, analyticsUrl: "https://stats.example.invalid/script.js" });
    expect(withAnalytics).toContain("connect-src 'self' https://stats.example.invalid;");
    expect(withAnalytics).toContain("script-src 'self' 'unsafe-inline' https://stats.example.invalid;");
    expect(contentSecurityPolicy({ dev: false, analyticsUrl: "not a url" })).toContain("connect-src 'self';");
  });
});

describe("baseHeaders", () => {
  it("sets nosniff, a referrer policy and same-origin framing", () => {
    const map = Object.fromEntries(baseHeaders.map((h) => [h.key, h.value]));
    expect(map["X-Content-Type-Options"]).toBe("nosniff");
    expect(map["Referrer-Policy"]).toBe("same-origin");
    expect(map["X-Frame-Options"]).toBe("SAMEORIGIN");
  });
});
