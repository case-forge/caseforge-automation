import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { alreadyScanned, lastOrderLine, longDate, measuredWords, scanBlockedReason, ukShortDate } from "./virtualScannerTypes";
import type { CommonDocument, VirtualScan } from "./virtualScannerTypes";
import { stubAddTitle, stubPdf, stubScan, stubScanOrder, stubRemoveTitle, stubUndo, stubVirtualScanner } from "./stubVirtualScanner";
import { DEMO_FIRM } from "./stubFirm";
import { GET as viewRoute } from "../app/api/virtual-scanner/route";
import { GET as fileRoute } from "../app/api/virtual-scanner/file/route";
import { GET as previewRoute } from "../app/api/virtual-scanner/preview/route";
import { POST as scanRoute } from "../app/api/virtual-scanner/scan/route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const today = () => stubVirtualScanner("9001").today;
const doc = (over: Partial<CommonDocument> = {}): CommonDocument => ({
  document_id: "d1", title: "Leaflet", file_name: "Leaflet.pdf", has_file: true, also_named: [], web_url: "", added_by: "", ...over,
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("the Scanner tab", () => {
  it("is its own tab on the extra-details page, before Billing, keyed by matter", () => {
    const detail = read("../components/DetailPanel.tsx");
    const tabs = detail.slice(detail.indexOf("const EXTRA_TABS"), detail.indexOf("interface CaseTab"));
    expect(tabs).toMatch(/\["scanner", "Scanner"\],\s*\["billing", "Billing"\]/);
    expect(detail).toContain('detailTab === "scanner" && matterId && <ScannerTab key={matterId} matterId={matterId} />');
  });

  it("never stamps or alters a document", () => {
    const tab = read("../components/ScannerTab.tsx");
    expect(tab).not.toMatch(/seal|stamp\(/i);
  });

  it("shows View as a picture of page 1, not the whole PDF, with the whole PDF a new-tab link away", () => {
    const tab = read("../components/ScannerTab.tsx");
    expect(tab).not.toContain("<iframe");
    const preview = tab.slice(tab.indexOf("function StockPreview"), tab.indexOf("export function ScannerTab"));
    expect(preview).toContain("src={virtualScannerPreviewUrl(doc.document_id)}");
    expect(preview).toMatch(/width=\{PREVIEW_WIDTH\}\s+height=\{PREVIEW_HEIGHT\}/);
    expect(preview).toContain('loading="lazy"');
    expect(preview).toContain("alt={`First page of ${doc.title}`}");
    expect(preview).toContain('aria-busy={state === "loading"}');
    expect(preview).toMatch(/href=\{virtualScannerFileUrl\(doc\.document_id\)\} target="_blank" rel="noopener noreferrer"/);
    expect(preview).toContain("Open the whole document");
    expect(preview).toContain("(opens in a new tab)");
    expect(preview).toContain('role="alert"');
  });

  it("draws the page as paper: a lift, never an outline", () => {
    const css = read("../app/vscan.css");
    const page = css.slice(css.indexOf(".vscan-page {"), css.indexOf("}", css.indexOf(".vscan-page {")));
    expect(page).toContain("box-shadow: var(--box-lift)");
    expect(page).not.toMatch(/border:/);
    expect(css).toMatch(/prefers-reduced-motion: reduce\) \{ \.vscan-page/);
  });
});

describe("helpers", () => {
  it("formats dates and measurements in words, unknown when not measured", () => {
    expect(ukShortDate("2026-10-15")).toBe("15.10.26");
    expect(measuredWords({ pages: 2, text_chars: 3725 })).toBe("2 pages, 3,725 characters");
    expect(measuredWords({ pages: null, text_chars: null })).toBe("pages unknown, characters unknown");
  });

  it("says why Scan is disabled", () => {
    const ok = { can_scan: true, refusal: "" };
    expect(scanBlockedReason(ok, doc(), "2026-10-15", "2026-10-16")).toBe("");
    expect(scanBlockedReason(ok, doc({ has_file: false }), "2026-10-15", "2026-10-16")).toBe("No stock copy yet.");
    expect(scanBlockedReason(ok, doc(), "2026-10-17", "2026-10-16")).toMatch(/after today/);
    expect(scanBlockedReason({ can_scan: false, refusal: "read only" }, doc(), "2026-10-15", "2026-10-16")).toBe("read only");
  });

  it("finds an earlier filed scan for the same document and date only", () => {
    const p = { document_id: "d1", date_received: "2026-10-15", status: "filed" } as VirtualScan;
    expect(alreadyScanned([p], "d1", "2026-10-15")).toBe(p);
    expect(alreadyScanned([{ ...p, status: "undone" }], "d1", "2026-10-15")).toBeUndefined();
    expect(alreadyScanned([p], "d1", "2026-10-14")).toBeUndefined();
  });
});

describe("last order and waiting-scan hints", () => {
  it("says where the date came from, and which hearing a notice is for", () => {
    const view = stubVirtualScanner("9001");
    expect(lastOrderLine(view.last_order!)).toBe("Order: 4 Aug 2026, from the file name");
    expect(view.orders_expected.map((o) => o.line)).toEqual(["Hearing 10 Sep 2026: no order filed yet"]);
    expect(view.scan_hints[0].line).toBe("Probably this client, likely the order from the hearing on 10 Sep 2026");
    expect(view.scan_hints[0].label).toMatch(/guess.*not checked/);
    expect(lastOrderLine(stubVirtualScanner("9002").last_order!)).toBe("Notice of hearing (for the hearing on 10 Sep 2026): 20 Aug 2026, the upload date");
    const none = stubVirtualScanner("9004");
    expect([none.last_order, none.orders_expected, none.scan_hints]).toEqual([null, [], []]);
  });

  it("offers no button that files or moves a waiting scan", () => {
    const tab = read("../components/ScannerTab.tsx");
    const hints = tab.slice(tab.indexOf('aria-label="Last order"'), tab.indexOf('aria-label="Scan order"'));
    expect(hints.length).toBeGreaterThan(100);
    expect(hints).not.toContain("<button");
    expect(longDate("2026-09-10")).toBe("10 Sep 2026");
  });
});

describe("Scan order", () => {
  it("records once, asks twice when an emailed reply is filed, and is refused in the read-only book", () => {
    const aug = stubVirtualScanner("9001").orders[0];
    const first = stubScanOrder("9001", aug.folder, aug.name, false);
    expect(first.ok).toBe(true);
    expect(stubVirtualScanner("9001").orders[0].recorded).toBe(true);
    expect(stubScanOrder("9001", aug.folder, aug.name, false).message).toMatch(/already recorded/);
    const oct = stubVirtualScanner("9003").orders[0];
    const warned = stubScanOrder("9003", oct.folder, oct.name, false);
    expect(warned).toMatchObject({ ok: false, needs_confirm: true });
    expect(stubScanOrder("9003", oct.folder, oct.name, true).ok).toBe(true);
    const nmo = stubVirtualScanner("9002").orders[0];
    expect(stubScanOrder("9002", nmo.folder, nmo.name, false)).toMatchObject({ ok: true, needs_confirm: false });
  });

  it("asks before a second run and posts the picked order to its route", () => {
    const tab = read("../components/ScannerTab.tsx");
    expect(tab).toContain("out.needs_confirm && window.confirm(");
    expect(read("./virtualScanner.ts")).toContain('"/api/scanner/scan-order"');
  });
});

describe("stub mode walks every state", () => {
  it("9003 has an empty catalogue; 9002 in NMO-CAO scans like any other client but cannot undo", () => {
    expect(stubVirtualScanner("9003").documents).toEqual([]);
    const nmo = stubVirtualScanner("9002");
    expect(nmo.can_scan).toBe(true);
    expect(nmo.refusal).toBe("");
    const filed = stubScan("9002", "stub-fjypb", today(), "Tester");
    if ("error" in filed) throw new Error(filed.error);
    expect(filed.file_name).toMatch(/^FJYPB Top Tips for Parents \d\d\.\d\d\.\d\d - STUBPERSON\.pdf$/);
    const undo = stubUndo(filed.scan_id, "Tester");
    expect("error" in undo && undo.error).toContain(DEMO_FIRM.folders.read_only_book);
  });

  it("a title without a file cannot scan; a taken name gets (2); a rescan bills nothing; undo then rescan reuses the charge", () => {
    const view = stubVirtualScanner("9001");
    const titleOnly = view.documents.find((d) => !d.has_file)!;
    expect("error" in stubScan("9001", titleOnly.document_id, today(), "Tester")).toBe(true);
    const first = stubScan("9001", "stub-pn", today(), "Tester");
    if ("error" in first) throw new Error(first.error);
    expect(first.file_name).toMatch(/^Family Court Privacy Notice \d\d\.\d\d\.\d\d \(2\) - TESTPERSON\.pdf$/);
    expect(first.billing_note).toMatch(/Rate TBC/);
    const again = stubScan("9001", "stub-pn", today(), "Tester");
    if ("error" in again) throw new Error(again.error);
    expect(again.already).toBe(true);
    expect(stubVirtualScanner("9001").scans).toHaveLength(1);
    const undone = stubUndo(first.scan_id, "Tester");
    if ("error" in undone) throw new Error(undone.error);
    expect(undone.status).toBe("undone");
    const rescan = stubScan("9001", "stub-pn", today(), "Tester");
    if ("error" in rescan) throw new Error(rescan.error);
    expect(rescan.billing_item_id).toBe(first.billing_item_id);
  });

  it("adds and removes a typed title, refusing a duplicate", () => {
    const added = stubAddTitle("A new leaflet", "Tester");
    if ("error" in added) throw new Error(added.error);
    expect("error" in stubAddTitle("a new leaflet", "Tester")).toBe(true);
    expect(stubRemoveTitle(`t:${added.title_id}`)).toEqual({ removed: true });
  });

  it("serves a PDF for the viewer", () => {
    expect(new TextDecoder().decode(stubPdf()).startsWith("%PDF-1.4")).toBe(true);
  });

  it("gives every scan its own id, even two matters scanned in the same millisecond", () => {
    const spy = vi.spyOn(Date, "now").mockReturnValue(Date.UTC(2026, 9, 21, 12));
    try {
      const a = stubScan("9201", "stub-fjypb", today(), "Tester");
      const b = stubScan("9202", "stub-fjypb", today(), "Tester");
      if ("error" in a || "error" in b) throw new Error("scan failed");
      expect(a.scan_id).not.toBe(b.scan_id);
      const undone = stubUndo(b.scan_id, "Tester");
      expect("error" in undone).toBe(false);
    } finally {
      spy.mockRestore();
    }
  });
});

describe("routes", () => {
  it("answer from the stub", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const view = await (await viewRoute(new NextRequest("http://localhost/api/virtual-scanner?matter_id=9001"))).json();
    expect(view.documents.length).toBeGreaterThan(0);
    const pdf = await fileRoute(new NextRequest("http://localhost/api/virtual-scanner/file?document_id=stub-pn"));
    expect(pdf.headers.get("content-type")).toBe("application/pdf");
    const picture = await previewRoute(new NextRequest("http://localhost/api/virtual-scanner/preview?document_id=stub-pn"));
    expect(picture.headers.get("content-type")).toBe("image/svg+xml");
    expect(await picture.text()).toContain("<svg");
    expect((await previewRoute(new NextRequest("http://localhost/api/virtual-scanner/preview"))).status).toBe(400);
    expect((await previewRoute(new NextRequest("http://localhost/api/virtual-scanner/preview?document_id=t:stub-private-law"))).status).toBe(404);
    const refused = await scanRoute(new NextRequest("http://localhost/api/virtual-scanner/scan", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ matter_id: "9001", document_id: "t:stub-private-law", date_received: view.today }),
    }));
    expect(refused.status).toBe(422);
  });

  it("forward a scan to the hub without leaking the token", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ scan_id: "p1", message: "Filed" })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await scanRoute(new NextRequest("http://localhost/api/virtual-scanner/scan", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ matter_id: "501", document_id: "abc", date_received: "2026-10-15" }),
    }));
    expect(res.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/virtual-scanner/scan");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ matter_id: "501", document_id: "abc", date_received: "2026-10-15", by: "tailnet", copies: 1 });
    expect(await res.text()).not.toContain("test-token-not-a-real-secret");
  });

  it("forward a preview to the hub's preview route and pass the picture through", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Uint8Array([0xff, 0xd8, 0xff]), { headers: { "content-type": "image/jpeg" } }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await previewRoute(new NextRequest("http://localhost/api/virtual-scanner/preview?document_id=abc"));
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("image/jpeg");
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/virtual-scanner/preview?document_id=abc");
  });

  it("refuse a malformed date before reaching the hub", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const res = await scanRoute(new NextRequest("http://localhost/api/virtual-scanner/scan", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ matter_id: "9001", document_id: "stub-pn", date_received: "15/10/2026" }),
    }));
    expect(res.status).toBe(400);
  });
});
