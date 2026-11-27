
export interface Countdown {
  overdue: boolean;

  label: string;

  long: string;
}

function two(n: number): string {
  return String(n).padStart(2, "0");
}

function plural(n: number, unit: string): string {
  return `${n} ${unit}${n === 1 ? "" : "s"}`;
}

export function countdown(dueUtc: string, now: Date = new Date()): Countdown | null {
  const due = new Date(dueUtc).getTime();
  if (Number.isNaN(due)) return null;
  const diffMs = due - now.getTime();
  const overdue = diffMs <= 0;
  const totalMinutes = Math.floor(Math.abs(diffMs) / 60_000);
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  return {
    overdue,
    label: `${two(days)}:${two(hours)}:${two(minutes)}`,
    long: [plural(days, "day"), plural(hours, "hour"), plural(minutes, "minute")].join(", "),
  };
}

export function countdownText(c: Countdown): string {
  return c.overdue ? `Overdue ${c.label}` : `Due in ${c.label}`;
}
