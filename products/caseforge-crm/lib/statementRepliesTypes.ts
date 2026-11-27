
export type ReplyState = "approved" | "amend";

export interface StatementReply {
  matter_id: string;
  client_name: string;
  state: ReplyState;
  note: string;
  by: string;
  recorded_utc: string;
}

export interface StatementReplies {
  approved_count: number;
  amend_count: number;
  items: StatementReply[];
}
