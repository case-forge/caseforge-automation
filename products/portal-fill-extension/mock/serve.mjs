
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const PORT = 8377;
const dist = join(dirname(fileURLToPath(import.meta.url)), "dist");
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8" };

export function start() {
  const server = createServer(async (request, response) => {
    const name = new URL(request.url, "http://127.0.0.1").pathname === "/mock.js" ? "mock.js" : "index.html";
    try {
      response.writeHead(200, { "content-type": types[name.slice(name.lastIndexOf("."))] });
      response.end(await readFile(join(dist, name)));
    } catch {
      response.writeHead(500).end("Build the mock first: node build.mjs");
    }
  });
  return new Promise((resolve) => server.listen(PORT, "127.0.0.1", () => resolve(server)));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  await start();
  console.log(`Mock portal page: http://127.0.0.1:${PORT}/#/cases/case-details/0000/trigger/allegationsOfHarmRevised/allegationsOfHarmRevised1`);
}
