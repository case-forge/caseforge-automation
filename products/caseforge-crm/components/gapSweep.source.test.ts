import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const root = new URL("..", import.meta.url).pathname;

function files(dir: string, ext: RegExp, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (name === "node_modules" || name === ".next") continue;
    if (statSync(path).isDirectory()) files(path, ext, out);
    else if (ext.test(name) && !/\.test\./.test(name)) out.push(path);
  }
  return out;
}

const tsx = [...files(join(root, "components"), /\.tsx$/), ...files(join(root, "app"), /\.tsx$/)];

describe("controls the whole CRM must keep consistent", () => {
  it("every search box has the one named Lucide clear button, and the browser's own is hidden", () => {
    const withSearch = tsx.filter((f) => /type="search"/.test(readFileSync(f, "utf8")));
    for (const file of withSearch) {
      const text = readFileSync(file, "utf8");
      expect(/SearchClearButton|aria-label=\{?"Clear the search"/.test(text) || file.endsWith("ClearableSearch.tsx"), file).toBe(true);
    }
    const css = readFileSync(join(root, "app/globals.css"), "utf8");
    expect(css).toContain('input[type="search"]::-webkit-search-cancel-button');
    const clear = readFileSync(join(root, "components/ClearableSearch.tsx"), "utf8");
    expect(clear).toContain("<IconClose");
    expect(clear).toContain("aria-label={label}");
  });

  it("no text cross or arrow stands in for an icon in a component", () => {
    for (const file of tsx) {
      const code = readFileSync(file, "utf8")
        .split("\n")
        .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
        .join("\n");
      if (/Glyphs\.tsx$/.test(file)) continue;
      expect(code, file).not.toMatch(/[×✕✖✗✘]|&times;|&#8600;|&#10005;/);
    }
  });

  it("every modal dialog has a Close cross", () => {
    for (const name of ["RemoveClientButton", "MergeClientButton", "NewClientButton", "PendingNewClients"]) {
      expect(readFileSync(join(root, `components/${name}.tsx`), "utf8"), name).toContain("<DialogClose");
    }
  });
});
