
import { useEffect, useState } from "react";
import { parseRole, type CrmRole } from "@/lib/crmRoleName";

export { parseRole, type CrmRole };

export async function loadCrmRole(fetcher: typeof fetch = fetch): Promise<CrmRole> {
  try {
    const res = await fetcher("/api/me/role", { cache: "no-store" });
    if (!res.ok) return "worker";
    return parseRole(((await res.json()) as { role?: unknown } | null)?.role);
  } catch {
    return "worker";
  }
}

export function useDevMode(): boolean {
  const [role, setRole] = useState<CrmRole>("worker");
  useEffect(() => {
    let cancelled = false;
    void loadCrmRole().then((answer) => {
      if (!cancelled) setRole(answer);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return role === "dev";
}
