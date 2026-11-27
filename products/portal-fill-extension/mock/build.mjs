
import { build } from "esbuild";
import { copyFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
await mkdir(join(here, "dist"), { recursive: true });
await build({
  entryPoints: [join(here, "src/main.ts")],
  bundle: true,
  outfile: join(here, "dist/mock.js"),
  format: "iife",
  target: "es2022",
  tsconfigRaw: { compilerOptions: { experimentalDecorators: true, useDefineForClassFields: false } },
  logLevel: "warning",
});
await copyFile(join(here, "index.html"), join(here, "dist/index.html"));
