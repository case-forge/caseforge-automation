
export type ScanDateSource = "filename" | "uploaded" | "modified" | "unknown";

export interface ScanRow {
  id: string;
  name: string;

  scan_date: string;

  date_source: ScanDateSource;
  uploaded_utc: string;
  modified_utc: string;

  pages: number | null;

  possible_client: string;
  folder: string;
  web_url: string;
  size_bytes: number;

  same_contents_as: string[];
}

export interface ScansTable {
  folder: string;

  readable: boolean;
  total: number;
  folders_not_listed: number;
  read_utc: string;
  rows: ScanRow[];
}
