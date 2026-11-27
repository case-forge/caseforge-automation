#!/usr/bin/env node

const [, , repoPath, manifestPath] = process.argv;
if (!repoPath || !manifestPath) {
  console.log(JSON.stringify({ ok: false, error: 'usage: bundletool_validate.mjs <repo-path> <manifest.json>' }));
  process.exit(2);
}

try {
  const { readFile } = await import('node:fs/promises');
  const { pathToFileURL } = await import('node:url');
  const { resolve } = await import('node:path');
  const { validateManifestShape } = await import(
    pathToFileURL(resolve(repoPath, 'public/js/manifestSchema.js')).href
  );
  const manifest = JSON.parse(await readFile(resolve(manifestPath), 'utf8'));
  validateManifestShape(manifest);
  console.log(JSON.stringify({ ok: true }));
} catch (err) {
  console.log(JSON.stringify({ ok: false, error: String(err && err.message ? err.message : err) }));
  process.exit(1);
}
