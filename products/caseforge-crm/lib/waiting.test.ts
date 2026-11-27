import { describe, expect, it } from "vitest";
import { WAITING_LABELS, WAITING_LISTS, waitingLabel, waitingOf } from "./waiting";

describe("waiting", () => {
  it("names the three pit stops in big capitals", () => {
    expect(WAITING_LABELS).toEqual({ client: "WAITING FOR CLIENT", court: "WAITING FOR COURT", counsel: "WAITING FOR COUNSEL" });
    expect(waitingLabel("counsel")).toBe("WAITING FOR COUNSEL");
  });

  it("reads a state from the hub's object or a bare name, and nothing else", () => {
    expect(waitingOf({ state: "client", label: "WAITING FOR CLIENT" })).toBe("client");
    expect(waitingOf("court")).toBe("court");
    expect(waitingOf({ state: "" })).toBeUndefined();
    expect(waitingOf(undefined)).toBeUndefined();
    expect(waitingOf("somebody")).toBeUndefined();
  });

  it("has one Client Lists entry per flag the hub sets", () => {
    expect(WAITING_LISTS.map((l) => l.flag)).toEqual(["waiting_client", "waiting_court", "waiting_counsel"]);
  });
});
