import { describe, expect, it, vi } from "vitest";
import { backendLabel, changeLine, formatCap, formatCost, formatSeconds, loadModelRoles, resetRoleModel, saveRoleModel, validModelId, validRole } from "./modelRoles";
import { resetStubModelRoles, stubModelRoles, stubResetRole, stubSwapRole } from "./stubModelRoles";

describe("model role formatting", () => {
  it("words time, cost and caps plainly", () => {
    expect(formatSeconds(null)).toBe("none yet");
    expect(formatSeconds(3.14)).toBe("3.1 s");
    expect(formatSeconds(41.5)).toBe("42 s");
    expect(formatCost(0)).toBe("$0");
    expect(formatCost(0.004)).toBe("under $0.01");
    expect(formatCost(1.117)).toBe("$1.12");
    expect(formatCap({ daily_usd: 4, total_usd: null })).toBe("$4.00 a day");
    expect(formatCap({ daily_usd: 10, total_usd: 90 })).toBe("$10.00 a day, $90.00 in all");
    expect(formatCap({ daily_usd: 0, total_usd: null })).toBe("none");
    expect(backendLabel({ backend: "anthropic-direct" })).toBe("Anthropic direct");
  });

  it("accepts only role names and model ids, never free text", () => {
    expect(validRole("case_summary")).toBe(true);
    for (const bad of ["", "Case Summary", "../x", "a b", 5, null]) expect(validRole(bad)).toBe(false);
    expect(validModelId("anthropic/claude-haiku-5.5")).toBe(true);
    for (const bad of ["", "two words", "x".repeat(121), "a;b", "a=b", 7]) expect(validModelId(bad)).toBe(false);
  });

  it("shows old and new in the confirm line", () => {
    expect(changeLine({ purpose: "Drafts letters", model: "a/b" }, "c/d")).toEqual({ purpose: "Drafts letters", from: "a/b", to: "c/d" });
  });
});

describe("the client calls", () => {
  it("treats a failed or odd load as an error", async () => {
    expect(await loadModelRoles(vi.fn().mockResolvedValue(new Response("{}", { status: 500 })))).toEqual({ state: "error" });
    expect(await loadModelRoles(vi.fn().mockResolvedValue(new Response(JSON.stringify({ nope: 1 }))))).toEqual({ state: "error" });
    expect(await loadModelRoles(vi.fn().mockRejectedValue(new Error("x")))).toEqual({ state: "error" });
  });

  it("sends the swap with the model the page showed, and returns the hub's words on a refusal", async () => {
    const ok = vi.fn().mockResolvedValue(new Response("{}"));
    expect(await saveRoleModel("chronology", "a/b", "c/d", ok)).toEqual({ ok: true });
    expect(ok.mock.calls[0][0]).toBe("/api/settings/models");
    expect(JSON.parse(ok.mock.calls[0][1].body)).toEqual({ role: "chronology", model: "a/b", expected_old: "c/d" });
    const refused = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "Plain words" }), { status: 422 }));
    expect(await saveRoleModel("chronology", "a/b", "c/d", refused)).toEqual({ ok: false, message: "Plain words" });
    const reset = vi.fn().mockResolvedValue(new Response("{}"));
    await resetRoleModel("chronology", reset);
    expect(reset.mock.calls[0][0]).toBe("/api/settings/models?role=chronology");
    expect(reset.mock.calls[0][1].method).toBe("DELETE");
  });
});

describe("the stub table", () => {
  it("is realistic: tiers, a locked row, an Anthropic row, and every candidate already in use", () => {
    resetStubModelRoles();
    const view = stubModelRoles(true);
    expect(view.roles.length).toBeGreaterThan(15);
    const used = new Set(view.roles.map((r) => r.model));
    for (const row of view.roles) {
      for (const candidate of row.candidates) expect(used.has(candidate)).toBe(true);
      expect(`${row.purpose}${row.note}${row.retention.text}`).not.toMatch(/--|—/);
    }
    expect(view.roles.find((r) => r.locked)?.candidates).toEqual([]);
    expect(view.roles.find((r) => r.anthropic_direct)?.retention.status).toBe("direct");
    expect(view.roles.find((r) => r.role === "vision")?.swappable).toBe(false);
  });

  it("swaps in memory only to a candidate, refuses the rest and resets", () => {
    resetStubModelRoles();
    expect(stubSwapRole("case_summary", "free/text", "", true)).toMatchObject({ ok: false, status: 422 });
    expect(stubSwapRole("case_summary", "anthropic/claude-haiku-5.5", "", false)).toMatchObject({ ok: false, status: 403 });
    expect(stubSwapRole("mail_triage", "x/y", "", true)).toMatchObject({ ok: false, status: 409 });
    expect(stubSwapRole("case_summary", "anthropic/claude-haiku-5.5", "wrong/old", true)).toMatchObject({ ok: false, status: 409 });
    const done = stubSwapRole("case_summary", "anthropic/claude-haiku-5.5", "", true);
    expect(done).toMatchObject({ ok: true });
    expect(stubModelRoles(true).roles.find((r) => r.role === "case_summary")).toMatchObject({ overridden: true, source: "override" });
    expect(stubResetRole("case_summary", true)).toMatchObject({ ok: true });
    expect(stubResetRole("case_summary", true)).toMatchObject({ ok: false, status: 422 });
    resetStubModelRoles();
  });
});
