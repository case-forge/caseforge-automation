
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOTS = [join(__dirname), join(__dirname, "..", "folder-locks")];
const WRITE = /export async function (PUT|POST|PATCH|DELETE)\([^\n]*\{\n([^\n]*)\n/g;

function routes(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return routes(path);
    return name === "route.ts" ? [path] : [];
  });
}

describe("settings write routes", () => {
  const files = ROOTS.flatMap(routes);
  it("finds the routes", () => expect(files.length).toBeGreaterThanOrEqual(9));
  it.each(files)("%s refuses a write from anyone but a developer first", (file) => {
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(WRITE)) {
      expect(match[2], `${match[1]} in ${file}`).toContain("await refuseUnlessDev(request)");
    }
  });
});
