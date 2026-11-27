
import { MATTER_FLAGS_CHANGED_EVENT } from "./draftFlag";
import { FLAGS_CHANGED_EVENT } from "./useFlagCounts";

export type FlagsByMatter = Record<string, Record<string, boolean>>;

const TTL_MS = 5_000;
const CHUNK = 200;

export const RETRY_MS = 400;

const cache = new Map<string, { at: number; promise: Promise<FlagsByMatter> }>();

const known = new Map<string, { at: number; flags: Record<string, boolean> }>();

export function invalidateMatterFlags(): void {
  cache.clear();
  known.clear();
}

export function knownMatterFlags(matterIds: readonly string[], now: number = Date.now()): FlagsByMatter {
  const out: FlagsByMatter = {};
  for (const id of matterIds) {
    const hit = known.get(id);
    if (hit && now - hit.at < TTL_MS) out[id] = hit.flags;
  }
  return out;
}

type FetchLike = (url: string) => Promise<Pick<Response, "ok" | "status" | "json">>;

async function readChunk(ids: string[], fetchImpl: FetchLike): Promise<FlagsByMatter> {
  const res = await fetchImpl(`/api/clients/matter-flags/batch?matter_ids=${encodeURIComponent(ids.join(","))}`);
  if (!res.ok) throw new Error(`request failed: ${res.status}`);
  const body = (await res.json()) as { flags_by_matter?: FlagsByMatter };
  return body.flags_by_matter ?? {};
}

function fetchChunk(ids: string[], fetchImpl: FetchLike): Promise<FlagsByMatter> {
  const key = [...ids].sort().join(",");
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.promise;
  const promise = readChunk(ids, fetchImpl)
    .catch(() => new Promise<FlagsByMatter>((resolve, reject) => setTimeout(() => readChunk(ids, fetchImpl).then(resolve, reject), RETRY_MS)))
    .then((flags) => {
      const at = Date.now();
      for (const [id, f] of Object.entries(flags)) known.set(id, { at, flags: f });
      return flags;
    })
    .catch(() => {
      if (cache.get(key)?.promise === promise) cache.delete(key);
      return {} as FlagsByMatter;
    });
  cache.set(key, { at: Date.now(), promise });
  return promise;
}

export async function fetchMatterFlagsBatch(matterIds: string[], fetchImpl: FetchLike = (url) => fetch(url)): Promise<FlagsByMatter> {
  const chunks: string[][] = [];
  for (let i = 0; i < matterIds.length; i += CHUNK) chunks.push(matterIds.slice(i, i + CHUNK));
  const parts = await Promise.all(chunks.map((c) => fetchChunk(c, fetchImpl)));
  return Object.assign({}, ...parts);
}

export const FLAGS_WAIT_MS = 500;

export function flagsReady(matterIds: readonly string[], ms: number = FLAGS_WAIT_MS, fetchImpl?: FetchLike): Promise<void> {
  if (matterIds.length === 0) return Promise.resolve();
  return new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    void fetchMatterFlagsBatch([...matterIds], fetchImpl).then(() => {
      clearTimeout(timer);
      resolve();
    });
  });
}

if (typeof window !== "undefined") {
  window.addEventListener(FLAGS_CHANGED_EVENT, invalidateMatterFlags);
  window.addEventListener(MATTER_FLAGS_CHANGED_EVENT, invalidateMatterFlags);
}
