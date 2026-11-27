"use client";

import { PORTAL_TITLE } from "@/lib/portalCell";

export function PortalCell({ className }: { className: string }) {
  return (
    <td className={className} title={PORTAL_TITLE}>
      Portal
    </td>
  );
}
