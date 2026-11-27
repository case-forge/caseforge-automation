
import type { ControlView, DecideView, QcItem } from "@/lib/mailReview";

const ROUTES = ["Client", "Counsel", "Court", "Legal Aid", "Other Side", "Process Server", "Junk", "Other"];

function item(n: number, over: Partial<QcItem>): QcItem {
  return {
    n,
    job_id: `demo-${n}`,
    from: "Sample Sender <sender@example.test>",
    to: "inbox@example.test",
    cc: "",
    date: "Mon, 19 Oct 2026 09:30:00 +0100",
    subject: `Sample subject ${n}`,
    attachments: [],
    text: `This is invented sample text for email ${n}. It stands in for a real message and names nobody.\n\n<b>Not bold</b> & plain.`,
    weblink: "",
    pool: "review",
    applied_route: "Court",
    route_source: "deterministic",
    stratum: "other",
    model_route: "",
    model_conf: null,
    rules_route: "Court",
    reason: "",
    created_utc: "2026-10-19T08:30:00Z",
    ...over,
  };
}

const DECIDE: QcItem[] = [
  item(1, { pool: "decide", applied_route: "Review", route_source: "deterministic", reason: "Route not decided", subject: "Documents for the hearing", attachments: ["scan-001.pdf"], created_utc: "2026-10-16T09:00:00Z", stratum: "unresolved" }),
  item(2, { pool: "decide", applied_route: "Court", route_source: "deterministic_ai_source_unconfirmed", model_route: "Counsel", model_conf: 0.88, rules_route: "Court", reason: "Route not decided", subject: "Re: directions", created_utc: "2026-10-18T09:00:00Z", stratum: "veto" }),
  item(3, { pool: "decide", applied_route: "Other Side", applied_destination: "Other Side", applied_other_text: "From the respondent", route_source: "respondent_guard", reason: "Route not decided", subject: "Quick question", created_utc: "2026-10-22T09:00:00Z", stratum: "unresolved" }),
];

const CONTROL: QcItem[] = [
  item(1, { pool: "review", applied_route: "Client", route_source: "ai_assisted", model_route: "Client", model_conf: 0.82, rules_route: "Junk", stratum: "model_overrode_rules", subject: "Update on my case" }),
  item(2, { pool: "control", applied_route: "Court", model_route: "Court", model_conf: 0.97, subject: "Notice of hearing" }),
  item(3, { pool: "review", applied_route: "Junk", route_source: "deterministic_ai_junk_disputed", model_route: "Complaints", model_conf: 0.9, rules_route: "Junk", stratum: "veto", subject: "I am not happy" }),
  item(4, { pool: "review", applied_route: "Counsel", route_source: "deterministic", model_conf: null, stratum: "unresolved", subject: "Skeleton argument" }),
];

const answered = new Map<string, string>();
const resolved = new Set<string>();

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function stubDecide(offset: number): DecideView {
  const queue = DECIDE.filter((i) => !resolved.has(i.job_id));
  const oldest = queue.length ? Math.max(0, (Date.now() - Date.parse(queue[0].created_utc)) / 86400000) : 0;
  const index = queue.length ? Math.max(0, offset) % queue.length : 0;
  return {
    total: queue.length,
    oldest_days: Math.round(oldest * 10) / 10,
    routes: ROUTES,
    item: queue.length ? { ...queue[index], n: index + 1, total: queue.length } : null,
    recent: [...resolved].reverse().slice(0, 5).map((_, i) => ({
      route: "Counsel",
      saved_utc: new Date().toISOString(),
      state: i === 0 ? "waiting" : "applied_blocked",
      plain: i === 0 ? "Waiting for the mail worker (about a minute)." : "The route Counsel was applied; the email is still held: no matter found.",
    })),
  };
}

export function stubDecideSave(jobId: string): { saved: true; job_id: string } {
  resolved.add(jobId);
  return { saved: true, job_id: jobId };
}

export function stubControl(n: number | null, pool?: "control" | "review"): ControlView {
  const batch = pool ? CONTROL.filter((i) => i.pool === pool) : CONTROL;
  const rows = batch.map((i) => ({ n: i.n, done: answered.has(i.job_id), verdict: answered.get(i.job_id) ?? "" }));
  const pick = n === null ? batch.find((i) => !answered.has(i.job_id)) : batch.find((i) => i.n === n);
  return {
    date: today(),
    total: batch.length,
    answered: rows.filter((r) => r.done).length,
    routes: ROUTES,
    pool_sizes: { review: 31, control: 212, decide: DECIDE.length },
    items: rows,
    item: pick ? { ...pick, answer: answered.has(pick.job_id) ? { route: "", verdict: answered.get(pick.job_id) ?? "" } : null } : null,
  };
}

export function stubControlSave(jobId: string, verdict: string): { saved: true; job_id: string; verdict: string } {
  answered.set(jobId, verdict);
  return { saved: true, job_id: jobId, verdict };
}
