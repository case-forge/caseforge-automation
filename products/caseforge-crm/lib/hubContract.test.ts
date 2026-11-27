
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { hubResponseSchema, hubRouteKeys, validateAgainstHub } from "./hubContract";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const routeModules = import.meta.glob("../app/api/**/route.ts");

type Case = { dir: string; query?: string; hub: string };

const CASES: Case[] = [
  { dir: "attendance-notes/backup", query: "matter_id=1", hub: "/client-viewer/attendance-notes/backup" },
  { dir: "attendance-notes/folders", query: "matter_id=1", hub: "/client-viewer/attendance-notes/folders" },
  { dir: "attendance-notes/recent", query: "matter_id=1", hub: "/client-viewer/attendance-notes/recent" },
  { dir: "case-review", query: "matter_id=1", hub: "/client-viewer/case-review" },
  { dir: "audit-trail", hub: "/client-viewer/audit-trail" },
  { dir: "billing/daily-totals", hub: "/client-viewer/billing/daily-totals" },
  { dir: "clients/concluded-matters", hub: "/client-viewer/concluded-matters" },
  { dir: "clients/flag-counts", hub: "/client-viewer/flag-counts" },
  { dir: "clients/flagged-matters", hub: "/client-viewer/flagged-matters" },
  { dir: "clients/hidden", hub: "/client-viewer/hidden-matters" },
  { dir: "clients/intro-link", query: "matter_id=1", hub: "/client-viewer/intro-link" },
  { dir: "clients/legal-aid", query: "matter_id=1", hub: "/client-viewer/legal-aid" },
  { dir: "clients/matter-court", query: "matter_id=1", hub: "/client-viewer/matter-court" },
  { dir: "clients/ws-candidates", query: "matter_id=9001", hub: "/client-viewer/ws-candidates" },
  { dir: "portal-courts", query: "matter_id=9001", hub: "/client-viewer/portal-courts" },
  { dir: "clients/matter-flags/batch", query: "matter_ids=1,2", hub: "/client-viewer/matter-flags/batch" },
  { dir: "clients/matter-markers", query: "matter_id=1", hub: "/client-viewer/matter-markers" },
  { dir: "clients/matter-milestones", query: "matter_id=1", hub: "/client-viewer/matter-milestones" },
  { dir: "clients/matter-neighbour", query: "matter_id=1&dir=next", hub: "/client-viewer/matter-neighbour" },
  { dir: "clients/matter-summary", query: "matter_id=1", hub: "/client-viewer/matter-summary" },
  { dir: "clients/merge", query: "from=1&into=2", hub: "/client-viewer/clients/merge-preview" },
  { dir: "clients/nearest", query: "matter_id=1", hub: "/client-viewer/nearest" },
  { dir: "clients/duplicates", hub: "/client-viewer/client-duplicates" },
  { dir: "clients/removed", hub: "/client-viewer/removed-clients" },
  { dir: "conflict-check", query: "matter_id=1", hub: "/client-viewer/conflict-check" },
  { dir: "folder-locks", hub: "/client-viewer/folder-locks" },
  { dir: "form-drafts/backup", query: "matter_id=1&form_id=f1", hub: "/client-viewer/form-drafts/backup" },
  { dir: "hearings", query: "from=2026-11-01&to=2026-11-30", hub: "/client-viewer/hearings" },
  { dir: "hearings/history", query: "hearing_id=1", hub: "/client-viewer/hearings/history" },
  { dir: "hearings/leads", hub: "/client-viewer/hearings/leads" },
  { dir: "hearings/request-options", query: "hearing_id=1", hub: "/client-viewer/hearings/request-options" },
  { dir: "hearings/review", hub: "/client-viewer/hearings/review" },
  { dir: "hearings/suggest-matters", query: "hearing_id=1", hub: "/client-viewer/hearings/suggest-matters" },
  { dir: "lexcel", query: "matter_id=1", hub: "/client-viewer/lexcel" },
  { dir: "mail-review", query: "view=decide", hub: "/client-viewer/mail-review/decide" },
  { dir: "mail-review", query: "view=control", hub: "/client-viewer/mail-review/control" },
  { dir: "new-client", hub: "/client-viewer/new-client/categories" },
  { dir: "new-client/pending", hub: "/client-viewer/new-client/pending" },
  { dir: "auto-send", hub: "/client-viewer/auto-send" },
  { dir: "notifications", hub: "/client-viewer/notifications" },
  { dir: "notifications/robot", hub: "/client-viewer/notifications/robot" },
  { dir: "ops-health", hub: "/client-viewer/ops-health" },
  { dir: "system-status", hub: "/client-viewer/system-status" },
  { dir: "storage-status", hub: "/client-viewer/storage-status" },
  { dir: "pipeline", query: "matter_id=1", hub: "/client-viewer/pipeline" },
  { dir: "pipeline/events", query: "matter_id=1", hub: "/client-viewer/pipeline/events" },
  { dir: "pipeline/matter-mode", query: "matter_id=1", hub: "/client-viewer/pipeline/matter-mode" },
  { dir: "pulse", hub: "/client-viewer/pulse" },
  { dir: "robot-notices", hub: "/client-viewer/robot-notices" },
  { dir: "scans", hub: "/client-viewer/scans" },
  { dir: "scans/count", hub: "/client-viewer/scans/count" },
  { dir: "scans/candidates", query: "item_id=i1", hub: "/client-viewer/scans/candidates" },
  { dir: "scans/for-client", query: "matter_id=1", hub: "/client-viewer/scans/for-client" },
  { dir: "settings", hub: "/client-viewer/settings" },
  { dir: "settings/email-classifier", hub: "/client-viewer/settings/email-classifier" },
  { dir: "settings/folder-map", hub: "/client-viewer/settings/folder-map" },
  { dir: "settings/minutes-per-page", hub: "/client-viewer/settings/minutes-per-page" },
  { dir: "settings/models", hub: "/client-viewer/settings/models" },
  { dir: "settings/scanned-docs-folder", hub: "/client-viewer/settings/scanned-docs-folder" },
  { dir: "settings/special-senders", hub: "/client-viewer/settings/special-senders" },
  { dir: "statement-replies", hub: "/client-viewer/statement-replies" },
  { dir: "status-board", hub: "/client-viewer/status-board" },
  { dir: "court-prep", hub: "/client-viewer/court-prep" },
  { dir: "today", hub: "/client-viewer/today" },
  { dir: "todos", query: "view=all&me=Alex", hub: "/client-viewer/todos" },
  { dir: "todos/summary", query: "me=Alex", hub: "/client-viewer/todos/summary" },
  { dir: "virtual-scanner", query: "matter_id=1", hub: "/client-viewer/virtual-scanner" },
  { dir: "whats-new", hub: "/client-viewer/whats-new" },
];

const NOT_CHECKED: Record<string, string> = {
  "audit-folders": "the hub types it as a bare dict, so the contract holds no fields to check; the shape is pinned by tests/test_audit_folder_view.py and lib/auditFolders.test.ts",
  "audit-folders/link": "a redirect to a SharePoint link, not JSON; pinned by app/api/audit-folders/link/route.test.ts and tests/test_audit_folder_view.py",
  "attendance-notes/status": "answers only for a note an earlier POST made (STUB-AN-n)",
  "case-review/export": "binary .docx download; the hub declares no JSON shape",
  "clients/bill-of-costs/export": "CSV download; the hub declares no JSON shape",
  "hearings/ics": "calendar file download",
  "settings/special-sender-logo": "image bytes",
  "virtual-scanner/file": "PDF bytes",
  "virtual-scanner/preview": "image bytes",
};

const KNOWN_DRIFT: Record<string, string[]> = {
  "pipeline": ["$.waiting: the stub sends this field, the hub's response has no such field"],
};

const apiRoot = fileURLToPath(new URL("../app/api", import.meta.url));
function stubbedGetRoutes(): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) walk(join(dir, entry.name));
      else if (entry.name === "route.ts") {
        const src = readFileSync(join(dir, entry.name), "utf8");
        if (src.includes("isStubMode()") && /export\s+(async\s+)?function\s+GET\b/.test(src)) found.push(relative(apiRoot, dir));
      }
    }
  };
  walk(apiRoot);
  return found.sort();
}

beforeEach(() => vi.stubEnv("CASEFORGE_HUB_API_STUB", "1"));
afterEach(() => vi.unstubAllEnvs());

describe("demo stubs match the hub contract (GET routes)", () => {
  it("every stubbed GET route is checked or has a stated reason it is not", () => {
    const covered = new Set([...CASES.map((c) => c.dir), ...Object.keys(NOT_CHECKED)]);
    const missing = stubbedGetRoutes().filter((dir) => !covered.has(dir));
    expect(missing, `stubbed GET routes with no contract case in lib/hubContract.test.ts: ${missing.join(", ")}`).toEqual([]);
  });

  it("every case names a hub route that exists in the contract", () => {
    const keys = new Set(hubRouteKeys());
    const unknown = CASES.filter((c) => !keys.has(`GET ${c.hub}`)).map((c) => `${c.dir} -> GET ${c.hub}`);
    expect(unknown, "hub no longer has these routes (renamed or removed?)").toEqual([]);
  });

  for (const c of CASES) {
    const label = `/api/${c.dir}${c.query ? `?${c.query}` : ""} matches GET ${c.hub}`;
    it(label, async () => {
      const mod = (await (routeModules[`../app/api/${c.dir}/route.ts`] as () => Promise<{ GET: (r: NextRequest) => Promise<Response> }>)());
      const res = await mod.GET(new NextRequest(`http://localhost/api/${c.dir}${c.query ? `?${c.query}` : ""}`));
      expect(res.status, `/api/${c.dir}: the fixture request in lib/hubContract.test.ts was refused by the route`).toBe(200);
      const schema = hubResponseSchema("GET", c.hub);
      expect(schema).toBeDefined();
      const problems = validateAgainstHub(await res.json(), schema!);
      const known = KNOWN_DRIFT[c.dir] ?? [];
      const fresh = problems.filter((p) => !known.includes(p));
      expect(fresh, `/api/${c.dir} (stub) differs from the hub's GET ${c.hub}`).toEqual([]);
      const healed = known.filter((p) => !problems.includes(p));
      expect(healed, `/api/${c.dir}: KNOWN_DRIFT entries that no longer apply, remove them`).toEqual([]);
    });
  }
});
