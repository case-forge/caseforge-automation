"use client";

import { useEffect, useState, type KeyboardEvent, type ReactNode, type SVGProps } from "react";
import { loadAppSettings, type AppSettingsView } from "@/lib/appSettings";
import { useDevMode } from "@/lib/devMode";
import { EmailClassifierSettings } from "./EmailClassifierSettings";
import { FirmLinksPanel } from "./FirmLinksPanel";
import { ExcludedFoldersPanel } from "./ExcludedFoldersPanel";
import { FolderMapPanel } from "./FolderMapPanel";
import { IconActivity, IconAutomation, IconBot, IconEnvelope, IconExternalLink, IconFolder, IconFolderTree, IconLandmark, IconPerson, IconPound, IconStorage, IconSystem } from "./icons";
import { ModelsPanel } from "./ModelsPanel";
import { BillingDefaultTime, ClassifierPromptsField, WindowGestureFields } from "./SettingsBox";
import { SettingsGroupPanel } from "./SettingsGroupPanel";
import { SpecialSendersPanel } from "./SpecialSendersPanel";
import { SystemHealthPanel } from "./SystemHealthPanel";
import { StoragePanel } from "./StoragePanel";

type Tab = { id: string; title: string; groups?: string[]; body?: ReactNode; extra?: ReactNode; devOnly?: boolean };

const TAB_ICONS: Record<string, (props: SVGProps<SVGSVGElement>) => ReactNode> = {
  "firm": IconLandmark,
  "folders": IconFolder,
  "folder-map": IconFolderTree,
  "billing": IconPound,
  "operations": IconAutomation,
  "models": IconBot,
  "email-classifier": IconEnvelope,
  "links": IconExternalLink,
  "special-senders": IconPerson,
  "system-health": IconActivity,
  "storage": IconStorage,
  "windows": IconSystem,
};

const DEFAULT_TAB = "firm";

const ALL_TABS: Tab[] = [
  { id: "firm", title: "Firm", groups: ["firm", "solicitor"], devOnly: true },
  { id: "folders", title: "Folders", groups: ["folders"], extra: <ExcludedFoldersPanel />, devOnly: true },
  { id: "folder-map", title: "Folder Map", body: <FolderMapPanel />, devOnly: true },
  { id: "billing", title: "Billing", groups: ["billing"], devOnly: true },
  { id: "operations", title: "Operations", groups: ["operations"], devOnly: true },
  { id: "models", title: "Models", body: <ModelsPanel />, devOnly: true },
  { id: "email-classifier", title: "Email Classifier", body: <div className="settings-group"><EmailClassifierSettings /></div>, devOnly: true },
  { id: "links", title: "Links", body: <FirmLinksPanel />, devOnly: true },
  { id: "special-senders", title: "Special Senders", body: <SpecialSendersPanel />, devOnly: true },
  { id: "system-health", title: "System Health", body: <SystemHealthPanel />, devOnly: true },
  { id: "storage", title: "Storage", body: <StoragePanel />, devOnly: true },
  { id: "windows", title: "This Browser", body: (
      <div className="settings-group">
        <WindowGestureFields />
        <BillingDefaultTime />
        <ClassifierPromptsField />
      </div>
    ) },
];

function ServerTab({ groups, after }: { groups: string[]; after?: ReactNode }) {
  const [view, setView] = useState<AppSettingsView | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void loadAppSettings().then((result) => {
      if (cancelled) return;
      if (result.state === "ok") setView(result.view);
      else setFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  if (failed && !view) return <p role="alert">The settings could not be loaded. Try again shortly.</p>;
  if (!view) return <p>Loading the settings</p>;
  return <SettingsGroupPanel key={groups.join("+")} groups={groups} view={view} onView={setView} after={after} />;
}

export function SettingsPage() {
  const [active, setActive] = useState(DEFAULT_TAB);

  const isDev = useDevMode();
  const TABS = ALL_TABS.filter((t) => isDev || !t.devOnly);
  const first = TABS[0];
  useEffect(() => {
    const fromHash = () => {
      const raw = window.location.hash.replace(/^#/, "");
      const id = raw === "solicitor" ? "firm" : raw;
      if (TABS.some((t) => t.id === id)) setActive(id);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDev]);

  function choose(id: string) {
    setActive(id);
    window.history.replaceState(null, "", id === first.id ? window.location.pathname : `#${id}`);
  }
  function onKeyDown(event: KeyboardEvent, index: number) {
    const keyed: Record<string, number> = { ArrowDown: index + 1, ArrowRight: index + 1, ArrowUp: index - 1, ArrowLeft: index - 1, Home: 0, End: TABS.length - 1 };
    if (!(event.key in keyed)) return;
    event.preventDefault();
    const next = TABS[(keyed[event.key] + TABS.length) % TABS.length];
    choose(next.id);
    document.getElementById(`settings-tab-${next.id}`)?.focus();
  }

  const current = TABS.find((t) => t.id === active) ?? first;
  return (
    <div className="settings-page">
      <h1>Settings</h1>
      <div className="settings-layout">
        <div className="settings-tabs" role="tablist" aria-label="Settings sections" aria-orientation="vertical">
          {TABS.map(({ id, title }, index) => {
            const TabIcon = TAB_ICONS[id];
            return (
            <button
              key={id}
              type="button"
              role="tab"
              id={`settings-tab-${id}`}
              aria-selected={id === current.id}
              aria-controls={`settings-panel-${id}`}
              tabIndex={id === current.id ? 0 : -1}
              className="cf-btn cf-btn--flush settings-tab"
              onClick={() => choose(id)}
              onKeyDown={(event) => onKeyDown(event, index)}
            >
              <TabIcon aria-hidden="true" />
              <span>{title}</span>
            </button>
            );
          })}
        </div>
        <label className="settings-section-select">
          <span className="models-sr">Settings section</span>
          <select value={current.id} onChange={(e) => choose(e.target.value)} aria-label="Settings section">
            {TABS.map(({ id, title }) => (
              <option key={id} value={id}>
                {title}
              </option>
            ))}
          </select>
        </label>
        <section role="tabpanel" id={`settings-panel-${current.id}`} aria-labelledby={`settings-tab-${current.id}`} className="settings-panel">
          <h2 className="settings-panel-title">{current.title}</h2>
          {current.groups ? <ServerTab groups={current.groups} after={current.extra} /> : current.body}
        </section>
      </div>
    </div>
  );
}
