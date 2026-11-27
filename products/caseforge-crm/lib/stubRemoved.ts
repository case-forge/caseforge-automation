
import type { DuplicatePair } from "./duplicates";
import type { RemovedClient } from "./removedClients";

const base = { folder_moved: true, restored_by: "", restored_utc: "", purged_utc: "", purge_note: "" };

export function stubRemoved(): RemovedClient[] {
  const now = Date.now();
  const days = (n: number) => new Date(now - n * 86_400_000).toISOString();
  return [
    { ...base, matter_id: "9003", client_name: "Demo Merged Person", reason: "Duplicate record", removed_by: "Demo user", removed_utc: days(2), state: "merged", merged_into: "9001", merged_into_name: "Demo Person One", can_undo: true },
    { ...base, matter_id: "9004", client_name: "Demo Removed Person", reason: "Opened by mistake", removed_by: "Demo user", removed_utc: days(5), state: "removed", merged_into: "", merged_into_name: "", can_undo: true },
    { ...base, matter_id: "9002", client_name: "Demo Unmerged Person", reason: "Duplicate record", removed_by: "Demo user", removed_utc: days(9), state: "unmerged", merged_into: "9001", merged_into_name: "Demo Person One", restored_by: "Demo user", restored_utc: days(8), can_undo: false },
    { ...base, matter_id: "9005", client_name: "Demo Old Removal", reason: "Left the firm", removed_by: "Demo user", removed_utc: days(60), state: "removed", merged_into: "", merged_into_name: "", can_undo: false },
  ];
}

export function stubDuplicates(): DuplicatePair[] {
  return [
    { reason: "same name", a: { matter_id: "9101", client_name: "Demo Twin Person" }, b: { matter_id: "9102", client_name: "Demo Twin Person" } },
    { reason: "same email", a: { matter_id: "9103", client_name: "Demo Email Person" }, b: { matter_id: "9104", client_name: "Demo Other Name" } },
  ];
}
