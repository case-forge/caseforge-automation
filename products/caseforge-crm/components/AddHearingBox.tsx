"use client";

import { hearingsHost, useHearingTabs } from "@/lib/hearingsHost";
import { TABS_FULL_HINT, MAX_HEARING_TABS, tabTitle, tabsFull } from "@/lib/hearingTabs";
import { NewHearingDrawer } from "./HearingDrawer";
import { WidgetBox } from "./WidgetBox";
import { IconClose } from "./icons";

export function AddHearingBox() {
  const state = useHearingTabs();
  const full = tabsFull(state);
  return (
    <WidgetBox corner="add-hearing" boxId="add-hearing" title="Add a Hearing" className="add-hearing-box" onOpened={() => { if (hearingsHost.tabs().tabs.length === 0) hearingsHost.addBlankTab(); }}>
      <div className="hearing-tabs" role="tablist" aria-label="Hearings being added">
        {state.tabs.map((t) => {
          const title = tabTitle(t.spec);
          const selected = state.active === t.key;
          return (
            <span key={t.key} className={`hearing-tab${selected ? " hearing-tab--active" : ""}`}>
              <button type="button" role="tab" id={`hearing-tab-${t.key}`} aria-selected={selected} aria-controls={`hearing-tabpanel-${t.key}`} tabIndex={selected ? 0 : -1} className="hearing-tab-label" onClick={() => hearingsHost.showTab(t.key)}>
                {title}
              </button>
              <button type="button" className="hearing-tab-close" aria-label={`Close tab ${title}`} title="Close this tab" onClick={() => hearingsHost.requestCloseTab(t.key)}>
                <IconClose aria-hidden="true" />
              </button>
            </span>
          );
        })}
        <button type="button" className="hearing-tab-add" aria-label="Add a tab" title={full ? TABS_FULL_HINT : "Add another hearing"} disabled={full} onClick={() => hearingsHost.addBlankTab()}>
          +
        </button>
        <span className="review-mail-sr">{`${state.tabs.length} of ${MAX_HEARING_TABS} tabs`}</span>
      </div>
      {state.tabs.length === 0 && <p className="hearing-muted">No hearing is being added. Press + to start one.</p>}
      { }
      {state.tabs.map((t) => (
        <div key={t.key} role="tabpanel" id={`hearing-tabpanel-${t.key}`} aria-labelledby={`hearing-tab-${t.key}`} hidden={state.active !== t.key}>
          <NewHearingDrawer
            bare
            guardId={t.key}
            clientName={t.spec.clientName}
            defaults={t.spec.defaults}
            draftId={t.spec.draftId}
            restoreValues={t.spec.restoreValues}
            known={t.spec.known}
            intro={t.spec.intro}
            onEditExisting={(existing) => {
              hearingsHost.closeTabNow(t.key);
              hearingsHost.openEdit(existing, { startEditing: true });
            }}
            onClose={() => hearingsHost.closeTabNow(t.key)}
            onCreated={(h) => {
              hearingsHost.closeTabNow(t.key);
              hearingsHost.bump();
              try {
                t.spec.onCreated?.(h);
              } catch {

              }
              if (t.spec.openAfter !== false) hearingsHost.openEdit(h);
            }}
          />
        </div>
      ))}
    </WidgetBox>
  );
}
