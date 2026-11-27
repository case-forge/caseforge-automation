import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { AUTO_SEND_DRAFT_KINDS, EACH_STEPS, GAME_NOT_ASSIGNED, HUB_MAP, draftAutoSends, ONCE_STEPS, gameEvents, gamePipeline, hubStepFor, hubStepState, isGameClientId, lockedGamePipeline } from "./gameFlow";
import type { DemoCard, DemoEvent } from "./gameFlow";
import { PIPELINE_STEP_KEYS, stepRef } from "./pipelineTypes";
import type { Pipeline, PipelineStepKey } from "./pipelineTypes";
import { STUB_MADE_FIRST_ID } from "./stubClients";

const card = (over: Partial<DemoCard> = {}): DemoCard => ({
  id: "email-1",
  name: "Rosa Onyxtest",
  column: "folders",
  waiting: false,
  assignedTo: 2,
  assignedName: "Sam",
  closedAs: null,
  active: true,
  step: "create-folder",
  draft: null,
  round: 1,
  rounds: 2,
  revision: 0,
  matterId: "9100",
  ...over,
});

const flow = (c: DemoCard, events: DemoEvent[] = [], mode: "auto" | "manual" = "auto"): Pipeline => gamePipeline({ card: c, events, mode, setting: "inherit" });
const step = (p: Pipeline, key: PipelineStepKey) => p.steps.find((s) => s.key === key)!;

describe("which clients are the game's", () => {
  it("starts at the first id the demo gives a client it makes", () => {
    expect(isGameClientId(String(STUB_MADE_FIRST_ID))).toBe(true);
    expect(isGameClientId(String(STUB_MADE_FIRST_ID - 1))).toBe(false);
    expect(isGameClientId("9001")).toBe(false);
    expect(isGameClientId("x9100")).toBe(false);
  });
});

const DRAFT_STEPS = [
  "client-email",
  "save-client-docs",
  "court-email",
  "order-client",
  "process-server-request",
  "counsel-request",
  "brief-counsel",
  "court-bundle",
  "post-order-client",
  "post-process-server",
];

describe("the mapping", () => {
  it("gives every game step to a hub step, and every hub step is shown", () => {
    for (const game of [...ONCE_STEPS, ...EACH_STEPS]) {
      if (game === "assign-case") continue;
      expect(hubStepFor(game), game).not.toBe("");
    }
    expect(flow(card()).steps.map((s) => s.key)).toEqual(PIPELINE_STEP_KEYS);
  });

  it("leaves exactly one step for a person to press whatever the game is at, and Send only where a draft waits", () => {
    for (const game of [...ONCE_STEPS, ...EACH_STEPS]) {
      if (game === "assign-case") continue;
      for (const round of [1, 2, 3]) {
        if (ONCE_STEPS.includes(game) && round > 1) continue;
        const idle = flow(card({ step: game, round, rounds: 3 }));
        const press = idle.steps.filter((s) => s.can_run || s.can_send);
        expect(press.length, `${game} round ${round}`).toBe(1);
        if (!DRAFT_STEPS.includes(game)) continue;
        const waiting = flow(card({ step: game, round, rounds: 3, draft: { type: "client", subject: "Subject", to: "a@b.test" } }));
        const sends = waiting.steps.filter((s) => s.can_send);
        expect(sends.length, `${game} draft`).toBe(1);
        expect(waiting.steps.filter((s) => s.can_run).length, `${game} draft run`).toBe(0);
      }
    }
  });
});

describe("a case just assigned", () => {
  const p = flow(card());
  it("has the sign-up done and the folder next", () => {
    expect(step(p, "record").status).toBe("done");
    expect(step(p, "folder").status).toBe("todo");
    expect(step(p, "folder").can_run).toBe(true);
    expect(step(p, "folder").actor).toBe("case flow");
  });
  it("holds the rest back and says what it waits for", () => {
    const statement = step(p, "statement");
    expect(statement.status).toBe("blocked");
    expect(statement.can_run).toBe(false);
    expect(statement.summary).toBe(`Waiting for ${stepRef("folder")}.`);
  });
  it("calls a step a person's when the firm is on Manual", () => {
    expect(step(flow(card(), [], "manual"), "folder").actor).toBe("you");
  });
  it("marks the steps the game has no counterpart for as not needed", () => {
    for (const key of ["serve_other", "sos_to_court", "ccl"] as PipelineStepKey[]) {
      expect(step(p, key).status).toBe("not_needed");
      expect(step(p, key).can_run).toBe(false);
    }
  });
  it("shows only game steps, with nothing for the hub's forms", () => {
    expect(p.steps.every((s) => s.game === true && s.resettable === false)).toBe(true);
  });
});

describe("a case that is not assigned or is closed", () => {
  it("is locked until it is assigned", () => {
    const p = flow(card({ assignedTo: null, assignedName: null, step: "assign-case" }));
    expect(p.locked).toBe(true);
    expect(p.lock_reason).toBe(GAME_NOT_ASSIGNED);
    expect(p.steps.some((s) => s.can_run || s.can_send)).toBe(false);
  });
  it("is locked when closed", () => {
    const p = flow(card({ closedAs: "dropped-out", step: "extract-zip" }));
    expect(p.locked).toBe(true);
    expect(p.lock_reason).toContain("dropped out");
    expect(p.steps.some((s) => s.can_run)).toBe(false);
  });
});

describe("a draft waiting for a person", () => {
  const events: DemoEvent[] = [{ at: "2026-10-17T10:00:00Z", step: "client-email", kind: "auto", label: 'Made 2 documents. Drafted "Letter" with 2 documents attached. Nothing has been sent.' }];
  const waiting = card({ step: "client-email", waiting: true, draft: { type: "court", subject: "Application", to: "court@example.test" } });
  const p = flow(waiting, events);

  it("has the statement done and the email needing attention, with Send", () => {
    expect(step(p, "statement").status).toBe("done");
    const email = step(p, "email");
    expect(email.status).toBe("attention");
    expect(email.actor).toBe("you");
    expect(email.can_send).toBe(true);
    expect(email.send_label).toBe("Send email");
    expect(email.can_run).toBe(false);
    expect(email.summary).toContain("Waiting for you to send it");
  });
  it("is Run, not Send, once the email has been sent and the sent copy is to be filed", () => {
    const sent = flow(card({ step: "client-email" }), events);
    expect(step(sent, "email").can_run).toBe(true);
    expect(step(sent, "email").can_send).toBeFalsy();
    expect(step(sent, "statement").status).toBe("done");
  });
  it("is the statement's run before the draft is made", () => {
    const before = flow(card({ step: "client-email" }), []);
    expect(step(before, "statement").status).toBe("todo");
    expect(step(before, "statement").can_run).toBe(true);
    expect(step(before, "email").status).toBe("blocked");
  });
  it("has no send button while the lock is on", () => {
    expect(flow({ ...waiting, assignedTo: null }, events).steps.some((s) => s.can_send)).toBe(false);
  });
});

describe("the client asks for changes to the statement", () => {
  it("shows a revision draft as the client wanting changes", () => {
    const p = flow(card({ step: "save-client-docs", revision: 1, draft: { type: "revision-2", subject: "Revised statement for approval (changes 2)", to: "r@e.test" } }));
    const email = step(p, "email");
    expect(email.status).toBe("attention");
    expect(email.can_send).toBe(true);
    expect(email.summary).toContain("asked for changes to the statement");
    expect(email.detail.join(" ")).toContain("Statement changes asked for so far: 1");
    expect(step(p, "court_pack").status).toBe("blocked");
  });
  it("keeps the email step open while the client's reply is being filed", () => {
    const p = flow(card({ step: "print-client-response", revision: 2 }));
    expect(step(p, "email").status).toBe("todo");
    expect(step(p, "email").can_run).toBe(true);
    expect(step(p, "email").summary).toContain("2 times");
  });
});

describe("later hearings and the end", () => {
  it("treats the once-only steps as done and the hearing's steps as to do again", () => {
    const p = flow(card({ step: "brief-counsel", round: 2, rounds: 3 }));
    for (const key of ["folder", "email", "court_email", "court_reply", "client_papers", "book_counsel", "serve"] as PipelineStepKey[]) {
      expect(step(p, key).status, key).toBe("done");
    }
    expect(step(p, "brief").status).toBe("todo");
    expect(step(p, "brief").can_run).toBe(true);
    expect(step(p, "brief").label).toContain("hearing 2 of 3");
    expect(step(p, "bundle").status).toBe("blocked");
    expect(step(p, "closing_letter").status).toBe("blocked");
  });
  it("lets the next hearing start from the last step of a hearing before the final one", () => {
    const p = flow(card({ step: "advance-hearing", round: 2, rounds: 3 }));
    expect(step(p, "closing_letter").can_run).toBe(true);
    expect(step(p, "mid_letter").status).toBe("done");
  });
  it("is done from end to end once the game has finished the case", () => {
    const p = flow(card({ step: null, round: 3, rounds: 3, column: "concluded" }));
    const open = p.steps.filter((s) => s.status !== "done" && s.status !== "not_needed");
    expect(open).toEqual([]);
    expect(step(p, "closing_letter").status).toBe("done");
    expect(p.steps.some((s) => s.can_run)).toBe(false);
  });
  it("judges the statement of service by the part the case has not passed", () => {
    const early = hubStepState("sos_received", card({ step: "counsel-request" }), []);
    expect(early.status).toBe("blocked");
    const during = hubStepState("sos_received", card({ step: "process-server-invoice" }), []);
    expect(during).toEqual({ status: "todo", owner: true });
    const between = hubStepState("sos_received", card({ step: "brief-counsel" }), []);
    expect(between.status).toBe("blocked");
    const after = hubStepState("sos_received", card({ step: "print-post-process-server-invoice", round: 2, rounds: 3 }), []);
    expect(after.owner).toBe(true);
  });
});

describe("modes and the log", () => {
  it("reports the mode this client is in", () => {
    const own = gamePipeline({ card: card(), events: [], mode: "auto", setting: "manual", setBy: "Sam", setAt: "2026-10-17T10:00:00Z" });
    expect(own.effective_mode).toBe("manual");
    expect(own.mode).toBe("auto");
    expect(own.matter_mode_by).toBe("Sam");
  });
  it("turns the game's log into Activity log lines by step, kind and who", () => {
    const events: DemoEvent[] = [
      { at: "2026-10-17T10:00:00Z", step: "create-folder", kind: "auto", label: "Set up the folder." },
      { at: "2026-10-17T10:01:00Z", step: "client-email", kind: "human", label: "Read the draft, then press Send." },
      { at: "2026-10-17T10:02:00Z", step: "extract-zip", kind: "stuck", label: "The zip could not be unpacked." },
    ];
    const lines = gameEvents(card(), events, "auto");
    expect(lines.map((l) => [l.step, l.status, l.by])).toEqual([
      ["folder", "ok", "Case flow"],
      ["email", "waiting", "Sam"],
      ["folder", "failed", "Case flow"],
    ]);
    expect(lines.map((l) => l.created_utc)).toEqual(events.map((e) => e.at));
    expect(new Set(lines.map((l) => l.event_id)).size).toBe(3);
  });
  it("has a locked pipeline for when the game cannot be reached", () => {
    const p = lockedGamePipeline("9100", "", "Open the demo windows (the DEMO button) to run this client's Case Flow.", "auto", "inherit");
    expect(p.locked).toBe(true);
    expect(p.steps).toHaveLength(HUB_MAP ? PIPELINE_STEP_KEYS.length : 0);
    expect(p.steps.some((s) => s.can_run)).toBe(false);
  });
});

describe("auto-send regardless of mode, as the production send gate does", () => {

  const policyPath = fileURLToPath(new URL("../../../deploy/azure/mail-send-gate/policy.json", import.meta.url));
  const policy = existsSync(policyPath) ? JSON.parse(readFileSync(policyPath, "utf8")) : null;
  const draft = (type: string) => ({ type, subject: "S", to: "x@example.test" });

  it("treats the statement pack, its e-signature link and the revised statement as safelist", () => {
    for (const type of ["client", "docusign", "revision-1", "revision-3"]) expect(draftAutoSends(draft(type)), type).toBe(true);
    if (policy) {
      expect(policy.classes["statement-to-client"]).toBeTruthy();
      expect(policy.classes["amended-statement-for-signature"]).toBeTruthy();
    }
  });

  it("sends every draft itself in Auto, after a pause, and only the safelist in Manual", () => {
    const app = readFileSync(fileURLToPath(new URL("../../training-engine/public/app.js", import.meta.url)), "utf8");

    expect(app).toMatch(/if \(!safelist && !autoRun\) return null;/);
    expect(app).toMatch(/const AUTO_READ_PAUSE_MS = \d{4};/);
  });

  it("shows every other draft as waiting for a person while it is on screen, in Manual and in Auto", () => {
    for (const type of ["court", "order-client", "process-server", "counsel", "brief-counsel-1", "court-bundle-2", "post-order-client-1", "post-process-server-1"]) {
      expect(draftAutoSends(draft(type)), type).toBe(false);
      const waiting = card({ step: "court-email", waiting: true, draft: draft(type) });
      for (const mode of ["manual", "auto"] as const) {
        const email = step(flow(waiting, [], mode), "email");
        const any = flow(waiting, [], mode).steps.find((s) => s.can_send)!;
        expect(any.can_send, `${type} ${mode}`).toBe(true);
        expect(any.summary).toContain("Waiting for you to send it");
        expect(email).toBeTruthy();
      }
    }
    expect(draftAutoSends(null)).toBe(false);
  });

  it("says a safelist draft is sent automatically in Manual too", () => {
    const c = card({ step: "client-email", waiting: true, draft: draft("client") });
    const p = flow(c, [], "manual");
    expect(step(p, "email").summary).toContain("Sent automatically");
  });

  it("keeps the CRM list and the game's own list the same", () => {
    const app = readFileSync(fileURLToPath(new URL("../../training-engine/public/app.js", import.meta.url)), "utf8");
    const m = /const AUTO_SEND_DRAFT_KINDS = (\[[^\]]*\]);/.exec(app);
    expect(m).not.toBeNull();
    expect(JSON.parse(m![1])).toEqual([...AUTO_SEND_DRAFT_KINDS]);
  });

  it("has one Auto | Manual pill in the Inbox heading, tied to the CRM's firm mode", () => {
    const app = readFileSync(fileURLToPath(new URL("../../training-engine/public/app.js", import.meta.url)), "utf8");
    expect(app).toContain('modePill.className = "mode-pill"');

    expect(app).toContain('document.createElement("button")');
    expect(app).toContain('setAttribute("role", "switch")');
    expect(app).toContain('aria-hidden="true">Auto</span>');
    expect(app).toContain('aria-hidden="true">Manual</span>');
    expect(app).toContain('Click to switch to');
    expect(app).toContain('"aria-checked"');
    expect(app).toContain('[data-window="inbox"] .panel-title');
    expect(app).toContain('new CustomEvent("training-demo-mode"');
    expect(app).toMatch(/setAuto\(on\) \{[^}]*paintModePill\(\)/);
    const bridge = readFileSync(fileURLToPath(new URL("./demoBridge.ts", import.meta.url)), "utf8");
    expect(bridge).toContain('addEventListener("training-demo-mode"');
  });

  it("no longer tells the trainee that Case flow never sends an email, or that a person sends the statement", () => {
    const engine = readFileSync(fileURLToPath(new URL("../../training-engine/engine/engine.gen.js", import.meta.url)), "utf8");
    expect(engine).not.toContain("It never sends");
    expect(engine).not.toContain("never sends an email by itself");
    expect(engine).toContain("sent automatically, in Auto or Manual");
  });
});
