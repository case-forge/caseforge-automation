
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { runPipelineStep, setMatterMode, setPipelineMode } from "./pipeline";
import { completeTodo, createTodo, deleteTodo, updateTodo } from "./todos";
import { draftFlagRequest } from "./draftFlag";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const ACTOR_KEYS = /(^|[\s{,])(by|edited_by|set_by|resolved_by|editor_name|created_by|who)\s*[:,}]/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

const SERVER_ONLY = new Set(["editor.ts", "hubProxy.ts", "accessIdentity.ts", "amendRound.ts"]);
const BROWSER_FILES = [
  ...files(join(ROOT, "components")),
  join(ROOT, "app/review-mail/page.tsx"),
  ...files(join(ROOT, "lib")).filter((p) => {
    const name = p.split("/").pop() ?? "";
    return !name.startsWith("stub") && !SERVER_ONLY.has(name);
  }),
];

function stringifiedObjects(src: string): string[] {
  const out: string[] = [];
  let at = src.indexOf("JSON.stringify({");
  while (at >= 0) {
    let i = at + "JSON.stringify(".length;
    let depth = 0;
    const start = i;
    for (; i < src.length; i++) {
      if (src[i] === "{") depth++;
      else if (src[i] === "}" && --depth === 0) break;
    }
    out.push(src.slice(start, i + 1));
    at = src.indexOf("JSON.stringify({", i);
  }
  return out;
}

describe("no naming step in the browser", () => {
  it("has no name box, no name prompt and no stored name", () => {
    for (const path of BROWSER_FILES) {
      const src = readFileSync(path, "utf8");
      expect(src, path).not.toMatch(/loadStoredEditorName|storeEditorName|resolveFlaggerName|caseforge-client-viewer:editor-name/);
      expect(src, path).not.toMatch(/prompt\(\s*"Your name/);
      expect(src, path).not.toMatch(/aria-label="Your name"|placeholder="Your name"|>\s*Your name\s*</);
    }
  });

  it("sends no actor name in any request body it builds", () => {
    for (const path of BROWSER_FILES) {
      for (const body of stringifiedObjects(readFileSync(path, "utf8"))) {
        expect(body, `${path}: ${body}`).not.toMatch(ACTOR_KEYS);
      }
    }
  });
});

describe("what the write helpers send", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("never names the person", async () => {
    const bodies: Record<string, unknown>[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === "POST") bodies.push(JSON.parse(String(init.body ?? "{}")));
        return new Response(JSON.stringify({ ok: true, workers: [], mode: "manual" }), { status: 200 });
      }),
    );
    vi.stubGlobal("window", { dispatchEvent: () => true });
    await completeTodo("t1", true);
    await updateTodo("t1", { starred: true });
    await deleteTodo("t1");
    await createTodo({ title: "Call the court" });
    await runPipelineStep("9001", "unpack");
    await setPipelineMode("auto", "9001");
    await setMatterMode("9001", "manual");
    expect(bodies.length).toBe(7);
    for (const body of bodies) {
      for (const key of ["by", "edited_by", "set_by", "resolved_by", "editor_name", "created_by", "who"]) {
        expect(body, JSON.stringify(body)).not.toHaveProperty(key);
      }
    }
    expect(draftFlagRequest("9001", true)).not.toHaveProperty("set_by");
  });
});
