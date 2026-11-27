import type { SameNameFields } from "./sameName";

export interface IntakeItem extends SameNameFields {
  matter_id: string;
  client_name: string;
  created_utc: string;
}
