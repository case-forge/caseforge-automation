import { describe, expect, it } from "vitest";
import { accessConfigProblem } from "./accessIdentity";
import { refuseCrossSiteWrite } from "./writeGuard";

const post = (headers: Record<string, string>, method = "POST") =>
  new Request("http://crm.test/api/x", { method, headers, body: method === "DELETE" ? undefined : "{}" });
const JSON_TYPE = { "Content-Type": "application/json" };

describe("refuseCrossSiteWrite", () => {
  it("lets a same-origin JSON write through", () => {
    expect(refuseCrossSiteWrite(post({ ...JSON_TYPE, "Sec-Fetch-Site": "same-origin" }))).toBeNull();
    expect(refuseCrossSiteWrite(post({ ...JSON_TYPE, "Sec-Fetch-Site": "none" }))).toBeNull();
  });

  it("lets a script with no browser headers through", () => {
    expect(refuseCrossSiteWrite(post(JSON_TYPE))).toBeNull();
  });

  it("refuses same-site and cross-site fetches with 403", () => {
    expect(refuseCrossSiteWrite(post({ ...JSON_TYPE, "Sec-Fetch-Site": "cross-site" }))?.status).toBe(403);
    expect(refuseCrossSiteWrite(post({ ...JSON_TYPE, "Sec-Fetch-Site": "same-site" }))?.status).toBe(403);
  });

  it("falls back to Origin against Host when Sec-Fetch-Site is absent", () => {
    expect(refuseCrossSiteWrite(post({ ...JSON_TYPE, Origin: "https://crm.test", Host: "crm.test" }))).toBeNull();
    expect(refuseCrossSiteWrite(post({ ...JSON_TYPE, Origin: "https://attacker.example", Host: "crm.test" }))?.status).toBe(403);
    expect(refuseCrossSiteWrite(post({ ...JSON_TYPE, Origin: "not a url", Host: "crm.test" }))?.status).toBe(403);
  });

  it("refuses a body that is not declared JSON with 415, unless the route opts out", () => {
    expect(refuseCrossSiteWrite(post({ "Content-Type": "text/plain" }))?.status).toBe(415);
    expect(refuseCrossSiteWrite(post({ "Content-Type": "application/json; charset=utf-8" }))).toBeNull();
    expect(refuseCrossSiteWrite(post({ "Content-Type": "image/png" }), { json: false })).toBeNull();
  });

  it("does not ask a DELETE for a content type", () => {
    expect(refuseCrossSiteWrite(post({}, "DELETE"))).toBeNull();
  });
});

describe("accessConfigProblem", () => {
  const prod = { NODE_ENV: "production", CASEFORGE_HUB_API_URL: "http://127.0.0.1:8771" } as unknown as NodeJS.ProcessEnv;

  it("refuses a production start on the live hub without both Access values", () => {
    expect(accessConfigProblem(prod)).toMatch(/CASEFORGE_CF_ACCESS/);
    expect(accessConfigProblem({ ...prod, CASEFORGE_CF_ACCESS_TEAM_DOMAIN: "team.example.test" })).toMatch(/CASEFORGE_CF_ACCESS/);
  });

  it("accepts both values, the stub, no hub, development and the build phase", () => {
    expect(accessConfigProblem({ ...prod, CASEFORGE_CF_ACCESS_TEAM_DOMAIN: "t", CASEFORGE_CF_ACCESS_AUD: "a" })).toBeNull();
    expect(accessConfigProblem({ ...prod, CASEFORGE_HUB_API_STUB: "1" })).toBeNull();
    expect(accessConfigProblem({ NODE_ENV: "production" } as unknown as NodeJS.ProcessEnv)).toBeNull();
    expect(accessConfigProblem({ ...prod, NODE_ENV: "development" })).toBeNull();
    expect(accessConfigProblem({ ...prod, NEXT_PHASE: "phase-production-build" })).toBeNull();
  });
});
