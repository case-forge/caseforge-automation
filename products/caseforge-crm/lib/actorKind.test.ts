import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { actorKindWord, isActorKind } from "./actorKind";

describe("actor kind", () => {
  it("is a word for each of the three kinds and nothing for an unrecorded one", () => {
    expect(actorKindWord("person")).toBe("Person");
    expect(actorKindWord("agent")).toBe("Agent");
    expect(actorKindWord("automation")).toBe("Automation");
    expect(actorKindWord("")).toBe("");
    expect(actorKindWord("human")).toBe("");
    expect(actorKindWord(undefined)).toBe("");
    expect(isActorKind("robot")).toBe(false);
  });

  it("dark words for all three; the icon is green, yellow or red from existing tokens (owner, 2026-11-16)", () => {
    const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf8");
    const rules = css.slice(css.indexOf(".actor-kind {"), css.indexOf(".actor-kind--automation .actor-kind-icon"));
    const word = rules.slice(0, rules.indexOf("}"));
    expect(word).toContain("color: var(--fg);");
    expect(rules).not.toMatch(/gradient/);
    expect(css).toMatch(/\.actor-kind--person \.actor-kind-icon \{ color: var\(--success\); \}/);
    expect(css).toMatch(/\.actor-kind--agent \.actor-kind-icon \{ color: var\(--star-yellow\); \}/);
    expect(css).toMatch(/\.actor-kind--automation \.actor-kind-icon \{ color: var\(--flag-red\); \}/);
    expect(css).not.toMatch(/\.actor-kind--(agent|automation) \{[^}]*color/);
  });
});
