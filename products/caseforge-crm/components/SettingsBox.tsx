"use client";

import { useClassifierPrompts } from "@/lib/classifierPrompts";
import { useFaviconLock } from "@/lib/faviconLock";
import { applyFavicon } from "@/components/FaviconColour";
import { useWindowDock, useWindowSnap } from "@/lib/windowBehaviour";
import { useEffect, useState } from "react";
import { SERVER_DEFAULT_MINUTES, loadDefaultTime, saveDefaultTime, totalMinutes } from "@/lib/anTime";
import type { AnTime } from "@/lib/anTime";

const EMPTY: AnTime = { hours: "", minutes: "" };

function DefaultTimeSetting() {
  const [time, setTime] = useState<AnTime>(() => loadDefaultTime() ?? EMPTY);
  const entered = time.hours.trim() !== "" || time.minutes.trim() !== "";
  const invalid = entered && totalMinutes(time) === null;
  function change(next: AnTime) {
    setTime(next);
    saveDefaultTime(next);
  }
  const digits = (value: string) => value.replace(/\D/g, "").slice(0, 2);
  return (
    <span className="settings-box-time">
      <input
        type="text"
        inputMode="numeric"
        className="an-form-time-box"
        value={time.hours}
        onChange={(e) => change({ ...time, hours: digits(e.target.value) })}
        placeholder="hh"
        aria-label="Default hours spent"
        aria-invalid={invalid || undefined}
      />
      <span aria-hidden="true">:</span>
      <input
        type="text"
        inputMode="numeric"
        className="an-form-time-box"
        value={time.minutes}
        onChange={(e) => change({ ...time, minutes: digits(e.target.value) })}
        placeholder={String(SERVER_DEFAULT_MINUTES)}
        aria-label="Default minutes spent"
        aria-invalid={invalid || undefined}
      />
    </span>
  );
}

export function ClassifierPromptsSetting() {
  const [on, setOn] = useClassifierPrompts();
  return (
    <div className="cf-segment" role="group" aria-label="Show classifier prompts">
      <button type="button" className="cf-btn cf-btn--segment" aria-pressed={on} onClick={() => setOn(true)}>
        On
      </button>
      <button type="button" className="cf-btn cf-btn--segment" aria-pressed={!on} onClick={() => setOn(false)}>
        Off
      </button>
    </div>
  );
}

export function BillingDefaultTime() {
  return (
    <div className="settings-field" role="group" aria-label="Default time">
      <p className="settings-field-label">Default time</p>
      <DefaultTimeSetting />
      <p className="settings-field-help">The time a new attendance note starts with. Kept in this browser and applied as you type; empty uses the server's own default.</p>
    </div>
  );
}

export function ClassifierPromptsField() {
  return (
    <div className="settings-field" role="group" aria-label="Classifier prompts">
      <p className="settings-field-label">Classifier prompts</p>
      <ClassifierPromptsSetting />
      <p className="settings-field-help">Now and then a small box asks whether an email was sorted correctly: at most one an hour, and never while you are typing. Kept in this browser.</p>
    </div>
  );
}

function OnOff({ label, on, setOn }: { label: string; on: boolean; setOn: (next: boolean) => void }) {
  return (
    <div className="cf-segment" role="group" aria-label={label}>
      <button type="button" className="cf-btn cf-btn--segment" aria-pressed={on} onClick={() => setOn(true)}>
        On
      </button>
      <button type="button" className="cf-btn cf-btn--segment" aria-pressed={!on} onClick={() => setOn(false)}>
        Off
      </button>
    </div>
  );
}

function FaviconLockField() {
  const [locked, setLocked] = useFaviconLock();
  return (
    <div className="settings-field" role="group" aria-label="Tab icon colour">
      <p className="settings-field-label">Tab icon colour</p>
      <div className="cf-segment" role="group" aria-label="Tab icon colour">
        <button type="button" className="cf-btn cf-btn--segment" aria-pressed={!locked} onClick={() => setLocked(null)}>
          Follow the theme
        </button>
        <button
          type="button"
          className="cf-btn cf-btn--segment"
          aria-pressed={!!locked}
          onClick={() => setLocked(applyFavicon())}
        >
          {locked ? `Locked to ${locked}` : "Lock to current colour"}
        </button>
      </div>
      <p className="settings-field-help">The tab icon turns white on a dark theme and black on a light one. Locking keeps it the colour it shows now, whatever the theme. Kept in this browser.</p>
    </div>
  );
}

export function WindowGestureFields() {
  const [snap, setSnap] = useWindowSnap();
  const [dock, setDock] = useWindowDock();
  return (
    <>
      <div className="settings-field" role="group" aria-label="Snap windows to the screen edges">
        <p className="settings-field-label">Snap windows to the screen edges</p>
        <OnOff label="Snap windows to the screen edges" on={snap} setOn={setSnap} />
        <p className="settings-field-help">Dragging a window to the left or right edge fits it to that half of the page, to the top edge fills the page, and to a corner takes that quarter. Kept in this browser.</p>
      </div>
      <div className="settings-field" role="group" aria-label="Dock windows at the screen edges">
        <p className="settings-field-label">Dock windows at the screen edges</p>
        <OnOff label="Dock windows at the screen edges" on={dock} setOn={setDock} />
        <p className="settings-field-help">Dragging a window right to the left or right edge turns it into a tab there; pressing the tab brings the window back. The minimise button still makes a tab. Kept in this browser.</p>
      </div>
      <FaviconLockField />
    </>
  );
}
