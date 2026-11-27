import { describe, expect, it } from "vitest";
import { DRAFT_FLAG_REASON, draftFlagRequest } from "./draftFlag";

describe("draftFlagRequest", () => {
  it("raises the Flagged flag with the reason when a draft is unfinished, naming nobody", () => {
    expect(draftFlagRequest("601", true)).toEqual({
      matter_id: "601", flag_name: "flagged", is_set: true, reason: DRAFT_FLAG_REASON,
    });
  });

  it("clears it only if it still carries that reason, so a hand-ticked flag survives", () => {
    const body = draftFlagRequest("601", false);
    expect(body).toMatchObject({ is_set: false, only_if_reason: DRAFT_FLAG_REASON });
    expect(body).not.toHaveProperty("reason");
  });

  it("never sends a name: the server records the signed-in person", () => {
    expect(draftFlagRequest("601", true)).not.toHaveProperty("set_by");
  });
});
