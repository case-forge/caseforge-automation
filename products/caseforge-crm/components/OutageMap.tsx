"use client";

import { OUTAGE_LOGOS } from "@/lib/outageLogos";
import { LINE_ICONS, PRESETS, SERVICES, capabilityResults, isDown, layout, telegramCards, wiring, type LiveDown, type Placed } from "@/lib/outageMap";
import { useMemo, useState } from "react";

const PLACED: Placed[] = layout();
const POS: Record<string, Placed> = Object.fromEntries(PLACED.map((s) => [s.id, s]));
const WIRES = wiring();

function radius(s: Placed): number {
  return s.ring === 0 ? 62 : s.ring === 1 ? 18 : 20;
}

function Node({ s, off, onToggle }: { s: Placed; off: ReadonlySet<string>; onToggle: (id: string) => void }) {
  const down = off.has(s.id);
  const hit = !down && isDown(s.id, off);
  const r = radius(s);
  const size = s.ring === 0 ? 26 : s.ring === 1 ? 18 : 20;
  const iy = s.ring === 0 ? -34 : 0;
  const line = s.line !== undefined;
  const d = line ? LINE_ICONS[s.line as string] : OUTAGE_LOGOS[s.logo as string];
  const cls = ["outage-node", s.ring === 0 ? "outage-node--hub" : "", down ? "outage-node--down" : "", hit ? "outage-node--hit" : ""].join(" ").trim();
  const state = down ? "down" : hit ? "cut off" : "running";
  return (
    <g
      className={cls}
      transform={`translate(${s.x},${s.y})`}
      tabIndex={0}
      role="button"
      aria-pressed={down}
      aria-label={`${s.name}${s.sub ? `, ${s.sub}` : ""}: ${state}. Activate to take it ${down ? "back up" : "down"}.`}
      onClick={() => onToggle(s.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggle(s.id);
        }
      }}
    >
      <circle r={r} />
      <path className={line ? "outage-icon outage-icon--line" : "outage-icon"} d={d} transform={`translate(${-size / 2},${iy - size / 2}) scale(${size / 24})`} />
      <text y={s.ring === 0 ? 10 : r + 16}>{s.name}</text>
      {s.sub && (
        <text className="outage-sub" y={s.ring === 0 ? 27 : r + 30}>
          {s.sub}
        </text>
      )}
    </g>
  );
}

export function OutageMap({ live }: { live: LiveDown }) {
  const [off, setOff] = useState<ReadonlySet<string>>(() => new Set(live.ids));
  const results = useMemo(() => capabilityResults(off), [off]);
  const cards = useMemo(() => telegramCards(off), [off]);
  const stops = results.filter((r) => r.state === "bad").length;
  const limited = results.filter((r) => r.state === "warn").length;
  const toggle = (id: string) =>
    setOff((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  return (
    <section aria-label="What stops when a service goes down" className="outage">
      <h2 className="system-health-heading">What stops when a service goes down</h2>
      <p className="system-health-muted">
        Click any service to take it down and see what the firm loses, what keeps working and what reaches your Telegram. The wiring is entered by hand from the
        repository and shows what depends on what. A service is switched off for you only when its provider declares an outage or the production box&rsquo;s own checks find it failing, and the reason is shown.
      </p>
      {live.ids.length > 0 && (
        <ul className="outage-live" role="status">
          {live.ids.map((id) => (
            <li key={id}>
              <strong>{SERVICES.find((s) => s.id === id)?.name ?? id}</strong>: {live.reasons[id]}
            </li>
          ))}
        </ul>
      )}
      <div className="outage-presets">
        {PRESETS.map(([label, ids]) => (
          <button key={label} type="button" className="cf-btn cf-btn--secondary" onClick={() => setOff(new Set(ids))}>
            {label}
          </button>
        ))}
        <button type="button" className="cf-btn cf-btn--secondary" onClick={() => setOff(new Set())}>
          Everything running
        </button>
        {live.ids.length > 0 && (
          <button type="button" className="cf-btn cf-btn--secondary" onClick={() => setOff(new Set(live.ids))}>
            Back to live
          </button>
        )}
      </div>
      <div className="outage-cols">
        <div className="outage-panel">
          <svg viewBox="-400 -385 800 770" role="group" aria-label="Service map" className="outage-svg">
            {WIRES.map(([a, b]) => (
              <line
                key={`${a}-${b}`}
                className={isDown(a, off) || isDown(b, off) ? "outage-wire outage-wire--cut" : "outage-wire"}
                x1={POS[a].x}
                y1={POS[a].y}
                x2={POS[b].x}
                y2={POS[b].y}
              />
            ))}
            {PLACED.map((s) => (
              <Node key={s.id} s={s} off={off} onToggle={toggle} />
            ))}
          </svg>
          <p className="outage-legend">
            <span className="outage-key">Running</span>
            <span className="outage-key outage-key--down">Down</span>
            <span className="outage-key outage-key--hit">Running, but cut off from something it needs</span>
          </p>
        </div>
        <div className="outage-side">
          <div className="outage-panel">
            <h3 className="outage-subhead">{off.size ? `What the firm can do: ${stops} stopped, ${limited} limited` : "What the firm can do"}</h3>
            <ul className="outage-caps" aria-live="polite">
              {results.map((r) => (
                <li key={r.cap.name}>
                  <span className={`outage-pill outage-pill--${r.state}`}>{r.label}</span>
                  <div>
                    <div>{r.cap.name}</div>
                    {r.why && <div className="system-health-muted">{r.why}</div>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <div className="outage-panel">
            <h3 className="outage-subhead">What reaches your Telegram</h3>
            {cards.map((c) => (
              <div key={`${c.bot}-${c.routeText}`} className="outage-alert">
                <div className="outage-alert-head">
                  <span className="outage-bot">{c.bot}</span>
                  <span className={`outage-route outage-route--${c.route}`}>{c.routeText}</span>
                </div>
                {c.text && <pre className="outage-tg">{c.text}</pre>}
              </div>
            ))}
            <p className="system-health-muted">
              A page reaches your phone at once, at any hour; a digest waits for the one morning message. Alerts name what stops, never a client.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
