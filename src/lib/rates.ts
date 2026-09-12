import "./env";
import fs from "node:fs";
import path from "node:path";
import { getJson, r2Enabled } from "./r2";
import { configuredPairKeys, pairKey } from "./config";

export type RateEntry = { ts: number; base: string; target: string; rate: number };

const R2_READ_CACHE_SECONDS = Number(process.env.R2_READ_CACHE_SECONDS ?? "60");
// Relative to the repo root, which is where both `astro dev` and the built
// server run from. (It was "../wp-content/uploads" while the app lived in
// astro-web/; leaving that after the move would have pointed one level above
// the repo.) In production WP_UPLOADS is set explicitly and this is unused —
// the container mounts the host directory somewhere else entirely.
const UPLOADS_DIR = process.env.WP_UPLOADS ?? path.resolve(process.cwd(), "wp-content/uploads");
const RATES_DIR = path.join(UPLOADS_DIR, "rates");

function cacheFresh(ts: number): boolean {
  return ts > 0 && (Date.now() - ts) / 1000 < R2_READ_CACHE_SECONDS;
}

// Fetching every pair at once turns a cold render into dozens of simultaneous
// R2 round trips, and — worse — holds every pair's full decoded history in
// memory at the same time, which costs more in GC than the serialized
// latencies it saves. A window wide enough to hide network latency, narrow
// enough that only a handful of histories are ever live at once.
const PAIR_CONCURRENCY = Math.max(1, Number(process.env.PAIR_CONCURRENCY ?? "6"));

/** Promise.all with a ceiling on how many run at once; results keep input order. */
export async function mapLimited<T, R>(
  items: readonly T[],
  worker: (item: T) => Promise<R>,
  limit = PAIR_CONCURRENCY,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const index = next++;
      results[index] = await worker(items[index]);
    }
  });
  await Promise.all(runners);
  return results;
}

/**
 * TTL memo for values derived from the rate set, on the same clock as the
 * entries themselves — past R2_READ_CACHE_SECONDS the inputs are reloaded
 * anyway, so a cached answer can never be staler than the data behind it.
 *
 * The in-flight promise is what is cached, not the resolved value: several
 * requests landing together on a cold cache then share one computation rather
 * than each starting their own. A rejected promise is dropped so the next
 * caller retries instead of inheriting the failure for a whole window.
 *
 * Cached values are shared by every caller and must be treated as read-only.
 */
export function memoByTtl<T>(compute: (key: string) => Promise<T>): (key: string) => Promise<T> {
  const cache = new Map<string, { ts: number; value: Promise<T> }>();
  return (key: string) => {
    const cached = cache.get(key);
    if (cached && cacheFresh(cached.ts)) return cached.value;
    const value = compute(key);
    cache.set(key, { ts: Date.now(), value });
    value.catch(() => {
      if (cache.get(key)?.value === value) cache.delete(key);
    });
    return value;
  };
}

// Mirrors _R2_PAIR_CACHE in the old app.py — caches misses too, since most
// menu pairs are derived and have no stored file of their own.
const pairCache = new Map<string, { ts: number; entries: RateEntry[] }>();
const allRatesCache: { ts: number; entries: RateEntry[] | null } = { ts: 0, entries: null };
const localRatesCache: { ts: number; entries: RateEntry[] | null } = { ts: 0, entries: null };
const usdTimelineCache: { ts: number; timeline: [number, Record<string, number>][] | null } = { ts: 0, timeline: null };
type UsdTable = { table: Record<string, number>; latestTs: number | null };
const latestUsdCache: { ts: number; value: UsdTable | null } = { ts: 0, value: null };

function pairJsonPath(base: string, target: string): string {
  return path.join(RATES_DIR, `${pairKey(base, target)}.json`);
}

function readLocalPairFile(base: string, target: string): RateEntry[] {
  const file = pairJsonPath(base, target);
  if (!fs.existsSync(file)) return [];
  try {
    return JSON.parse(fs.readFileSync(file, "utf-8"));
  } catch {
    return [];
  }
}

export async function loadPairEntries(base: string, target: string): Promise<RateEntry[]> {
  const key = pairKey(base, target);
  if (r2Enabled() && configuredPairKeys().has(key)) {
    const cached = pairCache.get(key);
    // A cached miss still falls through to the local file, exactly as a fresh
    // miss does — otherwise the first request of a window reads the local
    // file and the next 60 seconds' worth answer with the empty R2 result.
    if (cached && cacheFresh(cached.ts)) {
      if (cached.entries.length) return cached.entries;
    } else {
      try {
        const fetched = await getJson<RateEntry[]>(`rates/${key}.json`);
        const entries = Array.isArray(fetched) ? fetched : [];
        pairCache.set(key, { ts: Date.now(), entries });
        if (entries.length) return entries;
      } catch {
        // fall through to local file
      }
    }
  }
  return readLocalPairFile(base, target);
}

export async function loadJsonRates(): Promise<RateEntry[]> {
  if (r2Enabled()) {
    if (allRatesCache.entries !== null && cacheFresh(allRatesCache.ts)) return allRatesCache.entries;
    try {
      const index = await getJson<{ pairs?: { file?: string }[] }>("rates/index.json");
      const filenames = (index?.pairs ?? [])
        .map((pair) => (pair.file ? path.basename(pair.file) : ""))
        .filter((filename): filename is string => Boolean(filename));
      // One R2 GetObject round trip per pair file — fetch them concurrently
      // instead of one at a time, or a ~26-file cold load serializes to
      // 20+ seconds of pure network latency.
      const files = await Promise.all(filenames.map((filename) => getJson<RateEntry[]>(`rates/${filename}`)));
      const entries: RateEntry[] = [];
      for (const data of files) {
        if (Array.isArray(data)) entries.push(...data);
      }
      if (entries.length) {
        allRatesCache.ts = Date.now();
        allRatesCache.entries = entries;
        return entries;
      }
    } catch {
      // fall through to local files
    }
  }

  if (localRatesCache.entries !== null && cacheFresh(localRatesCache.ts)) return localRatesCache.entries;
  if (!fs.existsSync(RATES_DIR)) return [];
  const entries: RateEntry[] = [];
  for (const name of fs.readdirSync(RATES_DIR)) {
    if (!name.endsWith(".json") || name === "index.json") continue;
    try {
      entries.push(...JSON.parse(fs.readFileSync(path.join(RATES_DIR, name), "utf-8")));
    } catch {
      // skip unreadable file
    }
  }
  localRatesCache.ts = Date.now();
  localRatesCache.entries = entries;
  return entries;
}

function usdRateFor(table: Record<string, number>, currency: string): number | undefined {
  if (currency === "USD") return 1.0;
  return table[currency];
}

function addEntryToUsdTable(table: Record<string, number>, entry: RateEntry) {
  if (!entry.rate) return;
  if (entry.base === "USD") {
    table[entry.target] = Number(entry.rate);
  } else if (entry.target === "USD") {
    table[entry.base] = 1.0 / Number(entry.rate);
  }
}

export function deriveRateFromUsdTable(base: string, target: string, table: Record<string, number>): number | null {
  const basePerUsd = usdRateFor(table, base);
  const targetPerUsd = usdRateFor(table, target);
  if (!basePerUsd || !targetPerUsd) return null;
  return targetPerUsd / basePerUsd;
}

export async function usdTimeline(): Promise<[number, Record<string, number>][]> {
  if (usdTimelineCache.timeline !== null && cacheFresh(usdTimelineCache.ts)) return usdTimelineCache.timeline;
  const byTs = new Map<number, Record<string, number>>();
  for (const entry of await loadJsonRates()) {
    const ts = entry.ts ?? 0;
    if (!byTs.has(ts)) byTs.set(ts, {});
    addEntryToUsdTable(byTs.get(ts)!, entry);
  }
  const timeline = [...byTs.entries()].sort((a, b) => a[0] - b[0]);
  usdTimelineCache.ts = Date.now();
  usdTimelineCache.timeline = timeline;
  return timeline;
}

export async function derivedPairHistory(base: string, target: string, since?: number): Promise<RateEntry[]> {
  const data: RateEntry[] = [];
  for (const [ts, table] of await usdTimeline()) {
    if (since !== undefined && ts < since) continue;
    const rate = deriveRateFromUsdTable(base, target, table);
    if (rate !== null) data.push({ ts, base, target, rate });
  }
  return data;
}

export async function derivedPairLatest(base: string, target: string): Promise<RateEntry | null> {
  const timeline = await usdTimeline();
  for (let i = timeline.length - 1; i >= 0; i--) {
    const [ts, table] = timeline[i];
    const rate = deriveRateFromUsdTable(base, target, table);
    if (rate !== null) return { ts, base, target, rate };
  }
  return null;
}

export async function pairHistory(base: string, target: string): Promise<RateEntry[]> {
  base = base.toUpperCase();
  target = target.toUpperCase();
  if (base === target) {
    return [{ ts: Math.floor(Date.now() / 1000), base, target, rate: 1.0 }];
  }
  const direct = await loadPairEntries(base, target);
  if (direct.length) return direct;
  return derivedPairHistory(base, target);
}

// A full pass over every stored entry, and the home page needs the answer
// three times over (the rate board, the converter, and the hero tiles). Cached
// on the same clock as the entries it is derived from, so the pass happens
// once per refresh window rather than once per caller.
export async function buildLatestUsdTable(): Promise<UsdTable> {
  if (latestUsdCache.value !== null && cacheFresh(latestUsdCache.ts)) return latestUsdCache.value;
  const value = await computeLatestUsdTable();
  latestUsdCache.ts = Date.now();
  latestUsdCache.value = value;
  return value;
}

async function computeLatestUsdTable(): Promise<UsdTable> {
  const latestByCurrency: Record<string, number> = { USD: 1.0 };
  const latestTsByCurrency: Record<string, number> = { USD: 0 };
  let latestTs: number | null = null;
  // An entry contributes at most one currency to the table, so it is read
  // straight off rather than through a throwaway one-key object per entry —
  // this loop runs over every stored point of every pair.
  for (const entry of await loadJsonRates()) {
    const ts = Math.trunc(entry.ts ?? 0);
    const rate = Number(entry.rate);
    if (rate) {
      let currency: string | null = null;
      let perUsd = 0;
      if (entry.base === "USD") {
        currency = entry.target;
        perUsd = rate;
      } else if (entry.target === "USD") {
        currency = entry.base;
        perUsd = 1.0 / rate;
      }
      if (currency !== null && ts >= (latestTsByCurrency[currency] ?? 0)) {
        latestByCurrency[currency] = perUsd;
        latestTsByCurrency[currency] = ts;
      }
    }
    if (latestTs === null || ts > latestTs) latestTs = ts;
  }
  return { table: latestByCurrency, latestTs };
}
