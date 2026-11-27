import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { acceptAll, acceptPlan, allTicked, namesInWords, pendingWetransfers, tickedToSend, toggleTick } from "./wetransferBanner";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const row = (matter_id: string, client_name: string, wetransfer_pending?: boolean) => ({ matter_id, client_name, wetransfer_pending });

describe("the WeTransfer banner", () => {
  it("lists every client whose WeTransfer waits, once each, by name, and none already given", () => {
    const rows = [row("2", "Bo Example", true), row("1", "Ada Example", true), row("1", "Ada Example", true), row("3", "Cy Example", false), row("4", "Di Example")];
    expect(pendingWetransfers(rows)).toEqual([
      { matterId: "1", name: "Ada Example" },
      { matterId: "2", name: "Bo Example" },
    ]);
    expect(pendingWetransfers(rows, new Set(["1"]))).toEqual([{ matterId: "2", name: "Bo Example" }]);
    expect(pendingWetransfers([])).toEqual([]);
  });
  it("names them in words", () => {
    expect(namesInWords(["Ada"])).toBe("Ada");
    expect(namesInWords(["Ada", "Bo"])).toBe("Ada and Bo");
    expect(namesInWords(["Ada", "Bo", "Cy"])).toBe("Ada, Bo and Cy");
  });
  it("one Accept sends each pending client once, leaving out those given or on their way", () => {
    const pending = [{ matterId: "1", name: "A" }, { matterId: "2", name: "B" }, { matterId: "3", name: "C" }, { matterId: "3", name: "C" }];
    expect(acceptPlan(pending, new Set(["1"]), new Set(["2"]))).toEqual(["3"]);
  });
  it("calls the permission once per client, records success, keeps a failure for another try, and never repeats one", async () => {
    const given = new Set<string>();
    const inFlight = new Set<string>();
    const calls: string[] = [];
    const post = async (id: string) => {
      calls.push(id);
      expect(inFlight.has(id)).toBe(true);
      return id !== "2";
    };
    const first = await acceptAll(["1", "2", "1"], post, given, inFlight);
    expect(first).toEqual({ ok: ["1"], failed: ["2"] });
    expect(calls).toEqual(["1", "2"]);
    expect([...given]).toEqual(["1"]);
    expect(inFlight.size).toBe(0);

    const second = await acceptAll(acceptPlan([{ matterId: "1", name: "A" }, { matterId: "2", name: "B" }], given, inFlight), async () => true, given, inFlight);
    expect(second).toEqual({ ok: ["2"], failed: [] });
  });
  it("a call that throws counts as failed and is not left on its way", async () => {
    const inFlight = new Set<string>();
    const result = await acceptAll(["9"], () => Promise.reject(new Error("down")), new Set(), inFlight);
    expect(result.failed).toEqual(["9"]);
    expect(inFlight.size).toBe(0);
  });
  it("asks client by client: every client starts ticked, any can be unticked, and Yes sends only the ticked ones", async () => {
    const pending = [{ matterId: "1", name: "Ada" }, { matterId: "2", name: "Bo" }, { matterId: "3", name: "Cy" }];
    const ticks = allTicked(pending);
    expect([...ticks]).toEqual(["1", "2", "3"]);
    const unticked = toggleTick(ticks, "2");
    expect(tickedToSend(pending, unticked).map((p) => p.matterId)).toEqual(["1", "3"]);
    expect(toggleTick(unticked, "2").has("2")).toBe(true);

    expect(tickedToSend(pending.slice(0, 1), unticked).map((p) => p.matterId)).toEqual(["1"]);

    const given = new Set<string>();
    await acceptAll(acceptPlan(tickedToSend(pending, unticked), given, new Set()), async () => true, given, new Set());
    expect(pendingWetransfers([row("1", "Ada", true), row("2", "Bo", true), row("3", "Cy", true)], given)).toEqual([{ matterId: "2", name: "Bo" }]);
  });
  it("sits directly under the update banner, opens the board's own question with a tick per client, and uses the existing permission route", () => {
    const page = read("../components/Workspace.tsx");
    expect(page).toMatch(/<UpdateBanner onShowUnsaved=\{showUnsaved\} \/>\s*<WetransferBanner \/>/);
    const banner = read("../components/WetransferBanner.tsx");
    expect(banner).toContain("if (pending.length === 0) return null;");
    expect(banner).toContain("<BoardConfirm");
    expect(banner).toContain('title="Do you grant permission to download the documents from WeTransfer?"');
    expect(banner).toContain("setTicked(allTicked(pending))");
    expect(banner).toContain('type="checkbox"');
    expect(banner).toContain("yesDisabled={count === 0}");
    expect(banner).toContain("acceptPlan(tickedToSend(pending, ticked)");
    expect(banner).not.toMatch(/acceptAll\(\s*acceptPlan\(pending/);
    expect(read("../components/BoardConfirm.tsx")).toContain("disabled={busy || yesDisabled}");
    expect(read("./wetransferBanner.ts")).toContain('fetch("/api/wetransfer-gate"');

    expect(read("../components/StatusBoardCompact.tsx")).toContain("wetransferGiven.has(matterId) || wetransferInFlight.has(matterId)");

    expect(read("./demoWindows.ts")).toContain(".wetransfer-banner");
    expect(read("../app/globals.css")).toMatch(/\.wetransfer-banner \{[\s\S]*?var\(--success\)/);
  });
});
