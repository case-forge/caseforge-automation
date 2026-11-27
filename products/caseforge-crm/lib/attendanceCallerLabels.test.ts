import { describe, expect, it } from "vitest";
import { ATTENDANCE_CALLER_LABELS } from "./types";

describe("ATTENDANCE_CALLER_LABELS", () => {
  it("shows the other side as Opponent, since the client may be the respondent", () => {
    expect(ATTENDANCE_CALLER_LABELS.respondent).toBe("Opponent");
  });

  it("labels the two caller checkboxes Frequent caller and Frequent caller (Opponent)", async () => {
    const { FLAG_FIELDS } = await import("./types");
    const labels = Object.fromEntries(FLAG_FIELDS.map((f: { name: string; label: string }) => [f.name, f.label]));
    expect(labels.persistent_caller).toBe("Frequent caller");
    expect(labels.persistent_caller_respondent).toBe("Frequent caller (Opponent)");
  });
});
