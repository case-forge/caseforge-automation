"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  PRESETS,
  axisPounds,
  barHeight,
  formatDay,
  formatPounds,
  londonToday,
  presetRange,
  rangeProblem,
  shortDay,
  yScale,
  type DailyTotals,
  type DayTotal,
  type Range,
} from "@/lib/billingChart";

const W = 720;
const H = 280;
const M = { top: 16, right: 12, bottom: 34, left: 56 };

function describe(d: DayTotal): string {
  return `${formatDay(d.date)}: ${formatPounds(d.net_pence)} before VAT, ${d.items} ${d.items === 1 ? "item" : "items"}`;
}

export function BillingChartBody({ data, active, setActive }: { data: DailyTotals; active: number | null; setActive: (i: number | null) => void }) {
  const days = data.days;
  const scale = useMemo(() => yScale(days.map((d) => d.net_pence)), [days]);
  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;
  const slot = plotW / Math.max(1, days.length);
  const barW = Math.max(1, slot * 0.7);
  const y = (v: number) => M.top + plotH - (v / scale.top) * plotH;
  const labelEvery = Math.max(1, Math.ceil(days.length / 8));
  const shown = active === null ? null : days[active];
  const empty = data.total_net_pence <= 0;

  return (
    <div>
      <p data-testid="chart-summary" className="billing-chart-summary">
        {formatDay(data.from)} to {formatDay(data.to)}: {formatPounds(data.total_net_pence)} before VAT ({formatPounds(data.total_gross_pence)} with VAT) across{" "}
        {data.total_items} {data.total_items === 1 ? "item" : "items"}.
      </p>
      {data.undated_items > 0 ? (
        <p className="billing-chart-note">
          {data.undated_items} {data.undated_items === 1 ? "item has" : "items have"} no readable date and {data.undated_items === 1 ? "is" : "are"} not shown.
        </p>
      ) : null}

      {empty ? (
        <p className="billing-chart-empty" data-testid="chart-empty">
          Nothing was billed between {formatDay(data.from)} and {formatDay(data.to)}.
        </p>
      ) : (
        <div className="billing-chart-scroll">
          <div className="billing-chart-box" style={{ minWidth: `${Math.min(days.length * 9 + 80, 1200)}px` }}>
            <svg
              viewBox={`0 0 ${W} ${H}`}
              role="group"
              aria-label={`Bar chart of money billed per day before VAT, ${formatDay(data.from)} to ${formatDay(data.to)}. The same figures are in the table below.`}
              className="billing-chart-svg"
            >
              {scale.ticks.map((t) => (
                <g key={t}>
                  <line className="billing-chart-grid" x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} />
                  <text className="billing-chart-axis" x={M.left - 6} y={y(t)} textAnchor="end" dominantBaseline="middle">
                    {axisPounds(t)}
                  </text>
                </g>
              ))}
              {days.map((d, i) => {
                const x = M.left + i * slot + (slot - barW) / 2;
                const h = barHeight(d.net_pence, scale.top, plotH);
                return (
                  <g key={d.date}>
                    {i % labelEvery === 0 ? (
                      <text className="billing-chart-axis" x={x + barW / 2} y={H - M.bottom + 16} textAnchor="middle">
                        {shortDay(d.date)}
                      </text>
                    ) : null}
                    {h > 0 ? (
                      <rect
                        data-testid="bar"
                        className={`billing-chart-bar${active === i ? " is-active" : ""}`}
                        x={x}
                        y={M.top + plotH - h}
                        width={barW}
                        height={h}
                        rx={Math.min(4, barW / 2)}
                      />
                    ) : null}
                    <rect
                      className="billing-chart-hit"
                      x={M.left + i * slot}
                      y={M.top}
                      width={slot}
                      height={plotH}
                      tabIndex={0}
                      role="img"
                      aria-label={describe(d)}
                      onMouseEnter={() => setActive(i)}
                      onMouseLeave={() => setActive(null)}
                      onFocus={() => setActive(i)}
                      onBlur={() => setActive(null)}
                    />
                  </g>
                );
              })}
            </svg>
            {shown ? (
              <div role="tooltip" className="billing-chart-tip" style={{ left: `${Math.min(80, Math.max(2, ((M.left + (active! + 0.5) * slot) / W) * 100))}%` }}>
                <strong>{formatDay(shown.date)}</strong>
                <div>{formatPounds(shown.net_pence)} before VAT</div>
                <div>
                  {shown.items} {shown.items === 1 ? "item" : "items"}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      <details className="billing-chart-table">
        <summary>Show the figures as a table</summary>
        <div className="billing-chart-table-wrap">
          <table>
            <caption className="billing-chart-sr">Money billed per day</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col" className="num">Items</th>
                <th scope="col" className="num">Before VAT</th>
                <th scope="col" className="num">VAT</th>
                <th scope="col" className="num">With VAT</th>
              </tr>
            </thead>
            <tbody>
              {days.map((d) => (
                <tr key={d.date}>
                  <th scope="row">{formatDay(d.date)}</th>
                  <td className="num">{d.items}</td>
                  <td className="num">{formatPounds(d.net_pence)}</td>
                  <td className="num">{formatPounds(d.vat_pence)}</td>
                  <td className="num">{formatPounds(d.gross_pence)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

export function BillingChart() {
  const [range, setRange] = useState<Range>(() => presetRange(30));
  const [draft, setDraft] = useState<Range>(range);
  const [rangeError, setRangeError] = useState<string | null>(null);
  const [result, setResult] = useState<{ key: string; data: DailyTotals | null; error: string } | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const key = `${range.from}|${range.to}|${attempt}`;

  useEffect(() => {
    let cancelled = false;
    const failed = (message: string) => !cancelled && setResult({ key, data: null, error: message });
    fetch(`/api/billing/daily-totals?start=${range.from}&end=${range.to}`, { cache: "no-store" })
      .then(async (res) => ({ ok: res.ok, body: await res.json().catch(() => ({})) }))
      .then(({ ok, body }) => {
        if (cancelled) return;
        if (!ok) failed(String(body.error ?? body.detail ?? "The billing figures could not be loaded."));
        else setResult({ key, data: body as DailyTotals, error: "" });
      })
      .catch(() => failed("The billing figures could not be loaded."));
    return () => {
      cancelled = true;
    };
  }, [range, key]);

  const current = result?.key === key ? result : null;
  const data = current ? current.data : (result?.data ?? null);
  const error = current?.error ?? "";
  const loading = current === null;

  const apply = useCallback(() => {
    const problem = rangeProblem(draft);
    setRangeError(problem);
    if (!problem) {
      setActive(null);
      setRange({ ...draft });
    }
  }, [draft]);

  function pick(days: number) {
    const next = presetRange(days);
    setRangeError(null);
    setActive(null);
    setDraft(next);
    setRange(next);
  }

  const today = londonToday();
  const activeDays = PRESETS.find((p) => range.to === today && range.from === presetRange(p.days, today).from)?.days;

  return (
    <section aria-labelledby="billing-chart-h" className="billing-chart">
      <h1 id="billing-chart-h">Billing by Day</h1>
      <p className="billing-chart-note">Money billed on each day, before VAT, across every matter. Days run midnight to midnight UK time. This only shows figures; it does not change any billing.</p>

      <div className="billing-chart-controls">
        <div role="group" aria-label="Range" className="billing-chart-presets">
          {PRESETS.map((p) => (
            <button key={p.days} type="button" aria-pressed={activeDays === p.days} className="cf-btn cf-btn--chip" onClick={() => pick(p.days)}>
              {p.label}
            </button>
          ))}
        </div>
        <form
          className="billing-chart-dates"
          onSubmit={(e) => {
            e.preventDefault();
            apply();
          }}
        >
          <label>
            From <input type="date" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} />
          </label>
          <label>
            To <input type="date" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
          </label>
          <button type="submit" className="cf-btn cf-btn--primary">Show</button>
        </form>
      </div>
      {rangeError ? (
        <p className="billing-chart-error" role="alert">
          {rangeError}
        </p>
      ) : null}

      <div aria-live="polite">
        {error ? (
          <p className="billing-chart-error" role="alert">
            {error}{" "}
            <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" onClick={() => setAttempt((n) => n + 1)}>
              Try again
            </button>
          </p>
        ) : loading && !data ? (
          <p className="billing-chart-note">Loading billing figures</p>
        ) : data ? (
          <BillingChartBody data={data} active={active} setActive={setActive} />
        ) : null}
      </div>
    </section>
  );
}
