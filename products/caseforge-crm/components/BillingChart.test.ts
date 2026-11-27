
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { DailyTotals } from "@/lib/billingChart";
import { stubDailyTotals } from "@/lib/stubBillingChart";
import { BillingChartBody } from "./BillingChart";

const render = (data: DailyTotals, active: number | null = null) =>
  renderToStaticMarkup(createElement(BillingChartBody, { data, active, setActive: () => undefined }));

const day = (date: string, items: number, net: number) => ({ date, items, net_pence: net, vat_pence: net / 5, gross_pence: net * 1.2 });
const data: DailyTotals = {
  from: "2026-10-01", to: "2026-10-03",
  days: [day("2026-10-01", 2, 1080), day("2026-10-02", 0, 0), day("2026-10-03", 1, 540)],
  total_items: 3, total_net_pence: 1620, total_vat_pence: 324, total_gross_pence: 1944, undated_items: 0,
};

describe("BillingChartBody", () => {
  it("draws a bar for each day with money and none for a zero day, but keeps every day focusable", () => {
    const html = render(data);
    expect(html.match(/data-testid="bar"/g)).toHaveLength(2);
    expect(html.match(/class="billing-chart-hit"/g)).toHaveLength(3);
    expect(html).toContain("2 Oct 2026: £0.00 before VAT, 0 items");
  });
  it("summarises in pounds and offers every day in a table", () => {
    const html = render(data);
    expect(html).toContain("£16.20 before VAT");
    expect(html).toContain("£19.44 with VAT");
    expect(html.match(/<tr>/g)).toHaveLength(4);
    expect(html).toContain("Show the figures as a table");
  });
  it("shows the tooltip for the active day only", () => {
    expect(render(data)).not.toContain('role="tooltip"');
    expect(render(data, 0)).toContain('role="tooltip"');
  });
  it("says so when nothing was billed, and still gives the table", () => {
    const html = render({ ...data, days: data.days.map((d) => day(d.date, 0, 0)), total_items: 0, total_net_pence: 0, total_vat_pence: 0, total_gross_pence: 0 });
    expect(html).toContain("Nothing was billed between 1 Oct 2026 and 3 Oct 2026.");
    expect(html).not.toContain('data-testid="bar"');
    expect(html).toContain("billing-chart-table");
  });
  it("mentions items with no readable date", () => {
    expect(render({ ...data, undated_items: 2 })).toContain("2 items have no readable date");
  });
  it("has no cap, over-cap or limit wording", () => {
    expect(render(stubDailyTotals("2026-10-01", "2026-10-31"))).not.toMatch(/\bcap\b|over the|limit/i);
  });
});
