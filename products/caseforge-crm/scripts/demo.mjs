#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { existsSync, readdirSync, statSync } from "node:fs";
import http from "node:http";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const APP = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ENGINE = resolve(APP, "..", "training-engine");
const DIST = ".next-demo";

export function parseArgs(argv, env = process.env) {
  const out = {
    host: "127.0.0.1",
    port: Number(env.DEMO_PORT || 3011),
    gamePort: Number(env.DEMO_GAME_PORT || 8791),
    rebuild: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--port") out.port = Number(argv[++i]);
    else if (a === "--game-port") out.gamePort = Number(argv[++i]);
    else if (a === "--rebuild") out.rebuild = true;
    else if (a === "--help" || a === "-h") out.help = true;
    else throw new Error(`unknown option ${a}`);
  }
  for (const n of [out.port, out.gamePort]) {
    if (!Number.isInteger(n) || n < 1 || n > 65535) throw new Error("ports must be whole numbers from 1 to 65535");
  }
  return out;
}

function newestSource(dir, skip = new Set(["node_modules", ".next", DIST, "scripts"])) {
  let newest = 0;
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (skip.has(e.name) || e.name.startsWith(".next")) continue;
    const p = join(dir, e.name);
    newest = Math.max(newest, e.isDirectory() ? newestSource(p, skip) : statSync(p).mtimeMs);
  }
  return newest;
}

export function needsBuild(force) {
  if (force) return true;
  if (!existsSync(join(APP, DIST, "BUILD_ID"))) return true;

  return newestSource(APP) > statSync(join(APP, DIST, "BUILD_ID")).mtimeMs;
}

function ping(url) {
  return new Promise((ok) => {
    const req = http.get(url, (res) => {
      res.resume();
      ok(res.statusCode === 200);
    });
    req.on("error", () => ok(false));
    req.setTimeout(3000, () => {
      req.destroy();
      ok(false);
    });
  });
}

async function waitFor(url, what, ms = 90000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await ping(url)) return;
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`${what} did not answer 200 at ${url} within ${ms / 1000}s`);
}

function run(cmd, args, env) {

  const base = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.toLowerCase().startsWith("npm_config_")));
  const r = spawnSync(cmd, args, { cwd: APP, stdio: "inherit", env: { ...base, ...env } });
  if (r.status !== 0) throw new Error(`${cmd} ${args.join(" ")} failed (${r.status})`);
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) {
    console.log("usage: npm run demo [-- --port 3011] [-- --game-port 8791] [-- --rebuild]");
    return;
  }
  if (Number(process.versions.node.split(".")[0]) < 20) throw new Error("Node 20 or newer is needed");
  const gameOrigin = `http://${opts.host}:${opts.gamePort}`;
  const common = { NEXT_TELEMETRY_DISABLED: "1" };
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";

  if (!existsSync(join(APP, "node_modules", "next"))) run(npm, ["ci", "--no-audit", "--no-fund"], common);
  if (needsBuild(opts.rebuild)) {
    console.log("demo: building the stub CRM");
    run(npm, ["run", "build:demo"], common);
  }

  const kids = [];
  const stop = () => {
    for (const k of kids) {
      try {
        process.kill(-k.pid, "SIGTERM");
      } catch {

      }
    }
  };
  const start = (cmd, args, env, cwd) => {
    const k = spawn(cmd, args, { cwd, env: { ...process.env, ...common, ...env }, stdio: "inherit", detached: true });
    kids.push(k);
    k.on("exit", (code) => {
      if (!stopping) {
        console.error(`demo: ${args[0]} exited (${code}); stopping`);
        stopping = true;
        stop();
        process.exitCode = 1;
      }
    });
    return k;
  };
  let stopping = false;
  for (const sig of ["SIGINT", "SIGTERM"]) {
    process.on(sig, () => {
      stopping = true;
      stop();
    });
  }

  start(process.execPath, ["server.mjs"], { GAME_HOST: opts.host, GAME_PORT: String(opts.gamePort) }, ENGINE);
  start(
    process.execPath,
    [join(APP, "node_modules", "next", "dist", "bin", "next"), "start", "-H", opts.host, "-p", String(opts.port)],
    { CASEFORGE_HUB_API_STUB: "1", CASEFORGE_NEXT_DIST_DIR: DIST, CASEFORGE_DEMO_GAME_ORIGIN: gameOrigin },
    APP,
  );
  const base = `http://${opts.host}:${opts.port}`;
  try {
    await waitFor(`${gameOrigin}/`, "the training engine");
    await waitFor(`${base}/training/`, "the demo CRM (/training/)");
    await waitFor(`${base}/`, "the demo CRM");
  } catch (err) {
    console.error(`demo: ${err.message}`);
    stopping = true;
    stop();
    process.exitCode = 1;
    return;
  }
  console.log(`\ndemo: ready. Open ${base}/ and press DEMO. Ctrl-C stops both servers.`);
  await new Promise((done) => {
    const t = setInterval(() => {
      if (stopping) {
        clearInterval(t);
        done();
      }
    }, 200);
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((err) => {
    console.error(`demo: ${err.message}`);
    process.exit(1);
  });
}
