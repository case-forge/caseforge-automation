import { describe, expect, it } from "vitest";
import { OUTAGE_LOGOS } from "./outageLogos";
import { CAPABILITIES, LINE_ICONS, SERVICES, capabilityResults, capabilityState, isDown, layout, liveDownFromStatus, telegramCards, wiring } from "./outageMap";
import { stubSystemStatus } from "./stubSystemStatus";

const none = new Set<string>();
const state = (name: string, off: string[]) => capabilityState(CAPABILITIES.find((c) => c.name === name)!, new Set(off)).state;

describe("outage map wiring", () => {
  it("has one hub, unique ids, and every need, path step, wire and icon resolves", () => {
    const ids = new Set(SERVICES.map((s) => s.id));
    expect(ids.size).toBe(SERVICES.length);
    expect(SERVICES.filter((s) => s.ring === 0)).toHaveLength(1);
    for (const s of SERVICES) {
      s.needs.forEach((n) => expect(ids.has(n), `${s.id} needs ${n}`).toBe(true));
      expect(Boolean(s.logo ? OUTAGE_LOGOS[s.logo] : LINE_ICONS[s.line ?? ""]), `${s.id} icon`).toBe(true);
    }
    for (const c of CAPABILITIES) c.paths.flat().forEach((id) => expect(ids.has(id), `${c.name}: ${id}`).toBe(true));
    for (const [a, b] of wiring()) expect(ids.has(a) && ids.has(b)).toBe(true);
    expect(layout()).toHaveLength(SERVICES.length);
  });

  it("everything works when nothing is down", () => {
    expect(capabilityResults(none).every((r) => r.state === "ok")).toBe(true);
  });

  it("a service is down when what it needs is down", () => {
    expect(isDown("mail", new Set(["entra"]))).toBe(true);
    expect(isDown("entra", new Set(["mail"]))).toBe(false);
    expect(isDown("crm", new Set(["prod"]))).toBe(true);
  });
});

describe("outage map consequences", () => {
  it("a Microsoft outage stops mail and folders and limits CRM sign-in to the private network", () => {
    expect(state("Emails are drafted into the mailbox", ["entra"])).toBe("bad");
    expect(state("Client folders are read and filed to", ["entra"])).toBe("bad");
    expect(state("Someone signs in to the CRM afresh", ["entra"])).toBe("warn");
    expect(state("Staff already signed in use the CRM", ["entra"])).toBe("ok");
  });

  it("losing Resend limits signing, losing the vault warns not to restart", () => {
    expect(state("Clients sign documents", ["resend"])).toBe("warn");
    const vault = capabilityResults(new Set(["kv"])).find((r) => r.cap.name === "A restarted service gets its secrets")!;
    expect(vault.state).toBe("bad");
    expect(vault.why).toContain("Do not restart or reboot anything");
  });

  it("lists what stops before what is limited before what works", () => {
    const order = capabilityResults(new Set(["entra"])).map((r) => r.state);
    expect(order).toEqual([...order].sort((a, b) => ({ bad: 0, warn: 1, ok: 2 })[a] - ({ bad: 0, warn: 1, ok: 2 })[b]));
  });
});

describe("outage map Telegram", () => {
  it("says nothing is wrong when nothing is down", () => {
    expect(telegramCards(none)).toEqual([{ bot: "No message", route: "none", routeText: "Everything running", text: "" }]);
  });

  it("pages from the dev bot for the production box and holds the ops bot", () => {
    const cards = telegramCards(new Set(["prod"]));
    expect(cards.map((c) => [c.bot, c.route])).toEqual([["caseforge_dev_bot", "page"]]);
    expect(cards[0].text).toContain("DOWN: Production");
  });

  it("goes to the ops digest for a mailbox outage, and is silent when Telegram itself is down", () => {
    expect(telegramCards(new Set(["mail"]))[0]).toMatchObject({ bot: "caseforge_counsel_bot", route: "digest" });
    expect(telegramCards(new Set(["tg", "mail"]))[0].routeText).toBe("Telegram is down");
  });

  it("never names a client", () => {
    for (const s of SERVICES) expect(telegramCards(new Set([s.id])).map((c) => c.text).join(" ")).not.toMatch(/client name|matter/i);
  });
});

describe("outage map live state", () => {
  it("switches off a service its provider declares in outage, and says why", () => {
    const status = stubSystemStatus();
    status.services = undefined;
    expect(liveDownFromStatus(status).ids).toEqual([]);
    const github = status.providers.providers.find((p) => p.key === "github")!;
    github.state = "outage";
    github.title = "Actions is down";
    const live = liveDownFromStatus(status);
    expect(live.ids).toEqual(["gh"]);
    expect(live.reasons.gh).toBe("GitHub declares an outage: Actions is down.");
    github.state = "unknown";
    expect(liveDownFromStatus(status).ids).toEqual([]);
    expect(liveDownFromStatus(null)).toEqual({ ids: [], reasons: {} });
  });

  it("switches off a service the production box's own probes find down, with the reason and since when", () => {
    const live = liveDownFromStatus(stubSystemStatus());
    expect(live.ids).toEqual(["glitch"]);
    expect(live.reasons.glitch).toContain("health page is not running at all");
    expect(live.reasons.glitch).toMatch(/Since /);
  });

  it("never treats an unknown probe, an old snapshot or an unmapped key as an outage", () => {
    const status = stubSystemStatus();
    status.services!.services.find((s) => s.key === "glitch")!.state = "unknown";
    expect(liveDownFromStatus(status).ids).toEqual([]);
    status.services!.services.find((s) => s.key === "glitch")!.state = "down";
    status.services!.services.push({ key: "nonsense", state: "down", reason: "x", since: "" });
    expect(liveDownFromStatus(status).ids).toEqual(["glitch"]);
    status.services!.stale = true;
    expect(liveDownFromStatus(status).ids).toEqual([]);
  });

  it("a probed service going down stops what depends on it on the map", () => {
    expect(capabilityResults(new Set(liveDownFromStatus(stubSystemStatus()).ids)).find((r) => r.cap.name === "Errors are recorded")?.state).toBe("bad");
  });
});
