
import type { StorageRow, StorageStatusResponse } from "./storageStatus";

const GB = 10 ** 9;

function r(key: string, group: string, name: string, gb: number | null, total: number | null = null, note = ""): StorageRow {
  return { key, group, name, bytes: gb === null ? null : Math.round(gb * GB), total_bytes: total === null ? null : total * GB, state: gb === null ? "unknown" : "ok", note };
}

export function stubStorageStatus(): StorageStatusResponse {
  return {
    available: true,
    note: "",
    generated_at: new Date(Date.now() - 4 * 60_000).toISOString(),
    age_minutes: 4,
    stale: false,
    target_backup_bytes: 40 * GB,
    rows: [
      r("personal_live", "cloud", "Personal OneDrive, live files", 880, 1100),
      r("personal_recycle", "cloud", "Personal OneDrive, recycle bin", 1),
      r("sharepoint_live", "cloud", "SharePoint client files, live files", 430, 27000),
      r("sharepoint_recycle", "cloud", "SharePoint client files, recycle bin", 990),
      r("backup_folder", "backup", "Backup folder", 34, 40, "49 files"),
      r("company_data:Clients Live Files", "company_data_folders", "Clients Live Files", 330),
      r("company_data:Backups", "company_data_folders", "Backups", 34),
      r("personal:Closed Archives", "personal_folders", "Closed Archives", 131),
      r("personal:Attachments", "personal_folders", "Attachments", 18),
      r("server_root", "server", "Production box, whole disk", 53, 157),
      r("server_encrypted", "server", "Encrypted data volume", 25),
      r("server_builds_old", "server", "Old website builds kept as spares", 3.9),
      r("server_mail_capture", "server", "Raw mail capture", 1.7),
      r("azure:valauditlogs01", "azure", "valauditlogs01", 0.0008),
      r("azure:valsendgate01", "azure", "valsendgate01", null, null, "Not measured: this box is not allowed to read Azure storage figures"),
      r("github_repo", "github", "GitHub repository", null, null, "Not measured: this box holds no GitHub token"),
    ],
  };
}
