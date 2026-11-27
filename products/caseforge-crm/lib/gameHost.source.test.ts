
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(fileURLToPath(new URL("./gameHost.ts", import.meta.url)), "utf8");
const UNLOAD = SOURCE.slice(SOURCE.indexOf("export function unloadGame"), SOURCE.indexOf("async function start"));

describe("gameHost.ts unloadGame", () => {
  it("is exported and calls the game's destroy hook only if it is a function", () => {
    expect(SOURCE).toContain("export function unloadGame(): void");
    expect(UNLOAD).toContain("__TRAINING_DESTROY__");
    expect(UNLOAD).toContain('typeof w.__TRAINING_DESTROY__ === "function"');
  });

  it("removes what the game added and resets loading so the next load fetches again", () => {
    for (const id of ["demo-game-css", "demoGameHolder", "demoGameOverlays"]) expect(UNLOAD).toContain(id);
    expect(UNLOAD).toContain("/training/app.js");
    expect(UNLOAD).toContain("delete w.__TRAINING_EMBED__");
    expect(UNLOAD).toContain("delete w.__TRAINING_BASE__");
    expect(UNLOAD).toContain("loading = null");
  });
});
