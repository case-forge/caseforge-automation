
import type { ConflictCheck } from "./conflictCheck";
import { DEMO_PRINCIPAL, DEMO_SECOND } from "./stubFirm";

const BLANK: ConflictCheck = {
  matter_id: "",
  run: false,
  run_utc: "",
  run_by: "",
  stale: false,
  verdict: "",
  matches: [],
  held_back: 0,
  parties_checked: 0,
  compared: {},
  gaps: [],
};

const CHECKED: Record<string, Omit<ConflictCheck, "matter_id">> = {
  "9002": {
    run: true,
    run_utc: "2026-10-11T09:12:00Z",
    run_by: DEMO_SECOND,
    stale: false,
    verdict: "review",
    matches: [
      {
        direction: "opponent_is_client",
        strength: "strong",
        reasons: ["similar name", "same date of birth"],
        this_is: "Respondent on this matter: Sam Stubrespondent",
        that_is: "Client in another matter",
        other_name: "Samuel Stubrespondent",
        other_matter_id: "9003",
        other_reference: "260601/03FL",
        other_client: "Samuel Stubrespondent",
        other_closed: true,
      },
      {
        direction: "client_is_opponent",
        strength: "weak",
        reasons: ["similar name"],
        this_is: "This client",
        that_is: "Respondent in another matter",
        other_name: "Second Stubperson",
        other_matter_id: "9001",
        other_reference: "261001/01FL",
        other_client: "Stub Testperson",
        other_closed: false,
      },
    ],
    held_back: 0,
    parties_checked: 1,
    compared: { clients: 3, parties: 2 },
    gaps: [],
  },
  "9003": {
    run: true,
    run_utc: "2026-09-10T14:00:00Z",
    run_by: DEMO_PRINCIPAL,
    stale: false,
    verdict: "clear",
    matches: [],
    held_back: 0,
    parties_checked: 1,
    compared: { clients: 3, parties: 2 },
    gaps: ["1 other party has no date of birth, phone or email on record, so it was matched on name alone."],
  },
};

const runs = new Map<string, ConflictCheck>();

export function stubConflictCheck(matterId: string): ConflictCheck {
  const ran = runs.get(matterId);
  if (ran) return ran;
  const known = CHECKED[matterId];
  return known ? { ...BLANK, ...known, matter_id: matterId } : { ...BLANK, matter_id: matterId };
}

export function stubRunConflictCheck(matterId: string, by: string): ConflictCheck | { error: string } {
  const name = by.trim();
  if (!name) return { error: "type your name first" };
  const known = CHECKED[matterId];
  const result: ConflictCheck = {
    ...BLANK,
    ...(known ?? { verdict: "clear" as const, parties_checked: 0, gaps: ["No other party is recorded on this matter, so only the client was checked. Record the respondent and run the check again."] }),
    matter_id: matterId,
    run: true,
    run_utc: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
    run_by: name,
    stale: false,
  };
  runs.set(matterId, result);
  return result;
}
