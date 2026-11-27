
import { addDays, dayCount, type DailyTotals } from "@/lib/billingChart";

export function stubDailyTotals(from: string, to: string): DailyTotals {
  const days = Array.from({ length: dayCount(from, to) }, (_, i) => {
    const date = addDays(from, i);
    const weekday = new Date(`${date}T12:00:00Z`).getUTCDay();
    const items = weekday === 0 || weekday === 6 ? 0 : 2 + (i % 5);
    const net = items * 540;
    const vat = Math.round(net * 0.2);
    return { date, items, net_pence: net, vat_pence: vat, gross_pence: net + vat };
  });
  const sum = (k: "items" | "net_pence" | "vat_pence" | "gross_pence") => days.reduce((a, d) => a + d[k], 0);
  return {
    from,
    to,
    days,
    total_items: sum("items"),
    total_net_pence: sum("net_pence"),
    total_vat_pence: sum("vat_pence"),
    total_gross_pence: sum("gross_pence"),
    undated_items: 0,
  };
}
