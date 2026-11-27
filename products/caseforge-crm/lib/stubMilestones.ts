
import {
  MILESTONES,
  emptyMilestones,
  isManualMilestone,
  type MatterMilestonesResponse,
  type MilestoneKey,
  type MilestoneValue,
  type StatusBoardItem,
  type StatusBoardResponse,
} from "./matterMilestones";

const daysAgo = (days: number, hour = 10): string => {
  const d = new Date(Date.now() - days * 86_400_000);
  d.setUTCHours(hour, 15, 0, 0);
  return d.toISOString().replace(/\.\d+Z$/, "Z");
};

const system = (at: string, source: string): MilestoneValue => ({ at, source, set_by: "", manual: false, can_set: false });

const FOUND: Record<string, Partial<Record<MilestoneKey, MilestoneValue>>> = {
  "9001": {
    contacted: system(daysAgo(12), "first statement email sent"),
    papers_signed: system(daysAgo(9), "signed witness statement filed"),
    filed: system(daysAgo(6), "court email sent"),
    service_requested: system(daysAgo(5), "service email to referrer sent"),
    served: system(daysAgo(2), "statement of service received"),
    legal_aid_done: system(daysAgo(5), "signed legal aid declaration received"),
    laa_interim_cert: system(daysAgo(3), "certificate in the matter folder"),
  },
  "9002": { contacted: system(daysAgo(3), "first statement email sent") },
  "9003": {
    contacted: system(daysAgo(8), "first statement email sent"),
    papers_signed: system(daysAgo(2), "signed witness statement filed"),
    laa_interim_cert: system(daysAgo(40), "certificate in the matter folder"),
    laa_final_cert: system(daysAgo(1), "certificate in the matter folder"),
  },
  "9004": {},
  "9016": { filed: system(daysAgo(1), "court email sent") },

  "9010": {
    contacted: system(daysAgo(12), "first statement email sent"),
    filed: system(daysAgo(6), "court email sent"),
    laa_final_cert: system(daysAgo(2), "certificate in the matter folder"),
  },
  "9011": {
    contacted: system(daysAgo(20), "first statement email sent"),
    filed: system(daysAgo(14), "court email sent"),
    laa_final_cert: system(daysAgo(8), "certificate in the matter folder"),
  },
};

const PORTAL_COURT = new Set<string>(["9015", "9016"]);

const nudgeRule = { rule_id: "signing_loa_ws", since_date: "2026-11-05", working_days: 3 };
const NUDGES: Record<string, StatusBoardItem["nudge"]> = {
  "9012": { witness_statement: nudgeRule },
  "9013": { client_docs: nudgeRule },
  "9014": { client_docs: nudgeRule, witness_statement: nudgeRule },
};

const wetransferPending = new Set<string>(["9009", "9012"]);

export function stubWetransferGate(matterId: string): { ok: true; matter_id: string } {
  wetransferPending.delete(matterId);
  return { ok: true, matter_id: matterId };
}

const NAMES: Record<string, { name: string; joined: string; loa: string; ws: string; codes: string[]; book: string }> = {
  "9001": { name: "Stub client 9001", joined: daysAgo(14), loa: daysAgo(10), ws: daysAgo(9), codes: ["NMO"], book: "Book A - NMO-CAO" },
  "9002": { name: "Stub client 9002", joined: daysAgo(4), loa: "", ws: "", codes: ["NMO", "PSO"], book: "Book A - NMO-CAO" },
  "9003": { name: "Stub client 9003", joined: daysAgo(9), loa: daysAgo(3), ws: daysAgo(2), codes: ["CAO"], book: "Book A - NMO-CAO" },
  "9004": { name: "Stub client 9004", joined: daysAgo(1), loa: "", ws: "", codes: ["OO"], book: "Book B - Litigation" },
  "9005": { name: "Stub client 9005", joined: daysAgo(20), loa: daysAgo(15), ws: "", codes: [], book: "Book C - Other" },
  "9006": { name: "Stub client 9006", joined: daysAgo(30), loa: "", ws: "", codes: ["SIO"], book: "Care-Proceedings" },
  "9007": { name: "Stub client 9007", joined: daysAgo(6), loa: "", ws: "", codes: ["NMO"], book: "Book B - Litigation" },
  "9009": { name: "Stub client 9009", joined: daysAgo(5), loa: "", ws: "", codes: ["NMO"], book: "Book A - NMO-CAO" },
  "9010": { name: "Stub client 9010", joined: daysAgo(25), loa: daysAgo(20), ws: daysAgo(15), codes: ["CAO"], book: "Book A - NMO-CAO" },
  "9011": { name: "Stub client 9011", joined: daysAgo(40), loa: daysAgo(35), ws: daysAgo(28), codes: ["CAO"], book: "Book A - NMO-CAO" },

  "9012": { name: "Stub client 9012", joined: daysAgo(1), loa: daysAgo(1), ws: "", codes: ["NMO"], book: "Book A - NMO-CAO" },
  "9013": { name: "Stub client 9013", joined: daysAgo(2), loa: "", ws: daysAgo(1), codes: ["CAO"], book: "Book A - NMO-CAO" },
  "9014": { name: "Stub client 9014", joined: daysAgo(2), loa: "", ws: "", codes: ["NMO"], book: "Book A - NMO-CAO" },

  "9015": { name: "Stub client 9015", joined: daysAgo(1), loa: daysAgo(1), ws: "", codes: ["NMO"], book: "Book A - NMO-CAO" },
  "9016": { name: "Stub client 9016", joined: daysAgo(2), loa: daysAgo(2), ws: "", codes: ["CAO"], book: "Book A - NMO-CAO" },
  "9008": { name: "Stub client 9008", joined: daysAgo(3), loa: "", ws: "", codes: [], book: "Book A - NMO-CAO" },
};

const byHand = new Map<string, MilestoneValue>();

function valueFor(matterId: string, key: MilestoneKey): MilestoneValue {
  const typed = byHand.get(`${matterId}:${key}`);
  if (typed) return typed;

  return { ...emptyMilestones()[key], ...(FOUND[matterId]?.[key] ?? {}), can_set: isManualMilestone(key) };
}

export function stubMatterMilestones(matterId: string): MatterMilestonesResponse {
  return {
    matter_id: matterId,
    milestones: Object.fromEntries(MILESTONES.map(({ key }) => [key, valueFor(matterId, key)])) as MatterMilestonesResponse["milestones"],
  };
}

export function stubSetMilestone(
  matterId: string,
  milestone: string,
  at: string,
  clear: boolean,
): (MatterMilestonesResponse & { at: string; milestone: string }) | { error: string } {
  if (!isManualMilestone(milestone)) {
    return { error: "this milestone is recorded by the system and cannot be set by hand" };
  }
  const when = clear ? "" : at.trim() ? new Date(at).toISOString().replace(/\.\d+Z$/, "Z") : new Date().toISOString().replace(/\.\d+Z$/, "Z");
  if (!clear && Number.isNaN(new Date(when).getTime())) return { error: "that is not a date and time" };
  if (!clear && new Date(when).getTime() > Date.now() + 5 * 60_000) return { error: "that time is in the future" };
  byHand.set(`${matterId}:${milestone}`, { at: when, source: "manual", set_by: "demo", manual: true, can_set: true });
  return { ...stubMatterMilestones(matterId), at: when, milestone };
}

function stubLinks(joined: string, ws: string, contacted: string, filed: string, final: string): NonNullable<StatusBoardItem["links"]> {
  const mail = "https://outlook.office365.com/owa/?stub=1";
  const file = "https://example.sharepoint.com/stub.pdf";
  return {
    ...(joined ? { referred: mail } : {}),
    ...(contacted ? { contacted: mail } : {}),
    ...(ws ? { initial_ws: file } : {}),
    ...(filed ? { filed: mail } : {}),
    ...(final ? { laa_final_cert: file } : {}),
  };
}

export function stubStatusBoard(): StatusBoardResponse {
  return {
    columns: MILESTONES.map(({ key, label }) => ({ key, label })),
    items: Object.entries(NAMES).map(([matterId, n]) => ({
      matter_id: matterId,
      client_name: n.name,
      date_joined: n.joined,
      loa: n.loa,
      initial_ws: n.ws,
      order_codes: n.codes,
      book: n.book,
      milestones: Object.fromEntries(MILESTONES.map(({ key }) => [key, valueFor(matterId, key).at])) as Record<MilestoneKey, string>,
      wetransfer_pending: wetransferPending.has(matterId),
      portal_court: PORTAL_COURT.has(matterId),

      links: Number(matterId) % 2 === 0 ? stubLinks(n.joined, n.ws, valueFor(matterId, "contacted").at, valueFor(matterId, "filed").at, valueFor(matterId, "laa_final_cert").at) : {},
      ...(NUDGES[matterId] ? { nudge: NUDGES[matterId] } : {}),
    })),
  };
}
