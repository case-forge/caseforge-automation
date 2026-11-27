"use client";

import { IconExternalLink } from "./icons";
import { useCallback, useEffect, useState } from "react";
import { SameNameHint, SameNameSuffix } from "./SameNameLabel";
import {
  asOf,
  draftLinkText,
  isStepTile,
  itemLine,
  stepLine,
  safeLink,
  sectionHeading,
  tileLink,
  stepAge,
  visibleSections,
  type TodayBoardData,
  type TodayItem,
} from "@/lib/todayBoard";
import type { LandingTabId } from "@/lib/detailTabs";

export function TodayBoard({
  onOpenClient,
}: {
  onOpenClient: (name: string, matterId: string, tab?: LandingTabId, hearingId?: number) => void;
}) {
  const [data, setData] = useState<TodayBoardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(
    () =>
      fetch("/api/today", { cache: "no-store" })
        .then(async (res) => ({ ok: res.ok, body: await res.json().catch(() => ({})) }))
        .then(({ ok, body }) => {
          if (!ok) setError(String(body.error ?? "Today could not be loaded."));
          else {
            setData(body as TodayBoardData);
            setError("");
          }
        })
        .catch(() => setError("Today could not be loaded."))
        .finally(() => setLoading(false)),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const sections = visibleSections(data);

  function open(item: TodayItem, section: string) {
    const name = String(item.client_name || item.case_ref || "").trim();

    if (name) onOpenClient(name, String(item.matter_id || ""), isStepTile(section) ? "caseflow" : undefined);
  }

  return (
    <section className="today-board" aria-label="Today">
      <div className="today-head">
        <h2>Today</h2>
        <button
          type="button"
          className="cf-btn cf-btn--secondary cf-btn--small"
          onClick={() => {
            setLoading(true);
            void load();
          }}
          disabled={loading}
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>
      {error && <p className="new-client-error" role="alert">{error}</p>}
      {data && !error && sections.length === 0 && <p className="today-empty">Nothing waiting today.</p>}
      {sections.map((section) => (
        <div key={section.key} className="today-section" data-section={section.key}>
          <h3>{sectionHeading(section)}</h3>
          {!section.error && (
            <ul>
              {section.items.map((item, index) => {
                const tile = isStepTile(section.key);
                const link = tile ? tileLink(item) : section.key === "drafts" || section.key === "reminders" ? { kind: "draft" as const, label: draftLinkText(item), url: safeLink(item.web_link) ?? "" } : null;
                const age = tile ? stepAge(item) : null;
                return (
                  <li key={`${section.key}-${item.matter_id}-${index}`}>
                    <button type="button" className="cf-btn cf-btn--flush today-item" onClick={() => open(item, section.key)} title={tile ? "Open the client's Case flow page" : "Open the client"}>
                      <span className="today-item-name">{String(item.client_name || item.name || item.case_ref || "Unlinked")}<SameNameSuffix row={item} /></span>
                      <SameNameHint row={item} as="span" className="today-item-line" />
                      <span className="today-item-line">{itemLine(section.key, item)}</span>
                    </button>
                    {link && link.url && (
                      <a className="today-item-link" href={link.url} target="_blank" rel="noopener noreferrer" data-kind={link.kind}>
                        {link.label} <IconExternalLink aria-hidden="true" />
                      </a>
                    )}
                    {age && (
                      <div className="today-progress-row">
                        <span className="today-item-line">{[stepLine(age), asOf(item.checked_utc)].filter(Boolean).join(" · ")}</span>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ))}
    </section>
  );
}
