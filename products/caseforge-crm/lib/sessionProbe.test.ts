import { describe, expect, it } from "vitest";
import {
  GIVE_UP_AFTER_MS,
  RECONNECT_START,
  classifyResponse,
  classifySessionProbe,
  reconnectReducer,
  retryDelayMs,
} from "./sessionProbe";

const ACCESS = '<html><title>Sign in</title><a href="https://x.cloudflareaccess.com/cdn-cgi/access/login">';

describe("classifySessionProbe", () => {
  it("an opaque redirect is an Access expiry", () => {
    expect(classifySessionProbe({ type: "opaqueredirect", status: 0 })).toBe("access-expired");
  });
  it("a 401 with Access HTML is an expiry", () => {
    expect(classifySessionProbe({ type: "basic", status: 401, contentType: "text/html", bodyHint: ACCESS })).toBe("access-expired");
  });
  it("a 200 JSON answer is ok", () => {
    expect(classifySessionProbe({ type: "basic", status: 200, contentType: "application/json" })).toBe("ok");
  });
  it("a readable JSON error under 500 is ok (the session is fine)", () => {
    expect(classifySessionProbe({ status: 404, contentType: "application/json" })).toBe("ok");
  });
  it("a 502 HTML page is unreachable, even if the page mentions Access", () => {
    expect(classifySessionProbe({ status: 502, contentType: "text/html", bodyHint: ACCESS })).toBe("unreachable");
    expect(classifySessionProbe({ status: 502, contentType: "text/html", bodyHint: "<h1>Bad gateway</h1>" })).toBe("unreachable");
  });
  it("a 504 is unreachable", () => {
    expect(classifySessionProbe({ status: 504, contentType: "text/html" })).toBe("unreachable");
  });
  it("a thrown TypeError is unreachable", () => {
    expect(classifySessionProbe({ threw: true })).toBe("unreachable");
  });
  it("a 200 HTML page that is not Access is unreachable", () => {
    expect(classifySessionProbe({ status: 200, contentType: "text/html", bodyHint: "<html>hello</html>" })).toBe("unreachable");
  });
  it("a 401 HTML page that is not Access is unreachable", () => {
    expect(classifySessionProbe({ status: 401, contentType: "text/html", bodyHint: "<html>nope</html>" })).toBe("unreachable");
  });
});

describe("classifyResponse", () => {
  it("reads Access HTML from a real Response", async () => {
    const res = new Response(ACCESS, { status: 401, headers: { "content-type": "text/html" } });
    expect(await classifyResponse(res)).toBe("access-expired");
  });
  it("treats a 502 Response as unreachable", async () => {
    expect(await classifyResponse(new Response("<h1>x</h1>", { status: 502, headers: { "content-type": "text/html" } }))).toBe("unreachable");
  });
});

describe("reconnectReducer", () => {
  it("stays quiet after one failure, shows after two", () => {
    const one = reconnectReducer(RECONNECT_START, { type: "failure", now: 0 });
    expect(one.note).toBe("none");
    expect(reconnectReducer(one, { type: "failure", now: 30_000 }).note).toBe("reconnecting");
  });
  it("escalates after five minutes of failures", () => {
    let s = reconnectReducer(RECONNECT_START, { type: "failure", now: 0 });
    s = reconnectReducer(s, { type: "failure", now: 30_000 });
    s = reconnectReducer(s, { type: "failure", now: GIVE_UP_AFTER_MS - 1 });
    expect(s.note).toBe("reconnecting");
    s = reconnectReducer(s, { type: "failure", now: GIVE_UP_AFTER_MS });
    expect(s.note).toBe("still-unreachable");
  });
  it("clears at once on success and starts counting afresh", () => {
    let s = reconnectReducer(RECONNECT_START, { type: "failure", now: 0 });
    s = reconnectReducer(s, { type: "failure", now: 1 });
    s = reconnectReducer(s, { type: "success" });
    expect(s).toEqual(RECONNECT_START);
    expect(reconnectReducer(s, { type: "failure", now: 99 }).note).toBe("none");
  });
  it("backs off briefly, capped", () => {
    expect([1, 2, 3, 9].map(retryDelayMs)).toEqual([5000, 10000, 15000, 15000]);
  });
});
