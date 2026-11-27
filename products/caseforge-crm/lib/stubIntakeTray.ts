
import type { IntakeItem } from "./intakeTrayTypes";
import { stubMadeClients, stubMadeCreated } from "./stubClients";

const now = Date.now();
const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");

const items: IntakeItem[] = [
  { matter_id: "9001", client_name: "Stub Testperson", created_utc: iso(now - 40 * 60_000) },
  { matter_id: "9003", client_name: "Third Stubperson", created_utc: iso(now - 26 * 3_600_000) },
  { matter_id: "9012", client_name: "Stub Samename", created_utc: iso(now - 3 * 3_600_000), same_name_index: 2, same_name_count: 2, same_name_birth_year: 1991, same_name_ref: "EFL-STUB-0012" },
];

export function stubRecentIntakes(): IntakeItem[] {
  const made: IntakeItem[] = stubMadeClients("*")
    .map((c) => ({ matter_id: String(c.matter_id), client_name: String(c.client_name ?? ""), created_utc: iso(stubMadeCreated(String(c.matter_id))) }))
    .reverse();
  return [...made, ...items].map((i) => ({ ...i }));
}
