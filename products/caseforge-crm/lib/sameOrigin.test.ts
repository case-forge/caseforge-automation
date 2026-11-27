import { describe, expect, it } from "vitest";
import { refuseCrossSiteWrite } from "./sameOrigin";

function req(method: string, secFetchSite?: string): Request {
  return new Request("http://viewer.example.invalid/api/todos", {
    method,
    headers: secFetchSite === undefined ? {} : { "Sec-Fetch-Site": secFetchSite },
  });
}

describe("refuseCrossSiteWrite", () => {
  it.each(["POST", "PUT", "PATCH", "DELETE"])("refuses a cross-site and same-site %s", async (method) => {
    for (const site of ["cross-site", "same-site"]) {
      const response = refuseCrossSiteWrite(req(method, site));
      expect(response?.status).toBe(403);
      expect(await response?.json()).toEqual({ error: "Cross-site request refused." });
    }
  });

  it.each(["POST", "PUT", "PATCH", "DELETE"])("lets a same-origin %s through", (method) => {
    expect(refuseCrossSiteWrite(req(method, "same-origin"))).toBeNull();
  });

  it("lets a non-browser caller (no Sec-Fetch-Site) and a user-initiated one (none) through", () => {
    expect(refuseCrossSiteWrite(req("POST"))).toBeNull();
    expect(refuseCrossSiteWrite(req("POST", "none"))).toBeNull();
  });

  it("never blocks reads, whatever the site", () => {
    for (const method of ["GET", "HEAD", "OPTIONS"]) expect(refuseCrossSiteWrite(req(method, "cross-site"))).toBeNull();
  });
});
