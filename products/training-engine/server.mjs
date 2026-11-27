
import http from "node:http";
import { randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createEngine } from "./engine/engine.gen.js";
import { handlerFor, str } from "./engine/dispatch.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const HOST = process.env.GAME_HOST || "127.0.0.1";
const PORT = Number(process.env.GAME_PORT || 8791);
const MAX_SESSIONS = Number(process.env.GAME_MAX_SESSIONS || 20);
const IDLE_MS = Number(process.env.GAME_IDLE_MS || 60 * 60 * 1000);
const COOKIE = "demo_game_sid";
const MAX_BODY = 64 * 1024;

const sessions = new Map();

function b64(bytes) {
  return Buffer.from(bytes).toString("base64");
}

function sweep() {
  const cutoff = Date.now() - IDLE_MS;
  for (const [sid, s] of sessions) if (s.last < cutoff) sessions.delete(sid);
  while (sessions.size > MAX_SESSIONS) sessions.delete(sessions.keys().next().value);
}

function session(req, res) {
  const m = /(?:^|;\s*)demo_game_sid=([a-f0-9]{32})/.exec(req.headers.cookie || "");
  let sid = m && m[1];
  let s = sid && sessions.get(sid);
  if (!s) {
    sid = randomBytes(16).toString("hex");
    s = { api: createEngine({}), last: Date.now() };
    sessions.set(sid, s);
    res.setHeader("Set-Cookie", `${COOKIE}=${sid}; Path=/; HttpOnly; SameSite=Lax`);
    sweep();
  }
  s.last = Date.now();
  return s;
}

function respond(api, force, caseflow) {
  const downloads = api.env.takeDownloads().map((d) => ({ name: d.name, type: d.type, b64: b64(d.bytes) }));
  const email = api.fns.activeEmail();
  return {
    patches: api.env.takePatches(force),
    meta: {
      serverNow: Date.now(),
      status: api.ui.status(),
      focus: api.env.takeFocus(),
      downloads,
      build: api.consts.APP_BUILD,
      buildSha: null,
      nextStep: email ? api.fns.nextTrainingStep(email) : null,
      board: api.fns.caseflowBoard(),
      stepInfo: api.fns.caseflowStepInfo(email),
      caseflow,
    },
  };
}

function send(res, status, body, type = "application/json") {
  const data = typeof body === "string" ? body : JSON.stringify(body);
  res.writeHead(status, { "Content-Type": type, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
  res.end(data);
}

async function readJson(req) {
  let size = 0;
  const chunks = [];
  for await (const c of req) {
    size += c.length;
    if (size > MAX_BODY) throw new Error("too large");
    chunks.push(c);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}

async function handleApi(req, res, path) {

  if (req.headers["sec-fetch-site"] === "cross-site") return send(res, 403, { error: "cross-site request blocked" });
  if (path === "/api/version" && req.method === "GET") return send(res, 200, { buildId: "", sessionExpiresAt: null });
  const { api } = session(req, res);
  if (path === "/api/state" && req.method === "GET") return send(res, 200, respond(api, true));
  if (path === "/api/action" && req.method === "POST") {
    let action;
    try {
      action = await readJson(req);
    } catch {
      return send(res, 400, { error: "bad json" });
    }
    const type = str(action.type);
    const handler = handlerFor(type);
    if (!handler) return send(res, 400, { error: "unknown action" });
    let result;
    try {
      result = handler(api, action);
    } catch (err) {
      console.error("action failed", type, err && err.message);
      api.fns.setStatus("That action failed on the server. Try again.");
    }
    api.helpers.logAction(type);
    return send(res, 200, respond(api, false, type === "caseflow-next" && result ? result : undefined));
  }
  return send(res, 404, { error: "not found" });
}

const STATIC = {
  "/": ["index.html", "text/html; charset=utf-8"],
  "/index.html": ["index.html", "text/html; charset=utf-8"],
  "/app.js": ["app.js", "text/javascript; charset=utf-8"],
  "/embed.css": ["embed.css", "text/css; charset=utf-8"],
  "/styles.css": ["styles.css", "text/css; charset=utf-8"],
};
const cache = new Map();
async function serveStatic(res, path) {
  const hit = STATIC[path];
  if (!hit) return send(res, 404, { error: "not found" });
  let body = cache.get(hit[0]);
  if (!body) {
    body = await readFile(join(HERE, "public", hit[0]));
    cache.set(hit[0], body);
  }
  res.writeHead(200, { "Content-Type": hit[1], "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff" });
  res.end(body);
}

const server = http.createServer((req, res) => {
  const path = new URL(req.url, "http://x").pathname;
  const run = path.startsWith("/api/") ? handleApi(req, res, path) : req.method === "GET" ? serveStatic(res, path) : send(res, 405, { error: "method" });
  Promise.resolve(run).catch((err) => {
    console.error("request failed", err && err.message);
    if (!res.headersSent) send(res, 500, { error: "server error" });
  });
});

server.listen(PORT, HOST, () => console.log(`training engine listening on ${HOST}:${PORT}`));
for (const sig of ["SIGTERM", "SIGINT"]) process.on(sig, () => server.close(() => process.exit(0)));
