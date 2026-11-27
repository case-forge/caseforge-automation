import { describe, expect, it, vi } from "vitest";
import { SESSION_EXPIRED_MESSAGE, clientSearchUrl, fetchClientSearch, isAbortError, looksLikeStaleSession } from "./clientSearch";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("fetchClientSearch", () => {
  it("calls the same-origin route with the trimmed query and the limit", async () => {
    const fetchImpl = vi.fn(async () => json({ query: "ab", resolved_query: "ab", source: "stub", count: 0, results: [] }));
    await fetchClientSearch("  a b ", 8, undefined, fetchImpl);
    expect(fetchImpl).toHaveBeenCalledWith("/api/clients/search?q=a%20b&limit=8", { signal: undefined, redirect: "manual" });
    expect(clientSearchUrl("x&y", 20)).toBe("/api/clients/search?q=x%26y&limit=20");
  });

  it("returns the body on success", async () => {
    const body = { query: "ab", resolved_query: "ab", source: "stub", count: 1, results: [{ matter_id: 1, extra: {} }] };
    await expect(fetchClientSearch("ab", 8, undefined, async () => json(body))).resolves.toEqual(body);
  });

  it("says the session has expired when an HTML login page comes back", async () => {
    const html = async () =>
      new Response("<html>cloudflareaccess.com</html>", { status: 401, headers: { "content-type": "text/html" } });
    await expect(fetchClientSearch("ab", 8, undefined, html)).rejects.toThrow(SESSION_EXPIRED_MESSAGE);
  });

  it("does not say expired for a gateway page or other HTML", async () => {
    const html = async () => new Response("<h1>Bad gateway</h1>", { status: 502, headers: { "content-type": "text/html" } });
    await expect(fetchClientSearch("ab", 8, undefined, html)).rejects.toThrow("Could not reach the server");
  });

  it("passes the route's own error wording on", async () => {
    await expect(fetchClientSearch("ab", 8, undefined, async () => json({ error: "upstream request failed" }, 502))).rejects.toThrow(
      "upstream request failed",
    );
  });

  it("blames the session only for an Access login, not for a readable route error", () => {
    expect(looksLikeStaleSession(new Error(SESSION_EXPIRED_MESSAGE))).toBe(true);
    expect(looksLikeStaleSession(new TypeError("Failed to fetch"))).toBe(false);
    expect(looksLikeStaleSession(new Error("upstream request failed"))).toBe(false);
  });

  it("tells a cancelled search from a failed one", () => {
    expect(isAbortError(new DOMException("stop", "AbortError"))).toBe(true);
    expect(isAbortError(new Error("nope"))).toBe(false);
  });
});
