"use client";

import { clientHref } from "@/lib/clientLink";
import { COURT_PREP_COLUMNS, courtPrepCell, courtPrepRows, hearingLine } from "@/lib/courtPrep";
import type { CourtPrepItem } from "@/lib/courtPrep";

export function CourtPrepTable({ items }: { items: readonly CourtPrepItem[] }) {
  return (
    <div className="sb-compact-scroll">
      <table className="sb-compact-table">
        <thead>
          <tr>
            <th scope="col">Client</th>
            <th scope="col">Hearing</th>
            {COURT_PREP_COLUMNS.map((c) => (
              <th key={c.key} scope="col" title={c.title}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {courtPrepRows(items).map((item) => (
            <tr key={item.hearing_id}>
              <th scope="row">
                <a className="sb-client-link" href={clientHref(item.client_name, { matterId: item.matter_id })}>
                  {item.client_name}
                </a>
              </th>
              <td>
                {hearingLine(item) || <span className="sb-compact-empty">–</span>}
                {item.notice === "without notice" && <span className="hearing-badge hearing-badge--exparte"> Ex parte</span>}
              </td>
              {COURT_PREP_COLUMNS.map((c) => {
                const label = courtPrepCell(item.milestones[c.key]);
                return (
                  <td key={c.key} className={label ? undefined : "sb-compact-empty"}>
                    {label || "–"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
