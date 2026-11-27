
export type CrmRole = "dev" | "admin" | "worker";

export function parseRole(value: unknown): CrmRole {
  return value === "dev" || value === "admin" ? value : "worker";
}
