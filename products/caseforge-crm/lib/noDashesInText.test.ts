
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { basename, join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const PRODUCTS = join(__dirname, "..", "..");

const THIS_APP = basename(join(__dirname, ".."));
const APPS = [THIS_APP, "caseforge-chat-web", "caseforge-secretary"].filter((app) => existsSync(join(PRODUCTS, app)));
const SKIP_DIRS = new Set(["node_modules", ".next", "public", "scripts"]);

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) sourceFiles(full, out);
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) && !name.endsWith(".d.ts")) out.push(full);
  }
  return out;
}

export function withoutComments(source: string): string {

  return source
    .replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, ""))
    .replace(/(^|[^:"'`\w])\/\/.*$/gm, "$1");
}

export function dashOffences(source: string, label: string): string[] {
  return withoutComments(source)
    .split("\n")
    .flatMap((line, i) => (/ -- |—/.test(line) ? [`${label}:${i + 1}: ${line.trim().slice(0, 100)}`] : []));
}

describe("withoutComments", () => {
  it("drops comments but keeps text and URLs", () => {
    const src = 'const a = "x"; // note -- here\n/* block — dash */ const u = "http://a.b/c";\n{/* jsx -- comment */}';
    const cleaned = withoutComments(src);
    expect(cleaned).toContain('"http://a.b/c"');
    expect(cleaned).not.toMatch(/ -- |—/);
  });
  it("flags a visible double hyphen and a visible em dash", () => {
    expect(dashOffences('const s = "Refresh -- now";', "f")).toHaveLength(1);
    expect(dashOffences("<p>Onboarding — done</p>", "f")).toHaveLength(1);
    expect(dashOffences('const s = "Refresh. Now"; // fine -- comment', "f")).toEqual([]);
  });
});

describe("on-screen text", () => {
  it("has no em dash and no double-hyphen stand-in in the client viewer, chat or secretary", () => {
    const offences = APPS.flatMap((app) =>
      sourceFiles(join(PRODUCTS, app)).flatMap((file) =>
        dashOffences(readFileSync(file, "utf8"), relative(PRODUCTS, file).split(sep).join("/")),
      ),
    );
    expect(offences).toEqual([]);
  });
});
